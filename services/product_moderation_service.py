from datetime import datetime, timezone
import uuid
from fastapi import HTTPException, status
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from models.product_moderation import ProductModeration
from models.processed_event import ProcessedEvent
from models.field_report import FieldReport
from models.blocking_reason import BlockingReason
from schemas.events import ProductEventIn
from schemas.moderation import (
    DeclineRequest, ProductModerationCard, BlockingHistory,
    BlockingReasonOut, FieldReportOut
)
from services.b2b_client import fetch_product, send_moderation_event
from services.moderation_queue import get_next as get_next_from_queue


def _sum_active_quantity(product_data: dict) -> int:
    skus = product_data.get("skus") or []
    total = 0
    for sku in skus:
        try:
            total += int(sku.get("active_quantity") or 0)
        except (TypeError, ValueError):
            continue
    return total


def _queue_for_edit(existing: ProductModeration, total_active_quantity: int) -> int:
    if existing.blocking_reason_id is not None:
        return 2
    return 3 if total_active_quantity > 0 else 4


async def handle_b2b_event(db: AsyncSession, payload: ProductEventIn) -> dict:
    result = await db.execute(
        select(ProcessedEvent).where(
            ProcessedEvent.sender_service == "b2b",
            ProcessedEvent.idempotency_key == payload.idempotency_key,
        )
    )
    existing_event = result.scalar_one_or_none()
    if existing_event:
        return existing_event.response_cached or {"status": "duplicate"}

    response_payload: dict = {"status": "processed"}

    if payload.event == payload.event.DELETED:
        await db.execute(
            delete(ProductModeration).where(ProductModeration.product_id == payload.product_id)
        )
    else:
        product_data = await fetch_product(str(payload.product_id))
        total_active_quantity = _sum_active_quantity(product_data)

        result = await db.execute(
            select(ProductModeration).where(ProductModeration.product_id == payload.product_id)
        )
        item = result.scalar_one_or_none()

        if payload.event == payload.event.CREATED or item is None:
            if item is None:
                item = ProductModeration(
                    product_id=payload.product_id,
                    seller_id=payload.seller_id,
                )
                db.add(item)
            item.json_before = None
            item.json_after = product_data
            item.status = "PENDING"
            item.queue_priority = 1
            item.total_active_quantity = total_active_quantity
            item.date_moderation = None
        else:
            item.json_before = item.json_after
            item.json_after = product_data
            item.status = "PENDING"
            item.total_active_quantity = total_active_quantity
            item.queue_priority = _queue_for_edit(item, total_active_quantity)

    db.add(
        ProcessedEvent(
            sender_service="b2b",
            idempotency_key=payload.idempotency_key,
            response_cached=response_payload,
            processed_at=datetime.now(timezone.utc),
        )
    )

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return {"status": "duplicate"}

    return response_payload


async def get_next_card(db: AsyncSession, moderator_id: str, queue_id: int | None) -> ProductModeration | None:
    """
        Один get-next = одна карточка переходит из PENDING в IN_REVIEW с moderator_id
        Повторный get-next с тем же queueId возьмёт следующую карточку PENDING, а не ту же самую
        Товар, который взял, уже IN_REVIEW — он исключается из выборки PENDING
        работаешь с товаром (смотришь json_before/json_after, принимаешь решение) 
        и явно вызываешь approve или decline.После этого товар уходит из очереди (MODERATED/BLOCKED/HARD_BLOCKED).
        Если взял товар и ничего не сделал — он останется в IN_REVIEW навсегда 
        (таймаут возврата в PENDING не реализован, это в планах на будущее).
    """
    item = await get_next_from_queue(db, moderator_id=moderator_id, queue_id=queue_id)
    if item is not None:
        await db.commit()
        await db.refresh(item)
    
    return item 


async def _build_card(db: AsyncSession, item: ProductModeration) -> ProductModerationCard:
    field_reports_result = await db.execute(
        select(FieldReport).where(FieldReport.product_moderation_id == item.id)
    )
    field_reports = field_reports_result.scalars().all()

    blocking_reason = None
    if item.blocking_reason_id:
        reason_result = await db.execute(
            select(BlockingReason).where(BlockingReason.id == item.blocking_reason_id)
        )
        blocking_reason = reason_result.scalar_one_or_none()

    history = None
    if blocking_reason or field_reports:
        history = BlockingHistory(
            blocking_reason=BlockingReasonOut.model_validate(blocking_reason)
            if blocking_reason else None,
            field_reports=[FieldReportOut.model_validate(fr) for fr in field_reports],
        )

    return ProductModerationCard(
        id=str(item.id),
        product_id=str(item.product_id),
        seller_id=str(item.seller_id),
        status=item.status,
        queue_priority=item.queue_priority,
        total_active_quantity=item.total_active_quantity,
        json_before=item.json_before,
        json_after=item.json_after,
        blocking_reason_id=str(item.blocking_reason_id) if item.blocking_reason_id else None,
        moderator_id=str(item.moderator_id) if item.moderator_id else None,
        moderator_comment=item.moderator_comment,
        date_created=item.date_created,
        date_updated=item.date_updated,
        date_moderation=item.date_moderation,
        blocking_history=history
    )


async def approve_product(db: AsyncSession, product_id: str, moderator_id: str) -> None:
    product_uuid = uuid.UUID(product_id)
    result = await db.execute(
        select(ProductModeration).where(ProductModeration.product_id == product_uuid)
    )
    item = result.scalar_one_or_none()

    if not item or item.status != "IN_REVIEW":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Карточка не найдена")
    if str(item.moderator_id) != moderator_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нет доступа")

    product_data = await fetch_product(product_id)
    if not (product_data.get("skus") or []):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Товар не содержит SKU",
        )

    item.status = "MODERATED"
    item.date_moderation = datetime.now(timezone.utc)
    item.blocking_reason_id = None
    item.moderator_comment = None

    await db.execute(
        delete(FieldReport).where(FieldReport.product_moderation_id == item.id)
    )

    payload = {
        "idempotency_key": str(uuid.uuid4()),
        "product_id": product_id,
        "event_type": "MODERATED",
    }

    try:
        await send_moderation_event(payload)
        await db.commit()
    except Exception:
        await db.rollback()
        raise


async def decline_product(
    db: AsyncSession, product_id: str, moderator_id: str, data: DeclineRequest
) -> bool:
    product_uuid = uuid.UUID(product_id)
    result = await db.execute(
        select(ProductModeration).where(ProductModeration.product_id == product_uuid)
    )
    item = result.scalar_one_or_none()

    if not item or item.status != "IN_REVIEW":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Карточка не найдена")
    if str(item.moderator_id) != moderator_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нет доступа")

    reason_uuid = uuid.UUID(data.blocking_reason_id)
    reason_result = await db.execute(
        select(BlockingReason).where(BlockingReason.id == reason_uuid)
    )
    reason = reason_result.scalar_one_or_none()
    if not reason:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Причина блокировки не найдена",
        )

    await db.execute(
        delete(FieldReport).where(FieldReport.product_moderation_id == item.id)
    )

    for report in data.field_reports:
        db.add(FieldReport(
            product_moderation_id=item.id,
            field_name=report.field_name,
            sku_id=report.sku_id,
            comment=report.comment,
        ))

    item.blocking_reason_id = reason.id
    item.moderator_comment = data.moderator_comment
    item.status = "HARD_BLOCKED" if reason.hard_block else "BLOCKED"
    item.date_moderation = datetime.now(timezone.utc)

    payload = {
        "idempotency_key": str(uuid.uuid4()),
        "product_id": product_id,
        "event_type": "BLOCKED",
        "hard_block": bool(reason.hard_block),
        "blocking_reason": {
            "id": str(reason.id),
            "title": reason.title,
            "comment": data.moderator_comment or "",
        },
        "field_reports": [
            {
                "field_name": report.field_name,
                "sku_id": report.sku_id,
                "comment": report.comment,
            }
            for report in data.field_reports
        ],
    }

    try:
        await send_moderation_event(payload)
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    return bool(reason.hard_block)


async def list_blocking_reasons(db: AsyncSession) -> list[BlockingReason]:
    result = await db.execute(select(BlockingReason))
    return result.scalars().all()

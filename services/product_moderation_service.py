from datetime import datetime, timezone
import uuid
import sqlalchemy as sa
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from models import Ticket, ProcessedEvent, FieldReport, BlockingReason, TicketHistory, TicketBlockingReason
from schemas.events import IncomingB2BEvent, B2BEventType, EventProductCreated, EventProductEdited, EventProductDeleted
from schemas.moderation import (
    TicketResponse, TicketDetailResponse, FieldReport as FieldReportSchema,
    TicketHistoryEntry, BlockDecisionRequest
)
from schemas.blocking_reason import BlockingReasonResponse
from core.errors import raise_api_error
from services.b2b_client import send_moderation_event


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _has_skus(ticket: Ticket) -> bool:
    payload = ticket.json_after
    if not isinstance(payload, dict):
        return False
    skus = payload.get("skus")
    return isinstance(skus, list) and len(skus) > 0


async def add_history_entry(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    action: str,
    moderator_id: uuid.UUID | None = None,
    comment: str | None = None,
) -> None:
    db.add(TicketHistory(
        ticket_id=ticket_id,
        action=action,
        moderator_id=moderator_id,
        comment=comment,
    ))


async def handle_b2b_event(db: AsyncSession, payload: IncomingB2BEvent) -> bool:
    result = await db.execute(
        select(ProcessedEvent).where(
            ProcessedEvent.sender_service == "b2b",
            ProcessedEvent.idempotency_key == payload.idempotency_key,
        )
    )
    existing_event = result.scalar_one_or_none()
    if existing_event:
        return True

    if payload.event_type == B2BEventType.PRODUCT_DELETED:
        await db.execute(
            delete(Ticket).where(Ticket.product_id == payload.payload.product_id)
        )
    else:
        if payload.event_type == B2BEventType.PRODUCT_CREATED:
            data = payload.payload
            if not isinstance(data, EventProductCreated):
                raise_api_error(400, "BAD_REQUEST", "Invalid payload")
            kind = "CREATE"
            json_before = None
            json_after = data.json_after
            queue_priority = data.queue_priority or 3
        else:
            data = payload.payload
            if not isinstance(data, EventProductEdited):
                raise_api_error(400, "BAD_REQUEST", "Invalid payload")
            kind = "EDIT"
            json_before = data.json_before
            json_after = data.json_after
            queue_priority = data.queue_priority or 3

        result = await db.execute(
            select(Ticket).where(Ticket.product_id == data.product_id)
        )
        ticket = result.scalar_one_or_none()
        if ticket is None:
            ticket = Ticket(
                product_id=data.product_id,
                seller_id=data.seller_id,
            )
            db.add(ticket)
            await db.flush()
        elif payload.event_type == B2BEventType.PRODUCT_CREATED and ticket.status == "HARD_BLOCKED":
            db.add(
                ProcessedEvent(
                    sender_service="b2b",
                    idempotency_key=payload.idempotency_key,
                    response_cached={"status": "accepted"},
                    processed_at=_now(),
                )
            )
            try:
                await db.commit()
            except IntegrityError:
                await db.rollback()
            return False
        elif payload.event_type == B2BEventType.PRODUCT_EDITED and ticket.status == "HARD_BLOCKED":
            db.add(
                ProcessedEvent(
                    sender_service="b2b",
                    idempotency_key=payload.idempotency_key,
                    response_cached={"status": "accepted"},
                    processed_at=_now(),
                )
            )
            try:
                await db.commit()
            except IntegrityError:
                await db.rollback()
            return False

        ticket.category_id = data.category_id
        ticket.kind = kind
        ticket.status = "PENDING"
        ticket.queue_priority = queue_priority
        ticket.json_before = json_before
        ticket.json_after = json_after
        ticket.assigned_moderator_id = None
        ticket.claimed_at = None
        ticket.claim_expires_at = None
        ticket.decision_at = None
        ticket.decision_comment = None
        ticket.blocking_reason_id = None

        await db.execute(
            delete(FieldReport).where(FieldReport.product_moderation_id == ticket.id)
        )
        await db.execute(
            delete(TicketBlockingReason).where(TicketBlockingReason.ticket_id == ticket.id)
        )
        await add_history_entry(db, ticket.id, "CREATED")

    db.add(
        ProcessedEvent(
            sender_service="b2b",
            idempotency_key=payload.idempotency_key,
            response_cached={"status": "accepted"},
            processed_at=_now(),
        )
    )

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()

    return False

def _to_ticket_response(ticket: Ticket) -> TicketResponse:
    return TicketResponse.model_validate(ticket)


async def get_ticket(db: AsyncSession, ticket_id: str) -> Ticket:
    ticket_uuid = uuid.UUID(ticket_id)
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_uuid))
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise_api_error(404, "NOT_FOUND", "Ticket not found")
    return ticket


async def build_ticket_detail(db: AsyncSession, ticket: Ticket) -> TicketDetailResponse:
    field_reports_result = await db.execute(
        select(FieldReport).where(FieldReport.product_moderation_id == ticket.id)
    )
    field_reports = field_reports_result.scalars().all()

    reasons_result = await db.execute(
        select(BlockingReason)
        .join(TicketBlockingReason, TicketBlockingReason.reason_id == BlockingReason.id)
        .where(TicketBlockingReason.ticket_id == ticket.id)
    )
    reasons = reasons_result.scalars().all()

    history_result = await db.execute(
        select(TicketHistory).where(TicketHistory.ticket_id == ticket.id)
        .order_by(TicketHistory.at.asc())
    )
    history = history_result.scalars().all()

    detail = TicketDetailResponse.model_validate(ticket)
    detail.field_reports = [
        FieldReportSchema(
            field_path=fr.field_path,
            message=fr.message,
            severity=fr.severity,
        )
        for fr in field_reports
    ]
    detail.blocking_reasons = [BlockingReasonResponse.model_validate(r) for r in reasons]
    detail.decision_comment = ticket.decision_comment
    detail.history = [
        TicketHistoryEntry(
            at=h.at,
            action=h.action,
            moderator_id=h.moderator_id,
            comment=h.comment,
        )
        for h in history
    ]
    return detail


async def list_tickets(
    db: AsyncSession,
    limit: int,
    offset: int,
    status: str | None = None,
    moderator_id: str | None = None,
    product_id: str | None = None,
    seller_id: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> tuple[list[Ticket], int]:
    filters: list[sa.ColumnElement[bool]] = []
    if status:
        filters.append(Ticket.status == status)
    if moderator_id:
        filters.append(Ticket.assigned_moderator_id == uuid.UUID(moderator_id))
    if product_id:
        filters.append(Ticket.product_id == uuid.UUID(product_id))
    if seller_id:
        filters.append(Ticket.seller_id == uuid.UUID(seller_id))
    if created_from:
        filters.append(Ticket.created_at >= created_from)
    if created_to:
        filters.append(Ticket.created_at <= created_to)

    count_result = await db.execute(
        sa.select(sa.func.count()).select_from(Ticket).where(*filters)
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        select(Ticket).where(*filters)
        .order_by(Ticket.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return result.scalars().all(), total


async def release_ticket(db: AsyncSession, ticket: Ticket, moderator_id: uuid.UUID, is_admin: bool) -> None:
    if ticket.status == "HARD_BLOCKED":
        raise_api_error(403, "FORBIDDEN", "Ticket is hard blocked")
    if ticket.status != "IN_REVIEW":
        raise_api_error(409, "TICKET_WRONG_STATUS", "Ticket is not in review")
    if not is_admin and ticket.assigned_moderator_id != moderator_id:
        raise_api_error(409, "TICKET_WRONG_OWNER", "Ticket is assigned to another moderator")

    ticket.status = "PENDING"
    ticket.assigned_moderator_id = None
    ticket.claimed_at = None
    ticket.claim_expires_at = None
    await add_history_entry(db, ticket.id, "RELEASED", moderator_id)
    await db.commit()


async def approve_ticket(
    db: AsyncSession,
    ticket: Ticket,
    moderator_id: uuid.UUID,
    comment: str | None = None,
) -> None:
    if ticket.status == "HARD_BLOCKED":
        raise_api_error(403, "FORBIDDEN", "Ticket is hard blocked")
    if ticket.status != "IN_REVIEW":
        raise_api_error(409, "TICKET_WRONG_STATUS", "Ticket is not in review")
    if ticket.assigned_moderator_id != moderator_id:
        raise_api_error(403, "FORBIDDEN", "Ticket is assigned to another moderator")
    if not _has_skus(ticket):
        raise_api_error(409, "PRODUCT_NO_SKU", "Product has no SKU")

    ticket.status = "APPROVED"
    ticket.decision_at = _now()
    ticket.decision_comment = comment
    ticket.blocking_reason_id = None

    await db.execute(delete(FieldReport).where(FieldReport.product_moderation_id == ticket.id))
    await db.execute(delete(TicketBlockingReason).where(TicketBlockingReason.ticket_id == ticket.id))
    await add_history_entry(db, ticket.id, "APPROVED", moderator_id)

    payload = {
        "idempotency_key": str(uuid.uuid4()),
        "product_id": str(ticket.product_id),
        "event_type": "MODERATED",
        "occurred_at": ticket.decision_at.isoformat(),
    }

    try:
        await send_moderation_event(payload)
        await db.commit()
    except Exception:
        await db.rollback()
        raise


async def block_ticket(
    db: AsyncSession,
    ticket: Ticket,
    moderator_id: uuid.UUID,
    data: BlockDecisionRequest,
) -> None:
    if ticket.status == "HARD_BLOCKED":
        raise_api_error(403, "FORBIDDEN", "Ticket is hard blocked")
    if ticket.status != "IN_REVIEW":
        raise_api_error(409, "TICKET_WRONG_STATUS", "Ticket is not in review")
    if ticket.assigned_moderator_id != moderator_id:
        raise_api_error(409, "TICKET_WRONG_OWNER", "Ticket is assigned to another moderator")

    reasons_result = await db.execute(
        select(BlockingReason).where(BlockingReason.id.in_(data.blocking_reason_ids))
    )
    reasons = reasons_result.scalars().all()
    if len(reasons) != len(data.blocking_reason_ids):
        raise_api_error(404, "NOT_FOUND", "Blocking reason not found")

    await db.execute(delete(FieldReport).where(FieldReport.product_moderation_id == ticket.id))
    await db.execute(delete(TicketBlockingReason).where(TicketBlockingReason.ticket_id == ticket.id))

    for report in data.field_reports:
        db.add(FieldReport(
            product_moderation_id=ticket.id,
            field_path=report.field_path,
            message=report.message,
            severity=report.severity,
        ))

    for reason in reasons:
        db.add(TicketBlockingReason(ticket_id=ticket.id, reason_id=reason.id))

    is_hard_block = any(reason.hard_block for reason in reasons)
    ticket.status = "HARD_BLOCKED" if is_hard_block else "BLOCKED"
    ticket.decision_at = _now()
    ticket.decision_comment = data.comment
    ticket.blocking_reason_id = reasons[0].id if reasons else None

    await add_history_entry(
        db,
        ticket.id,
        "HARD_BLOCKED" if is_hard_block else "BLOCKED",
        moderator_id,
        data.comment,
    )

    payload = {
        "idempotency_key": str(uuid.uuid4()),
        "product_id": str(ticket.product_id),
        "event_type": "BLOCKED",
        "occurred_at": ticket.decision_at.isoformat(),
        "hard_block": bool(is_hard_block),
        "blocking_reason_id": str(reasons[0].id) if reasons else None,
        "comment": data.comment or "",
        "field_reports": [
            {
                "field_name": report.field_path,
                "comment": report.message,
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
import sqlalchemy as sa
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from models import ProductModeration
from fastapi import HTTPException, status


QUEUE_IDS = (1, 2, 3, 4)


def _queue_filters(queue_id: int) -> list[sa.ColumnElement[bool]]:
    base_filters: list[sa.ColumnElement[bool]] = [
        ProductModeration.status == "PENDING",
    ]

    if queue_id == 1:
        return base_filters + [ProductModeration.date_moderation.is_(None)]

    if queue_id == 2:
        return base_filters + [
            ProductModeration.date_moderation.is_not(None),
            ProductModeration.blocking_reason_id.is_not(None),
        ]

    if queue_id == 3:
        return base_filters + [
            ProductModeration.date_moderation.is_not(None),
            ProductModeration.blocking_reason_id.is_(None),
            ProductModeration.total_active_quantity > 0,
        ]

    return base_filters + [
        ProductModeration.date_moderation.is_not(None),
        ProductModeration.blocking_reason_id.is_(None),
        ProductModeration.total_active_quantity == 0,
    ]


async def get_next(db: AsyncSession, moderator_id: sa.UUID, queue_id: int | None = None) -> ProductModeration | None:
    if isinstance(moderator_id, str):
        moderator_id = uuid.UUID(moderator_id)

    if queue_id is not None and queue_id not in QUEUE_IDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="queue_id must be in 1..4",
        )
    
    queue_ids = (queue_id,) if queue_id is not None else QUEUE_IDS


    for current_queue in queue_ids:
        filters = _queue_filters(current_queue)

        stmt = (
            sa.select(ProductModeration)
            .where(*filters)
            .order_by(ProductModeration.date_updated.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        )

        result = await db.execute(stmt)
        item = result.scalar_one_or_none()
        if not item:
            continue

        item.status = "IN_REVIEW"
        item.moderator_id = moderator_id
        await db.flush()
        return item

    return None

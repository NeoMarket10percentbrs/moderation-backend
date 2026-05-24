from datetime import datetime, timedelta, timezone
import sqlalchemy as sa
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from models import Ticket, TicketHistory


async def return_expired_tickets(db: AsyncSession) -> None:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        sa.select(Ticket)
        .where(Ticket.status == "IN_REVIEW", Ticket.claim_expires_at < now)
    )
    expired = result.scalars().all()
    for ticket in expired:
        moderator_id = ticket.assigned_moderator_id
        ticket.status = "PENDING"
        ticket.assigned_moderator_id = None
        ticket.claimed_at = None
        ticket.claim_expires_at = None
        db.add(TicketHistory(
            ticket_id=ticket.id,
            action="AUTO_RETURNED",
            moderator_id=moderator_id,
        ))


async def claim_next_ticket(
    db: AsyncSession,
    moderator_id: str | uuid.UUID,
    queue_priority: int | None = None,
    category_ids: list[uuid.UUID] | None = None,
) -> Ticket | None:
    if isinstance(moderator_id, str):
        moderator_id = uuid.UUID(moderator_id)

    await return_expired_tickets(db)

    filters = [Ticket.status == "PENDING"]
    if queue_priority is not None:
        filters.append(Ticket.queue_priority == queue_priority)
    if category_ids:
        filters.append(Ticket.category_id.in_(category_ids))

    stmt = (
        sa.select(Ticket)
        .where(*filters)
        .order_by(Ticket.queue_priority.asc(), Ticket.created_at.asc())
        .with_for_update(skip_locked=True)
        .limit(1)
    )

    result = await db.execute(stmt)
    ticket = result.scalar_one_or_none()
    if not ticket:
        return None

    now = datetime.now(timezone.utc)
    ticket.status = "IN_REVIEW"
    ticket.assigned_moderator_id = moderator_id
    ticket.claimed_at = now
    ticket.claim_expires_at = now + timedelta(minutes=30)
    await db.flush()
    return ticket


async def list_pending_tickets(
    db: AsyncSession,
    limit: int,
    offset: int,
    queue_priority: int | None = None,
    category_id: uuid.UUID | None = None,
    seller_id: uuid.UUID | None = None,
) -> tuple[list[Ticket], int]:
    filters = [Ticket.status == "PENDING"]
    if queue_priority is not None:
        filters.append(Ticket.queue_priority == queue_priority)
    if category_id is not None:
        filters.append(Ticket.category_id == category_id)
    if seller_id is not None:
        filters.append(Ticket.seller_id == seller_id)

    count_result = await db.execute(
        sa.select(sa.func.count()).select_from(Ticket).where(*filters)
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        sa.select(Ticket)
        .where(*filters)
        .order_by(Ticket.queue_priority.asc(), Ticket.created_at.asc())
        .offset(offset)
        .limit(limit)
    )
    return result.scalars().all(), total

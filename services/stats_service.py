from datetime import datetime, timedelta, timezone
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from models import Ticket, TicketHistory, Moderator


def _period_start(period: str) -> datetime:
    now = datetime.now(timezone.utc)
    if period == "week":
        return now - timedelta(days=7)
    if period == "month":
        return now - timedelta(days=30)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


async def get_overview(db: AsyncSession, period: str) -> dict:
    start = _period_start(period)

    pending_count = await _count_status(db, "PENDING")
    in_review_count = await _count_status(db, "IN_REVIEW")
    approved_count = await _count_decisions(db, "APPROVED", start)
    blocked_count = await _count_decisions(db, "BLOCKED", start)
    hard_blocked_count = await _count_decisions(db, "HARD_BLOCKED", start)

    avg_review = await _avg_review_time(db, start)
    pending_by_priority = await _pending_by_priority(db)

    return {
        "pending_count": pending_count,
        "in_review_count": in_review_count,
        "approved_count": approved_count,
        "blocked_count": blocked_count,
        "hard_blocked_count": hard_blocked_count,
        "avg_review_time_seconds": avg_review,
        "pending_by_priority": pending_by_priority,
    }


async def get_moderator_stats(db: AsyncSession, period: str) -> list[dict]:
    start = _period_start(period)

    decisions_stmt = (
        sa.select(
            Ticket.assigned_moderator_id.label("moderator_id"),
            sa.func.count().label("decisions_count"),
            sa.func.sum(sa.case((Ticket.status == "APPROVED", 1), else_=0)).label("approved_count"),
            sa.func.sum(sa.case((Ticket.status == "BLOCKED", 1), else_=0)).label("blocked_count"),
            sa.func.sum(sa.case((Ticket.status == "HARD_BLOCKED", 1), else_=0)).label("hard_blocked_count"),
            sa.func.avg(
                sa.func.extract("epoch", Ticket.decision_at - Ticket.claimed_at)
            ).label("avg_review_time_seconds"),
        )
        .where(
            Ticket.decision_at.is_not(None),
            Ticket.decision_at >= start,
            Ticket.assigned_moderator_id.is_not(None),
        )
        .group_by(Ticket.assigned_moderator_id)
    )

    decisions_result = await db.execute(decisions_stmt)
    decisions = {row.moderator_id: row for row in decisions_result.fetchall()}

    if not decisions:
        return []

    released_stmt = (
        sa.select(
            TicketHistory.moderator_id.label("moderator_id"),
            sa.func.count().label("released_count"),
        )
        .where(
            TicketHistory.action == "RELEASED",
            TicketHistory.at >= start,
            TicketHistory.moderator_id.is_not(None),
        )
        .group_by(TicketHistory.moderator_id)
    )
    released_result = await db.execute(released_stmt)
    released = {row.moderator_id: row.released_count for row in released_result.fetchall()}

    moderators_stmt = sa.select(Moderator).where(Moderator.id.in_(decisions.keys()))
    moderators_result = await db.execute(moderators_stmt)
    moderators = {m.id: m for m in moderators_result.scalars().all()}

    stats = []
    for moderator_id, row in decisions.items():
        moderator = moderators.get(moderator_id)
        stats.append({
            "moderator_id": moderator_id,
            "moderator_name": f"{moderator.first_name} {moderator.last_name}" if moderator else None,
            "decisions_count": row.decisions_count or 0,
            "approved_count": row.approved_count or 0,
            "blocked_count": row.blocked_count or 0,
            "hard_blocked_count": row.hard_blocked_count or 0,
            "avg_review_time_seconds": int(row.avg_review_time_seconds) if row.avg_review_time_seconds else None,
            "released_count": released.get(moderator_id, 0),
        })

    return stats


async def _count_status(db: AsyncSession, status: str) -> int:
    result = await db.execute(
        sa.select(sa.func.count()).select_from(Ticket).where(Ticket.status == status)
    )
    return result.scalar() or 0


async def _count_decisions(db: AsyncSession, status: str, start: datetime) -> int:
    result = await db.execute(
        sa.select(sa.func.count()).select_from(Ticket).where(
            Ticket.status == status,
            Ticket.decision_at >= start,
        )
    )
    return result.scalar() or 0


async def _avg_review_time(db: AsyncSession, start: datetime) -> int | None:
    result = await db.execute(
        sa.select(
            sa.func.avg(sa.func.extract("epoch", Ticket.decision_at - Ticket.claimed_at))
        ).where(
            Ticket.decision_at.is_not(None),
            Ticket.decision_at >= start,
            Ticket.claimed_at.is_not(None),
        )
    )
    value = result.scalar()
    return int(value) if value is not None else None


async def _pending_by_priority(db: AsyncSession) -> dict:
    result = await db.execute(
        sa.select(Ticket.queue_priority, sa.func.count())
        .where(Ticket.status == "PENDING")
        .group_by(Ticket.queue_priority)
    )
    return {str(priority): count for priority, count in result.fetchall()}

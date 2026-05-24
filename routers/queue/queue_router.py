from fastapi import APIRouter, Depends, Response, status
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from core.dependencies import get_current_moderator
from schemas.moderation import QueueClaimRequest, PaginatedTickets, TicketResponse
from services.moderation_queue import claim_next_ticket, list_pending_tickets, return_expired_tickets
from services.product_moderation_service import add_history_entry


queue_router = APIRouter(
    prefix="/v1/queue",
    tags=["Queue"],
    dependencies=[Depends(get_current_moderator)],
)


@queue_router.get("", response_model=PaginatedTickets)
async def list_queue(
    limit: int = 20,
    offset: int = 0,
    queue_priority: int | None = None,
    category_id: str | None = None,
    seller_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    await return_expired_tickets(db)
    await db.commit()
    category_uuid = uuid.UUID(category_id) if category_id else None
    seller_uuid = uuid.UUID(seller_id) if seller_id else None
    tickets, total = await list_pending_tickets(
        db,
        limit=limit,
        offset=offset,
        queue_priority=queue_priority,
        category_id=category_uuid,
        seller_id=seller_uuid,
    )
    return PaginatedTickets(
        items=[TicketResponse.model_validate(t) for t in tickets],
        total_count=total,
        limit=limit,
        offset=offset,
    )


@queue_router.post("/claim", response_model=TicketResponse)
async def claim_ticket(
    data: QueueClaimRequest | None = None,
    db: AsyncSession = Depends(get_db),
    moderator=Depends(get_current_moderator),
):
    payload = data or QueueClaimRequest()
    ticket = await claim_next_ticket(
        db,
        moderator_id=str(moderator.id),
        queue_priority=payload.queue_priority,
        category_ids=payload.category_ids,
    )
    if not ticket:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    await add_history_entry(db, ticket.id, "CLAIMED", moderator.id)
    await db.commit()
    await db.refresh(ticket)
    return TicketResponse.model_validate(ticket)

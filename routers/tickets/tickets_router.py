from fastapi import APIRouter, Depends
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from core.dependencies import get_current_moderator
from schemas.moderation import (
    PaginatedTickets, TicketResponse, TicketDetailResponse,
    BlockDecisionRequest, ApproveRequest,
)
from services import product_moderation_service


tickets_router = APIRouter(
    prefix="/v1/tickets",
    tags=["Tickets"],
    dependencies=[Depends(get_current_moderator)],
)


@tickets_router.get("", response_model=PaginatedTickets)
async def list_tickets(
    limit: int = 20,
    offset: int = 0,
    status: str | None = None,
    moderator_id: str | None = None,
    product_id: str | None = None,
    seller_id: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    db: AsyncSession = Depends(get_db),
):
    tickets, total = await product_moderation_service.list_tickets(
        db,
        limit=limit,
        offset=offset,
        status=status,
        moderator_id=moderator_id,
        product_id=product_id,
        seller_id=seller_id,
        created_from=created_from,
        created_to=created_to,
    )
    return PaginatedTickets(
        items=[TicketResponse.model_validate(t) for t in tickets],
        total_count=total,
        limit=limit,
        offset=offset,
    )


@tickets_router.get("/{ticket_id}", response_model=TicketDetailResponse)
async def get_ticket(ticket_id: str, db: AsyncSession = Depends(get_db)):
    ticket = await product_moderation_service.get_ticket(db, ticket_id)
    return await product_moderation_service.build_ticket_detail(db, ticket)


@tickets_router.post("/{ticket_id}/release", response_model=TicketResponse)
async def release_ticket(
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
    moderator=Depends(get_current_moderator),
):
    ticket = await product_moderation_service.get_ticket(db, ticket_id)
    await product_moderation_service.release_ticket(
        db,
        ticket,
        moderator_id=moderator.id,
        is_admin=moderator.role == "ADMIN",
    )
    await db.refresh(ticket)
    return TicketResponse.model_validate(ticket)


@tickets_router.post("/{ticket_id}/approve", response_model=TicketResponse)
async def approve_ticket(
    ticket_id: str,
    data: ApproveRequest | None = None,
    db: AsyncSession = Depends(get_db),
    moderator=Depends(get_current_moderator),
):
    ticket = await product_moderation_service.get_ticket(db, ticket_id)
    await product_moderation_service.approve_ticket(
        db,
        ticket,
        moderator_id=moderator.id,
        comment=data.comment if data else None,
    )
    await db.refresh(ticket)
    return TicketResponse.model_validate(ticket)


@tickets_router.post("/{ticket_id}/block", response_model=TicketResponse)
async def block_ticket(
    ticket_id: str,
    data: BlockDecisionRequest,
    db: AsyncSession = Depends(get_db),
    moderator=Depends(get_current_moderator),
):
    ticket = await product_moderation_service.get_ticket(db, ticket_id)
    await product_moderation_service.block_ticket(db, ticket, moderator_id=moderator.id, data=data)
    await db.refresh(ticket)
    return TicketResponse.model_validate(ticket)

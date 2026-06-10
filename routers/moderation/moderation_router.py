from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from core.dependencies import get_current_moderator
from schemas.moderation import (
    GetNextRequest,
    ProductModerationCard,
    BlockDecisionRequest,
    PaginatedTickets,
)
from schemas.blocking_reason import BlockingReasonResponse
from models.moderation_status import ModerationStatus
from schemas.product_moderation import ApproveResponse, DeclineResponse
from services import product_moderation_service

moderation_router = APIRouter(tags=["Moderation"])


@moderation_router.post(
    "/v1/product-moderation/get-next",
    response_model=ProductModerationCard,
)
async def get_next_card(
    data: GetNextRequest | None = None,
    db: AsyncSession = Depends(get_db),
    moderator=Depends(get_current_moderator),
):
    queue_id = data.queue_id if data else None
    item = await product_moderation_service.get_next_card(
        db, moderator_id=str(moderator.id), queue_id=queue_id
    )
    if not item:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return await product_moderation_service.build_ticket_detail(db, item)


@moderation_router.post(
    "/v1/products/{product_id}/approve",
    response_model=ApproveResponse,
)
async def approve_product(
    product_id: str,
    db: AsyncSession = Depends(get_db),
    moderator=Depends(get_current_moderator),
):
    await product_moderation_service.approve_product(db, product_id, str(moderator.id))
    return ApproveResponse(status="MODERATED")


@moderation_router.post(
    "/v1/products/{product_id}/decline",
    response_model=DeclineResponse,
)
async def decline_product(
    product_id: str,
    data: BlockDecisionRequest,
    db: AsyncSession = Depends(get_db),
    moderator=Depends(get_current_moderator),
):
    hard_block = await product_moderation_service.decline_product(
        db, product_id, str(moderator.id), data
    )
    return DeclineResponse(status="BLOCKED", hard_block=hard_block)


@moderation_router.get(
    "/v1/products/",
    response_model=PaginatedTickets,
)
async def get_all_products(
    status: ModerationStatus,
    limit: int = 20,
    page: int = 1,
    db: AsyncSession = Depends(get_db),
    moderator=Depends(get_current_moderator),
):
    return await product_moderation_service.get_all_products(
        db, status=status.value, limit=limit, page=page
    )


@moderation_router.get(
    "/v1/product-blocking-reasons",
    response_model=list[BlockingReasonResponse],
)
async def get_blocking_reasons(
    db: AsyncSession = Depends(get_db), moderator=Depends(get_current_moderator)
):
    reasons = await product_moderation_service.list_blocking_reasons(db)
    return [
        BlockingReasonResponse(
            id=reason.id,
            code=reason.code,
            title=reason.title,
            description=reason.description,
            hard_block=reason.hard_block,
            is_active=reason.is_active,
        )
        for reason in reasons
    ]

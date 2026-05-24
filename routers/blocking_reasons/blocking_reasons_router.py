from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from core.dependencies import get_current_moderator, require_admin_moderator
from core.errors import raise_api_error
from schemas.blocking_reason import (
    BlockingReasonCreateRequest, BlockingReasonUpdateRequest, BlockingReasonResponse,
)
from services.blocking_reason_service import (
    list_blocking_reasons, get_blocking_reason, create_blocking_reason,
)


blocking_reasons_router = APIRouter(
    prefix="/v1/blocking-reasons",
    tags=["BlockingReasons"],
    dependencies=[Depends(get_current_moderator)],
)


@blocking_reasons_router.get("", response_model=list[BlockingReasonResponse])
async def list_reasons(
    hard_block: bool | None = None,
    is_active: bool | None = True,
    db: AsyncSession = Depends(get_db),
):
    reasons = await list_blocking_reasons(db, hard_block=hard_block, is_active=is_active)
    return [BlockingReasonResponse.model_validate(r) for r in reasons]


@blocking_reasons_router.post(
    "", response_model=BlockingReasonResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin_moderator)],
)
async def create_reason(
    data: BlockingReasonCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    reason = await create_blocking_reason(
        db,
        code=data.code,
        title=data.title,
        description=data.description,
        hard_block=data.hard_block,
    )
    await db.commit()
    await db.refresh(reason)
    return BlockingReasonResponse.model_validate(reason)


@blocking_reasons_router.patch(
    "/{reason_id}", response_model=BlockingReasonResponse,
    dependencies=[Depends(require_admin_moderator)],
)
async def update_reason(
    reason_id: str,
    data: BlockingReasonUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    reason = await get_blocking_reason(db, reason_id)
    if not reason:
        raise_api_error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Blocking reason not found")

    if data.title is not None:
        reason.title = data.title
    if data.description is not None:
        reason.description = data.description
    if data.is_active is not None:
        reason.is_active = data.is_active

    await db.commit()
    await db.refresh(reason)
    return BlockingReasonResponse.model_validate(reason)


@blocking_reasons_router.delete(
    "/{reason_id}", status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin_moderator)],
)
async def deactivate_reason(reason_id: str, db: AsyncSession = Depends(get_db)):
    reason = await get_blocking_reason(db, reason_id)
    if not reason:
        raise_api_error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Blocking reason not found")

    reason.is_active = False
    await db.commit()

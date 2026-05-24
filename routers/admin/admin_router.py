from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from core.dependencies import get_current_moderator, require_admin_moderator
from core.errors import raise_api_error
from schemas.moderator import (
    ModeratorCreateRequest, ModeratorUpdateRequest, ModeratorResponse, PaginatedModerators
)
from services import auth_service
from services.moderator_service import (
    list_moderators, set_moderator_active, update_moderator, get_moderator_by_id
)


admin_router = APIRouter(prefix="/v1/moderators", tags=["Moderators"])


@admin_router.get("", response_model=PaginatedModerators, dependencies=[Depends(require_admin_moderator)])
async def get_moderators(
    limit: int = 20,
    offset: int = 0,
    is_active: bool | None = None,
    db: AsyncSession = Depends(get_db),
):
    moderators, total = await list_moderators(db, is_active=is_active, limit=limit, offset=offset)
    return PaginatedModerators(
        items=[ModeratorResponse.model_validate(m) for m in moderators],
        total_count=total,
        limit=limit,
        offset=offset,
    )


@admin_router.post(
    "", response_model=ModeratorResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin_moderator)],
)
async def create_moderator(
    data: ModeratorCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    moderator = await auth_service.register(db, data)
    return ModeratorResponse.model_validate(moderator)


@admin_router.get("/me", response_model=ModeratorResponse)
async def get_me(moderator=Depends(get_current_moderator)):
    return ModeratorResponse.model_validate(moderator)


@admin_router.get(
    "/{moderator_id}", response_model=ModeratorResponse,
    dependencies=[Depends(require_admin_moderator)],
)
async def get_moderator(moderator_id: str, db: AsyncSession = Depends(get_db)):
    moderator = await get_moderator_by_id(db, moderator_id)
    if not moderator:
        raise_api_error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Moderator not found")
    return ModeratorResponse.model_validate(moderator)


@admin_router.patch(
    "/{moderator_id}", response_model=ModeratorResponse,
    dependencies=[Depends(require_admin_moderator)],
)
async def update_moderator_handler(
    moderator_id: str,
    data: ModeratorUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    moderator = await update_moderator(db, moderator_id, data)
    if not moderator:
        raise_api_error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Moderator not found")
    await db.commit()
    await db.refresh(moderator)
    return ModeratorResponse.model_validate(moderator)


@admin_router.delete(
    "/{moderator_id}", status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin_moderator)],
)
async def deactivate_moderator(
    moderator_id: str,
    db: AsyncSession = Depends(get_db),
):
    moderator = await set_moderator_active(db, moderator_id, is_active=False)
    if not moderator:
        raise_api_error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Moderator not found")

    await db.commit()

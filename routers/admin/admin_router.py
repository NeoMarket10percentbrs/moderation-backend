from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from core.dependencies import require_admin_moderator
from schemas.moderator import ModeratorCreate, ModeratorRead
from services import auth_service
from services.moderator_service import list_moderators, set_moderator_active


admin_router = APIRouter(
    prefix="/v1/admin", tags=["Admin"],
    dependencies=[Depends(require_admin_moderator)]
)


@admin_router.post(
    "/register", response_model=ModeratorRead,
    status_code=status.HTTP_201_CREATED,
    summary="Регистрация модератора"
)
async def register(
    data: ModeratorCreate,
    db: AsyncSession = Depends(get_db),
):
    moderator = await auth_service.register(db, data)
    return ModeratorRead.model_validate(moderator)


@admin_router.get("/moderators", response_model=list[ModeratorRead])
async def get_moderators(db: AsyncSession = Depends(get_db)):
    moderators = await list_moderators(db)
    return [ModeratorRead.model_validate(m) for m in moderators]


@admin_router.post("/moderators/{moderator_id}/ban", response_model=ModeratorRead)
async def ban_moderator(
    moderator_id: str,
    db: AsyncSession = Depends(get_db),
):
    moderator = await set_moderator_active(db, moderator_id, is_active=False)
    if not moderator:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Модератор не найден")

    await db.commit()
    await db.refresh(moderator)
    return ModeratorRead.model_validate(moderator)

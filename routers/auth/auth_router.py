from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from schemas.auth import TokenResponse, RefreshRequest, LoginRequest
from services import auth_service
from core.dependencies import require_admin_moderator

auth_router = APIRouter(prefix="/auth", tags=["Auth"])


@auth_router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    return await auth_service.login(db, data.email, data.password)


@auth_router.post("/refresh", response_model=TokenResponse, summary="Обновить токены")
async def refresh(data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    return await auth_service.refresh_tokens(db, data.refresh_token)


@auth_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Выход")
async def logout(data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    await auth_service.logout(db, data.refresh_token)

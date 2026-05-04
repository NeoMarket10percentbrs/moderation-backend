from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from core.security import decode_access_token
from core.config import settings
from models.moderator import Moderator
from services.moderator_service import get_moderator_by_id

security = HTTPBearer()

async def get_current_moderator(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> Moderator:
    token = credentials.credentials
    try:
        moderator_id = decode_access_token(token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невалидный токен",
            headers={"WWW-Authenticate": "Bearer"},
        )

    moderator = await get_moderator_by_id(db, moderator_id)
    if not moderator:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Модератор не найден",
        )

    return moderator


def require_service_key(x_service_key: str | None = Header(default=None, alias="X-Service-Key")) -> str:
    if not x_service_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="X-Service-Key обязателен")
    return x_service_key


def require_moderation_key(x_service_key: str = Depends(require_service_key)) -> None:
    if x_service_key != settings.MOD_SERVICE_KEY:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Неверный Service Key")


def require_b2c_key(x_service_key: str = Depends(require_service_key)) -> None:
    if x_service_key != settings.B2C_SERVICE_KEY:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Неверный Service Key")


def require_b2b_to_mod_key(x_service_key: str = Depends(require_service_key)) -> None:
    if x_service_key != settings.B2B_TO_MOD_KEY:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Неверный Service Key")


def require_internal_token(x_internal_token: str | None = Header(default=None, alias="X-Internal-Token")) -> None:
    if not x_internal_token or x_internal_token != settings.INTERNAL_API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Неверный внутренний токен",
        )


async def require_admin_moderator(
    moderator: Moderator = Depends(get_current_moderator)
) -> Moderator:
    if not moderator.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Требуются права администратора",
        )
    return moderator

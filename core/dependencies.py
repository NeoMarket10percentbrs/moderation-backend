from fastapi import Depends, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from core.security import decode_access_token
from core.errors import raise_api_error
from core.config import settings
from models.moderator import Moderator
from services.moderator_service import get_moderator_by_id

security = HTTPBearer(scheme_name="bearerAuth")

async def get_current_moderator(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> Moderator:
    token = credentials.credentials
    try:
        payload = decode_access_token(token)
    except JWTError:
        raise_api_error(
            status.HTTP_401_UNAUTHORIZED,
            "UNAUTHORIZED",
            "Invalid token",
        )

    moderator = await get_moderator_by_id(db, payload["moderator_id"])
    if not moderator:
        raise_api_error(
            status.HTTP_401_UNAUTHORIZED,
            "UNAUTHORIZED",
            "Moderator not found",
        )

    if not moderator.is_active:
        raise_api_error(
            status.HTTP_403_FORBIDDEN,
            "FORBIDDEN",
            "Moderator is inactive",
        )

    return moderator


def require_service_key(x_service_key: str | None = Header(default=None, alias="X-Service-Key")) -> str:
    if not x_service_key:
        raise_api_error(
            status.HTTP_401_UNAUTHORIZED,
            "UNAUTHORIZED",
            "X-Service-Key is required",
        )
    return x_service_key


def require_moderation_key(x_service_key: str = Depends(require_service_key)) -> None:
    if x_service_key != settings.MOD_SERVICE_KEY:
        raise_api_error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "Invalid service key")


def require_b2c_key(x_service_key: str = Depends(require_service_key)) -> None:
    if x_service_key != settings.B2C_SERVICE_KEY:
        raise_api_error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "Invalid service key")


def require_b2b_to_mod_key(x_service_key: str = Depends(require_service_key)) -> None:
    if x_service_key != settings.B2B_TO_MOD_KEY:
        raise_api_error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "Invalid service key")


def require_internal_token(x_internal_token: str | None = Header(default=None, alias="X-Internal-Token")) -> None:
    if not x_internal_token or x_internal_token != settings.INTERNAL_API_TOKEN:
        raise_api_error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "Invalid internal token")


async def require_admin_moderator(
    moderator: Moderator = Depends(get_current_moderator)
) -> Moderator:
    if moderator.role != "ADMIN":
        raise_api_error(
            status.HTTP_403_FORBIDDEN,
            "FORBIDDEN",
            "Admin role required",
        )
    return moderator

from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError
from models.refresh_token import RefreshToken
from models.moderator import Moderator
from schemas.auth import TokenPairResponse, LoginResponse
from schemas.moderator import ModeratorRead, ModeratorCreate
from core.security import (
    verify_password, create_access_token,
    generate_refresh_token, hash_refresh_token,
)
from core.config import settings
from services.moderator_service import (
    get_moderator_by_email, get_moderator_by_id, create_moderator
)


async def register(db: AsyncSession, data: ModeratorCreate) -> Moderator:
    existing = await get_moderator_by_email(db, data.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Модератор с таким email уже существует",
        )

    new_moderator = await create_moderator(db, data)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if "unique" in str(exc.orig).lower() or "moderators_email_key" in str(exc.orig):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Модератор с таким email уже существует",
            ) from exc
        raise

    await db.refresh(new_moderator)

    return new_moderator


async def login(db: AsyncSession, email: str, password: str) -> LoginResponse:
    moderator = await get_moderator_by_email(db, email)
    if not moderator or not verify_password(password, moderator.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный email или пароль",
        )
    if not moderator.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Модератор заблокирован",
        )
    tokens = await _issue_tokens(db, moderator)
    return LoginResponse(
        user=ModeratorRead.model_validate(moderator),
        **tokens,
    )


async def refresh_tokens(db: AsyncSession, raw_token: str) -> TokenPairResponse:
    token_hash = hash_refresh_token(raw_token)

    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked == False,
            RefreshToken.expires_at > datetime.now(timezone.utc),
        )
    )
    db_token = result.scalar_one_or_none()

    if not db_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невалидный или истёкший refresh token",
        )

    db_token.revoked = True
    await db.commit()

    moderator = await get_moderator_by_id(db, db_token.moderator_id)
    tokens = await _issue_tokens(db, moderator)
    return TokenPairResponse(**tokens)


async def logout(db: AsyncSession, raw_token: str) -> None:
    token_hash = hash_refresh_token(raw_token)

    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    db_token = result.scalar_one_or_none()

    if db_token:
        db_token.revoked = True
        await db.commit()


async def _issue_tokens(db: AsyncSession, moderator: Moderator) -> dict:
    access_token = create_access_token(str(moderator.id))
    raw_refresh = generate_refresh_token()

    db.add(RefreshToken(
        moderator_id=moderator.id,
        token_hash=hash_refresh_token(raw_refresh),
        expires_at=datetime.now(timezone.utc) + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        ),
    ))

    result = await db.execute(
        select(RefreshToken.id)
        .where(RefreshToken.moderator_id == moderator.id)
        .order_by(RefreshToken.created_at.asc())
    )
    all_token_ids = result.scalars().all()
    if len(all_token_ids) > 5:
        ids_to_delete = all_token_ids[:len(all_token_ids) - 5]
        await db.execute(
            delete(RefreshToken).where(RefreshToken.id.in_(ids_to_delete))
        )

    await db.commit()

    return {
        "access_token": access_token,
        "refresh_token": raw_refresh,
        "token_type": "Bearer",
        "expires_in": int(settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60),
    }


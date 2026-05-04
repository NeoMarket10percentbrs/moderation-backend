import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models.moderator import Moderator
from schemas.moderator import ModeratorCreate
from core.security import hash_password


async def get_moderator_by_id(db: AsyncSession, moderator_id: str | uuid.UUID):
	moderator_uuid = moderator_id if isinstance(moderator_id, uuid.UUID) else uuid.UUID(moderator_id)
	result = await db.execute(
		select(Moderator).where(Moderator.id == moderator_uuid)
	)
	return result.scalar_one_or_none()


async def get_moderator_by_email(db: AsyncSession, email: str):
	result = await db.execute(
		select(Moderator).where(Moderator.email == email)
	)
	return result.scalar_one_or_none()


async def create_moderator(db: AsyncSession, data: ModeratorCreate, is_admin: bool = False) -> Moderator:
	moderator = Moderator(
		email=data.email,
		password_hash=hash_password(data.password),
		first_name=data.first_name,
		last_name=data.last_name,
		is_active=True,
		is_admin=is_admin
	)
	db.add(moderator)
	return moderator


async def list_moderators(db: AsyncSession) -> list[Moderator]:
	result = await db.execute(select(Moderator).order_by(Moderator.created_at.desc()))
	return result.scalars().all()


async def set_moderator_active(db: AsyncSession, moderator_id: str | uuid.UUID, is_active: bool) -> Moderator | None:
	moderator = await get_moderator_by_id(db, moderator_id)
	if not moderator:
		return None

	moderator.is_active = is_active
	return moderator

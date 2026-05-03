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


async def create_moderator(db: AsyncSession, data: ModeratorCreate) -> Moderator:
	moderator = Moderator(
		email=data.email,
		password_hash=hash_password(data.password),
		first_name=data.first_name,
		last_name=data.last_name,
		is_active=True,
	)
	db.add(moderator)
	return moderator

import uuid
import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models.moderator import Moderator
from schemas.moderator import ModeratorCreateRequest, ModeratorUpdateRequest
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


async def create_moderator(
    db: AsyncSession, data: ModeratorCreateRequest, is_admin: bool = False
) -> Moderator:
	moderator = Moderator(
		email=data.email,
		password_hash=hash_password(data.password),
		first_name=data.first_name,
		last_name=data.last_name or "",
		is_active=True,
		is_admin=is_admin,
		role=data.role if hasattr(data, "role") else ("ADMIN" if is_admin else "MODERATOR"),
		category_specializations=[str(cid) for cid in data.category_specializations]
	)
	db.add(moderator)
	return moderator


async def list_moderators(
	db: AsyncSession, is_active: bool | None, limit: int, offset: int
) -> tuple[list[Moderator], int]:
	query = select(Moderator)
	if is_active is not None:
		query = query.where(Moderator.is_active == is_active)

	count_result = await db.execute(
		select(sa.func.count()).select_from(query.subquery())
	)
	total = count_result.scalar() or 0

	result = await db.execute(
		query.order_by(Moderator.created_at.desc()).offset(offset).limit(limit)
	)
	return result.scalars().all(), total


async def set_moderator_active(db: AsyncSession, moderator_id: str | uuid.UUID, is_active: bool) -> Moderator | None:
	moderator = await get_moderator_by_id(db, moderator_id)
	if not moderator:
		return None

	moderator.is_active = is_active
	return moderator


async def update_moderator(
	db: AsyncSession, moderator_id: str | uuid.UUID, data: ModeratorUpdateRequest
) -> Moderator | None:
	moderator = await get_moderator_by_id(db, moderator_id)
	if not moderator:
		return None

	if data.first_name is not None:
		moderator.first_name = data.first_name
	if data.last_name is not None:
		moderator.last_name = data.last_name
	if data.role is not None:
		moderator.role = data.role
		moderator.is_admin = data.role == "ADMIN"
	if data.is_active is not None:
		moderator.is_active = data.is_active
	if data.category_specializations is not None:
		moderator.category_specializations = [str(cid) for cid in data.category_specializations]

	return moderator

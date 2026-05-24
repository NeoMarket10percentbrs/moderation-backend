import uuid
from datetime import datetime
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from typing import TYPE_CHECKING
from core.database import Base

if TYPE_CHECKING:
	from models.refresh_token import RefreshToken


class Moderator(Base):
	__tablename__ = "moderators"

	id: Mapped[uuid.UUID] = mapped_column(
		UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
	)
	email: Mapped[str] = mapped_column(sa.String(255), nullable=False, unique=True)
	password_hash: Mapped[str] = mapped_column(sa.String(255), nullable=False)
	first_name: Mapped[str] = mapped_column(sa.String(100), nullable=False)
	last_name: Mapped[str] = mapped_column(sa.String(100), nullable=False)
	is_active: Mapped[bool] = mapped_column(
		sa.Boolean, nullable=False, default=True, server_default=sa.true()
	)
	role: Mapped[str] = mapped_column(
		sa.String(20), nullable=False, default="MODERATOR", server_default=sa.text("'MODERATOR'")
	)
	category_specializations: Mapped[list] = mapped_column(
		JSONB, nullable=False, default=list, server_default=sa.text("'[]'::jsonb")
	)
	is_admin: Mapped[bool] = mapped_column(
		sa.Boolean, nullable=False, default=False, server_default=sa.false()
	)
	created_at: Mapped[datetime] = mapped_column(
		sa.DateTime(timezone=True), server_default=func.now(), nullable=False
	)
	last_login_at: Mapped[datetime | None] = mapped_column(
		sa.DateTime(timezone=True), nullable=True
	)

	refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
		back_populates="moderator", cascade="all, delete-orphan"
	)

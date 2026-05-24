from datetime import datetime
from enum import Enum
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field


class ModeratorRole(str, Enum):
	MODERATOR = "MODERATOR"
	ADMIN = "ADMIN"


class ModeratorCreateRequest(BaseModel):
	email: EmailStr
	password: str = Field(min_length=12)
	first_name: str = Field(max_length=100)
	last_name: str | None = Field(default=None, max_length=100)
	role: ModeratorRole
	category_specializations: list[UUID] = Field(default_factory=list)


class ModeratorUpdateRequest(BaseModel):
	first_name: str | None = Field(default=None, max_length=100)
	last_name: str | None = Field(default=None, max_length=100)
	role: ModeratorRole | None = None
	is_active: bool | None = None
	category_specializations: list[UUID] | None = None


class ModeratorResponse(BaseModel):
	id: UUID
	email: EmailStr
	first_name: str
	last_name: str | None = None
	role: ModeratorRole
	is_active: bool
	category_specializations: list[UUID] = Field(default_factory=list)
	created_at: datetime
	last_login_at: datetime | None = None

	class Config:
		from_attributes = True


class PaginatedModerators(BaseModel):
	items: list[ModeratorResponse]
	total_count: int
	limit: int
	offset: int

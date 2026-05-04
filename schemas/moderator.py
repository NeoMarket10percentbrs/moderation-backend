from uuid import UUID
from pydantic import BaseModel, EmailStr


class ModeratorCreate(BaseModel):
	email: EmailStr
	password: str
	first_name: str
	last_name: str


class ModeratorRead(BaseModel):
	id: UUID
	email: EmailStr
	first_name: str
	last_name: str
	is_active: bool
	is_admin: bool

	class Config:
		from_attributes = True

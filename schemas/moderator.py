from pydantic import BaseModel, EmailStr


class ModeratorCreate(BaseModel):
	email: EmailStr
	password: str
	first_name: str
	last_name: str


class ModeratorRead(BaseModel):
	id: str
	email: EmailStr
	first_name: str
	last_name: str
	is_active: bool

	class Config:
		from_attributes = True

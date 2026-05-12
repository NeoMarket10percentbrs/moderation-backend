from pydantic import BaseModel, EmailStr
from schemas.moderator import ModeratorRead


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int


class LoginResponse(TokenPairResponse):
    user: ModeratorRead


class RefreshRequest(BaseModel):
    refresh_token: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"

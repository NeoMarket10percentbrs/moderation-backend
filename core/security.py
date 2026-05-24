import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
import bcrypt
from core.config import settings


def hash_password(password: str) -> str:
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    password_byte = plain_password.encode('utf-8')
    hashed_byte = hashed_password.encode('utf-8')
    return bcrypt.checkpw(password_byte, hashed_byte)


def create_access_token(moderator_id: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": moderator_id,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "jti": str(uuid.uuid4()),
    }
    secret = settings.SECRET_KEY
    algorithm = settings.ALGORITHM
    return jwt.encode(payload, secret, algorithm=algorithm)


def decode_access_token(token: str) -> dict:
    secret = settings.SECRET_KEY
    algorithm = settings.ALGORITHM
    payload = jwt.decode(token, secret, algorithms=[algorithm])

    moderator_id: str | None = payload.get("sub")
    if moderator_id is None:
        raise JWTError("Missing subject")

    role: str | None = payload.get("role")
    if not role:
        raise JWTError("Missing role")

    return {"moderator_id": moderator_id, "role": role}


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(64)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

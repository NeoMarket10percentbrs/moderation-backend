from pydantic import BaseModel


class Error(BaseModel):
    code: str
    message: str
    details: dict | None = None

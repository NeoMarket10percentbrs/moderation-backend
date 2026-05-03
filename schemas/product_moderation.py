from pydantic import BaseModel


class ApproveResponse(BaseModel):
    status: str


class DeclineResponse(BaseModel):
    status: str
    hard_block: bool

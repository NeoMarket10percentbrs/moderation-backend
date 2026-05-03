from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class GetNextRequest(BaseModel):
    queue_id: int | None = Field(default=None, alias="queueId")

    class Config:
        populate_by_name = True


class FieldReportIn(BaseModel):
    field_name: str
    sku_id: str | None = None
    comment: str


class DeclineRequest(BaseModel):
    blocking_reason_id: str
    moderator_comment: str | None = None
    field_reports: list[FieldReportIn]


class BlockingReasonOut(BaseModel):
    id: str
    title: str
    hard_block: bool

    class Config:
        from_attributes = True


class FieldReportOut(BaseModel):
    id: str
    field_name: str
    sku_id: str | None
    comment: str

    class Config:
        from_attributes = True


class BlockingHistory(BaseModel):
    blocking_reason: BlockingReasonOut | None = None
    field_reports: list[FieldReportOut] = Field(default_factory=list)


class ProductModerationCard(BaseModel):
    id: str
    product_id: str
    seller_id: str
    status: str
    queue_priority: int
    total_active_quantity: int
    json_before: dict | None
    json_after: dict
    blocking_reason_id: str | None
    moderator_id: str | None
    moderator_comment: str | None
    date_created: datetime
    date_updated: datetime
    date_moderation: datetime | None
    blocking_history: BlockingHistory | None = None

    class Config:
        from_attributes = True

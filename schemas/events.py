from datetime import datetime
from enum import Enum
from uuid import UUID
from pydantic import BaseModel


class ProductEventType(str, Enum):
    CREATED = "CREATED"
    EDITED = "EDITED"
    DELETED = "DELETED"


class ProductEventIn(BaseModel):
    idempotency_key: UUID
    product_id: UUID
    seller_id: UUID
    event: ProductEventType
    date: datetime


class EventProcessedResponse(BaseModel):
    status: str

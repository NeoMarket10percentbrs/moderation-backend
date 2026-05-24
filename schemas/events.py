from datetime import datetime
from enum import Enum
from uuid import UUID
from pydantic import BaseModel


class B2BEventType(str, Enum):
    PRODUCT_CREATED = "PRODUCT_CREATED"
    PRODUCT_EDITED = "PRODUCT_EDITED"
    PRODUCT_DELETED = "PRODUCT_DELETED"


class EventProductCreated(BaseModel):
    product_id: UUID
    seller_id: UUID
    category_id: UUID | None = None
    queue_priority: int | None = 3
    json_after: dict


class EventProductEdited(BaseModel):
    product_id: UUID
    seller_id: UUID
    category_id: UUID | None = None
    queue_priority: int | None = 3
    json_before: dict
    json_after: dict


class EventProductDeleted(BaseModel):
    product_id: UUID


class IncomingB2BEvent(BaseModel):
    event_type: B2BEventType
    idempotency_key: UUID
    occurred_at: datetime
    payload: EventProductCreated | EventProductEdited | EventProductDeleted

from datetime import datetime
from enum import Enum
from uuid import UUID
from pydantic import BaseModel, Field
from schemas.blocking_reason import BlockingReasonResponse


class TicketKind(str, Enum):
    CREATE = "CREATE"
    EDIT = "EDIT"


class TicketStatus(str, Enum):
    PENDING = "PENDING"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    BLOCKED = "BLOCKED"
    HARD_BLOCKED = "HARD_BLOCKED"


class QueueClaimRequest(BaseModel):
    queue_priority: int | None = Field(default=None, ge=1, le=4)
    category_ids: list[UUID] | None = None


class FieldReportSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class FieldReport(BaseModel):
    field_path: str
    message: str = Field(max_length=1000)
    severity: FieldReportSeverity = FieldReportSeverity.ERROR


class TicketHistoryEntry(BaseModel):
    at: datetime
    action: str
    moderator_id: UUID | None = None
    comment: str | None = None


class TicketResponse(BaseModel):
    id: UUID
    product_id: UUID
    seller_id: UUID
    category_id: UUID | None = None
    kind: TicketKind
    status: TicketStatus
    queue_priority: int = Field(ge=1, le=4)
    assigned_moderator_id: UUID | None = None
    claimed_at: datetime | None = None
    claim_expires_at: datetime | None = None
    decision_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class TicketDetailResponse(TicketResponse):
    json_before: dict | None = None
    json_after: dict
    diff: list[dict] | None = None
    field_reports: list[FieldReport] = Field(default_factory=list)
    blocking_reasons: list[BlockingReasonResponse] = Field(default_factory=list)
    decision_comment: str | None = None
    history: list[TicketHistoryEntry] = Field(default_factory=list)


class BlockDecisionRequest(BaseModel):
    blocking_reason_ids: list[UUID] = Field(min_length=1)
    comment: str | None = Field(default=None, max_length=2000)
    field_reports: list[FieldReport] = Field(default_factory=list)


class ApproveRequest(BaseModel):
    comment: str | None = Field(default=None, max_length=2000)


class PaginatedTickets(BaseModel):
    items: list[TicketResponse]
    total_count: int
    limit: int
    offset: int


class GetNextRequest(BaseModel):
    queue_id: UUID | None = None


class ProductModerationCard(TicketDetailResponse):
    pass

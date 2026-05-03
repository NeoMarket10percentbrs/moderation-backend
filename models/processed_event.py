import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from uuid import uuid4
from core.database import Base


class ProcessedEvent(Base):
    __tablename__ = "processed_events"

    id: Mapped[sa.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    sender_service: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    idempotency_key: Mapped[sa.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    response_cached: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    processed_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "sender_service",
            "idempotency_key",
            name="uq_processed_events_sender_idempotency",
        ),
    )

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from uuid import uuid4
from core.database import Base


class ProductModeration(Base):
    __tablename__ = "product_moderation"

    id: Mapped[sa.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    product_id: Mapped[sa.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, unique=True, index=True
    )
    seller_id: Mapped[sa.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(20), nullable=False, default="PENDING")
    queue_priority: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    total_active_quantity: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )
    json_before: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    json_after: Mapped[dict] = mapped_column(JSONB, nullable=False)
    blocking_reason_id: Mapped[sa.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("blocking_reasons.id"), nullable=True
    )
    moderator_id: Mapped[sa.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    moderator_comment: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    date_created: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    date_updated: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    date_moderation: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        sa.CheckConstraint(
            "queue_priority BETWEEN 1 AND 4",
            name="ck_product_moderation_queue_priority",
        ),
        sa.Index(
            "ix_product_moderation_status_priority_updated",
            "status",
            "queue_priority",
            "date_updated",
        ),
    )

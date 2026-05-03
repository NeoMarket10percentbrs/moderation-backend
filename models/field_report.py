import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid import uuid4
from core.database import Base


class FieldReport(Base):
    __tablename__ = "field_reports"

    id: Mapped[sa.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    product_moderation_id: Mapped[sa.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("product_moderation.id", ondelete="CASCADE"),
        nullable=False,
    )
    field_name: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    sku_id: Mapped[sa.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    comment: Mapped[str] = mapped_column(sa.Text, nullable=False)

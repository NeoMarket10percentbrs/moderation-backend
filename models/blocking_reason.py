import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid import uuid4
from core.database import Base


class BlockingReason(Base):
    __tablename__ = "blocking_reasons"

    id: Mapped[sa.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    hard_block: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )

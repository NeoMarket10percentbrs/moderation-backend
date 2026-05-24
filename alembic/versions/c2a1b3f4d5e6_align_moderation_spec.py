"""align moderation spec

Revision ID: c2a1b3f4d5e6
Revises: 754929e2408c
Create Date: 2026-05-24 12:00:00.000000

"""
from typing import Sequence, Union
import uuid
import re
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c2a1b3f4d5e6"
down_revision: Union[str, Sequence[str], None] = "754929e2408c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _base26(value: int) -> str:
    if value <= 0:
        return "A"
    letters = []
    while value > 0:
        value, rem = divmod(value, 26)
        letters.append(chr(ord("A") + rem))
    return "".join(reversed(letters))


def upgrade() -> None:
    # Moderators
    op.add_column(
        "moderators",
        sa.Column("role", sa.String(length=20), server_default=sa.text("'MODERATOR'"), nullable=False),
    )
    op.add_column(
        "moderators",
        sa.Column(
            "category_specializations",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "moderators",
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Blocking reasons
    op.add_column("blocking_reasons", sa.Column("code", sa.String(length=64), nullable=True))
    op.add_column("blocking_reasons", sa.Column("description", sa.Text(), nullable=True))
    op.add_column(
        "blocking_reasons",
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )

    # Tickets (product_moderation table)
    op.add_column("product_moderation", sa.Column("category_id", postgresql.UUID(), nullable=True))
    op.add_column(
        "product_moderation",
        sa.Column("kind", sa.String(length=10), server_default=sa.text("'CREATE'"), nullable=False),
    )
    op.add_column("product_moderation", sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "product_moderation",
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Field reports
    op.add_column(
        "field_reports",
        sa.Column("severity", sa.String(length=10), server_default=sa.text("'ERROR'"), nullable=False),
    )
    op.alter_column("field_reports", "field_name", type_=sa.String(length=255))

    # Ticket history
    op.create_table(
        "ticket_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("moderator_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["ticket_id"], ["product_moderation.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ticket_history_ticket_id", "ticket_history", ["ticket_id"], unique=False
    )

    # Ticket blocking reasons
    op.create_table(
        "ticket_blocking_reasons",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["ticket_id"], ["product_moderation.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reason_id"], ["blocking_reasons.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticket_id", "reason_id", name="uq_ticket_reason"),
    )
    op.create_index(
        "ix_ticket_blocking_reasons_ticket_id",
        "ticket_blocking_reasons",
        ["ticket_id"],
        unique=False,
    )
    op.create_index(
        "ix_ticket_blocking_reasons_reason_id",
        "ticket_blocking_reasons",
        ["reason_id"],
        unique=False,
    )

    bind = op.get_bind()

    # Backfill moderator roles
    bind.execute(
        sa.text(
            "UPDATE moderators SET role = CASE WHEN is_admin THEN 'ADMIN' ELSE 'MODERATOR' END"
        )
    )

    # Backfill ticket kind
    bind.execute(
        sa.text(
            "UPDATE product_moderation SET kind = CASE WHEN json_before IS NULL THEN 'CREATE' ELSE 'EDIT' END"
        )
    )

    # Normalize statuses
    bind.execute(
        sa.text(
            """
            UPDATE product_moderation
            SET status = CASE
                WHEN status = 'MODERATED' THEN 'APPROVED'
                WHEN status = 'CREATED' THEN 'PENDING'
                WHEN status = 'ON_MODERATION' THEN 'IN_REVIEW'
                ELSE status
            END
            """
        )
    )

    # Backfill blocking reason codes
    result = bind.execute(sa.text("SELECT id, title FROM blocking_reasons"))
    rows = result.fetchall()
    for reason_id, title in rows:
        base = _base26(int(uuid.UUID(str(reason_id))))
        code = f"LEGACY_{base}"[:64]
        bind.execute(
            sa.text("UPDATE blocking_reasons SET code = :code WHERE id = :id"),
            {"code": code, "id": reason_id},
        )

    op.alter_column("blocking_reasons", "code", nullable=False)

    # Backfill ticket blocking reasons from legacy column
    ticket_result = bind.execute(
        sa.text(
            "SELECT id, blocking_reason_id FROM product_moderation WHERE blocking_reason_id IS NOT NULL"
        )
    )
    for ticket_id, reason_id in ticket_result.fetchall():
        bind.execute(
            sa.text(
                "INSERT INTO ticket_blocking_reasons (id, ticket_id, reason_id) VALUES (:id, :ticket_id, :reason_id)"
            ),
            {
                "id": str(uuid.uuid4()),
                "ticket_id": ticket_id,
                "reason_id": reason_id,
            },
        )


def downgrade() -> None:
    op.drop_index("ix_ticket_blocking_reasons_reason_id", table_name="ticket_blocking_reasons")
    op.drop_index("ix_ticket_blocking_reasons_ticket_id", table_name="ticket_blocking_reasons")
    op.drop_table("ticket_blocking_reasons")

    op.drop_index("ix_ticket_history_ticket_id", table_name="ticket_history")
    op.drop_table("ticket_history")

    op.drop_column("field_reports", "severity")
    op.alter_column("field_reports", "field_name", type_=sa.String(length=20))

    op.drop_column("product_moderation", "claim_expires_at")
    op.drop_column("product_moderation", "claimed_at")
    op.drop_column("product_moderation", "kind")
    op.drop_column("product_moderation", "category_id")

    op.drop_column("blocking_reasons", "is_active")
    op.drop_column("blocking_reasons", "description")
    op.drop_column("blocking_reasons", "code")

    op.drop_column("moderators", "last_login_at")
    op.drop_column("moderators", "category_specializations")
    op.drop_column("moderators", "role")

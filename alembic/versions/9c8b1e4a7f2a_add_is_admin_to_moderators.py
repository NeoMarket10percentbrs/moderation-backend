"""add is_admin to moderators

Revision ID: 9c8b1e4a7f2a
Revises: b535ab5db54c
Create Date: 2026-05-04 18:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9c8b1e4a7f2a"
down_revision: Union[str, Sequence[str], None] = "b535ab5db54c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "moderators",
        sa.Column(
            "is_admin",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("moderators", "is_admin")

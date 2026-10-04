"""integration api: balance memo column and idempotency table

Revision ID: 20261004_92
Revises: 20261004_91
Create Date: 2026-10-04
"""

import sqlalchemy as sa
from alembic import op

revision: str = "20261004_92"
down_revision: str | None = "20261004_91"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "balance_transactions",
        sa.Column("memo", sa.String(length=200)),
    )
    op.create_table(
        "integration_idempotencies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("key_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("response_body", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("integration_idempotencies")
    op.drop_column("balance_transactions", "memo")

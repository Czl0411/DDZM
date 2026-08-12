"""Add personal profiles and shared labor settings."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260812_39"
down_revision: str | None = "20260811_38"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "profile_text",
            sa.Text(),
            nullable=False,
            server_default="",
        ),
    )
    op.create_table(
        "profile_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("edit_cost", sa.Integer(), nullable=False),
        sa.Column("shared_labor", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    settings = sa.table(
        "profile_settings",
        sa.column("id", sa.Integer()),
        sa.column("edit_cost", sa.Integer()),
        sa.column("shared_labor", sa.Integer()),
        sa.column("version", sa.Integer()),
    )
    op.bulk_insert(
        settings,
        [{"id": 1, "edit_cost": 10, "shared_labor": 5, "version": 0}],
    )


def downgrade() -> None:
    op.drop_table("profile_settings")
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("profile_text")

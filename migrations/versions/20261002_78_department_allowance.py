"""Add the department allowance system."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20261002_78"
down_revision: str | None = "20261002_77"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("departments", sa.Column("allowance_kind", sa.String(length=32)))
    op.create_table(
        "department_allowances",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("allow_date", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "kind IN ('dept_checkin', 'dept_event', 'dept_game_host', "
            "'dept_game_play', 'dept_submission', 'dept_chat')",
            name="ck_department_allowance_kind",
        ),
    )
    op.create_index(
        "ix_department_allowances_user_date",
        "department_allowances",
        ["user_id", "allow_date"],
    )
    op.create_table(
        "department_game_plays",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("play_date", sa.Date(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "play_date"),
    )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table in ("department_game_plays", "department_allowances"):
        if inspector.has_table(table):
            op.drop_table(table)
    columns = {column["name"] for column in inspector.get_columns("departments")}
    if "allowance_kind" in columns:
        op.drop_column("departments", "allowance_kind")

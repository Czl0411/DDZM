"""Add approval records for department changes."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260807_24"
down_revision: str | None = "20260807_23"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "department_requests",
        sa.Column("id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("number", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("applicant_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "source_department_id",
            sa.Uuid(),
            sa.ForeignKey("departments.id"),
            nullable=False,
        ),
        sa.Column(
            "target_department_id",
            sa.Uuid(),
            sa.ForeignKey("departments.id"),
            nullable=False,
        ),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ux_department_requests_pending_employee",
        "department_requests",
        ["applicant_id"],
        unique=True,
        postgresql_where=sa.text("state = 'pending'"),
        sqlite_where=sa.text("state = 'pending'"),
    )
    op.create_table(
        "department_approvals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "request_id",
            sa.Uuid(),
            sa.ForeignKey("department_requests.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("approver_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("department_approvals")
    op.drop_index(
        "ux_department_requests_pending_employee",
        table_name="department_requests",
    )
    op.drop_table("department_requests")

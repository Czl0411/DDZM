"""discipline fine tables

Revision ID: 20261003_82
Revises: 20261003_81
Create Date: 2026-10-03
"""

import sqlalchemy as sa
from alembic import op

revision: str = "20261003_82"
down_revision: str | None = "20261003_81"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "discipline_fine_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("department_id", sa.Uuid(), nullable=True),
        sa.Column("amount", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("kickback_percent", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("rank_quotas", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("cooldown_minutes", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("target_daily_limit", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "discipline_fine_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("group_chat_id", sa.Uuid(), nullable=False),
        sa.Column("issuer_id", sa.Uuid(), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("kickback", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("via_reply", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["group_chat_id"], ["group_chats.id"]),
        sa.ForeignKeyConstraint(["issuer_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["target_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["revoked_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_discipline_fine_records_created_at",
        "discipline_fine_records",
        ["created_at"],
    )
    # 执法抽成走部门津贴封顶台账：放行 kind='dept_fine'
    with op.batch_alter_table("department_allowances") as batch:
        batch.drop_constraint("ck_department_allowance_kind", type_="check")
        batch.create_check_constraint(
            "ck_department_allowance_kind",
            "kind IN ('dept_checkin', 'dept_event', 'dept_game_host', "
            "'dept_game_play', 'dept_submission', 'dept_chat', 'dept_referral', "
            "'dept_fine')",
        )


def downgrade() -> None:
    with op.batch_alter_table("department_allowances") as batch:
        batch.drop_constraint("ck_department_allowance_kind", type_="check")
        batch.create_check_constraint(
            "ck_department_allowance_kind",
            "kind IN ('dept_checkin', 'dept_event', 'dept_game_host', "
            "'dept_game_play', 'dept_submission', 'dept_chat', 'dept_referral')",
        )
    op.drop_index(
        "ix_discipline_fine_records_created_at", table_name="discipline_fine_records"
    )
    op.drop_table("discipline_fine_records")
    op.drop_table("discipline_fine_settings")

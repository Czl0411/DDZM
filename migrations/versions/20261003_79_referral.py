"""referral records + department allowance kind referral

Revision ID: 79
Revises: 78
Create Date: 2026-10-03
"""

import sqlalchemy as sa
from alembic import op

revision: str = "20261003_79"
down_revision: str | None = "20261002_78"
branch_labels = None
depends_on = None

_KIND_CONSTRAINT = "ck_department_allowance_kind"
_KIND_WITH_REFERRAL = (
    "kind IN ('dept_checkin', 'dept_event', 'dept_game_host', "
    "'dept_game_play', 'dept_submission', 'dept_chat', 'dept_referral')"
)
_KIND_WITHOUT_REFERRAL = (
    "kind IN ('dept_checkin', 'dept_event', 'dept_game_host', "
    "'dept_game_play', 'dept_submission', 'dept_chat')"
)


def upgrade() -> None:
    with op.batch_alter_table("department_allowances") as batch_op:
        batch_op.drop_constraint(_KIND_CONSTRAINT, type_="check")
        batch_op.create_check_constraint(_KIND_CONSTRAINT, _KIND_WITH_REFERRAL)
    op.create_table(
        "referral_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("chatroom_id", sa.String(length=64), nullable=False),
        sa.Column("platform_message_id", sa.String(length=64), nullable=False),
        sa.Column("newcomer_platform_id", sa.String(length=64)),
        sa.Column("newcomer_name", sa.String(length=128), nullable=False),
        sa.Column("inviter_platform_id", sa.String(length=64)),
        sa.Column("inviter_name", sa.String(length=128)),
        sa.Column("inviter_user_id", sa.Uuid()),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column(
            "joined_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.ForeignKeyConstraint(["inviter_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("platform_message_id", name="uq_referral_message"),
        sa.UniqueConstraint("newcomer_platform_id", name="uq_referral_newcomer"),
    )
    op.create_index(
        "ix_referral_records_inviter",
        "referral_records",
        ["inviter_user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_referral_records_inviter", table_name="referral_records")
    op.drop_table("referral_records")
    with op.batch_alter_table("department_allowances") as batch_op:
        batch_op.drop_constraint(_KIND_CONSTRAINT, type_="check")
        batch_op.create_check_constraint(_KIND_CONSTRAINT, _KIND_WITHOUT_REFERRAL)

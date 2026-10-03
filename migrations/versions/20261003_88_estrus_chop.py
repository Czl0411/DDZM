"""estrus chop tables and users gender column

Revision ID: 20261003_88
Revises: 20261003_87
Create Date: 2026-10-03
"""

import sqlalchemy as sa
from alembic import op

revision: str = "20261003_88"
down_revision: str | None = "20261003_87"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("gender", sa.String(length=16), nullable=False,
                  server_default="unknown"),
    )
    op.create_check_constraint(
        "ck_users_gender",
        "users",
        "gender IN ('male', 'female', 'unknown')",
    )
    op.create_table(
        "estrus_states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("group_chat_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("heat", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "chopped_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "total_climaxes", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "today_climaxes", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("last_climax_date", sa.Date()),
        sa.Column(
            "opted_out", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.ForeignKeyConstraint(["group_chat_id"], ["group_chats.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("group_chat_id", "user_id"),
    )
    op.create_table(
        "estrus_chops",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("group_chat_id", sa.Uuid(), nullable=False),
        sa.Column("chopper_user_id", sa.Uuid(), nullable=False),
        sa.Column("target_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "heat_gain", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("coins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "climax_triggered", sa.Boolean(), nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("note", sa.String(length=200)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["group_chat_id"], ["group_chats.id"]),
        sa.ForeignKeyConstraint(["chopper_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["target_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "estrus_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False,
                  server_default=sa.true()),
        sa.Column(
            "climax_threshold", sa.Integer(), nullable=False,
            server_default="100",
        ),
        sa.Column("heat_p0", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("heat_p1", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("heat_p2", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("coin_p0", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("coin_p1", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("coin_p2", sa.Integer(), nullable=False, server_default="20"),
        sa.Column(
            "chop_cooldown_seconds", sa.Integer(), nullable=False,
            server_default="0",
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("estrus_settings")
    op.drop_table("estrus_chops")
    op.drop_table("estrus_states")
    op.drop_constraint("ck_users_gender", "users", type_="check")
    op.drop_column("users", "gender")

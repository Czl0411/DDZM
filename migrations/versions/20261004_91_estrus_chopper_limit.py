"""estrus chopper daily limit and /我的凿 command rename

Revision ID: 20261004_91
Revises: 20261003_90
Create Date: 2026-10-04
"""

import sqlalchemy as sa
from alembic import op

revision: str = "20261004_91"
down_revision: str | None = "20261003_90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 每人每天可凿别人的次数上限（0 = 不限制）
    op.add_column(
        "estrus_settings",
        sa.Column(
            "chopper_daily_limit",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    # /我的发情值 → /我的凿（内容增加凿人次数）
    op.execute(
        "UPDATE command_definitions SET command = '/我的凿', "
        "syntax = '/我的凿', "
        "description = '查看自己的发情值、被凿/凿人与高潮次数' "
        "WHERE command = '/我的发情值'"
    )


def downgrade() -> None:
    op.execute("DELETE FROM command_definitions WHERE command = '/我的凿'")
    op.drop_column("estrus_settings", "chopper_daily_limit")

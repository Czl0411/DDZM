"""estrus popularity board and daily heat reset

Revision ID: 20261003_90
Revises: 20261003_89
Create Date: 2026-10-04
"""

import sqlalchemy as sa
from alembic import op

revision: str = "20261003_90"
down_revision: str | None = "20261003_89"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 发情值每日清零：last_climax_date（只管今日高潮重置）
    # 统一成 last_active_date（heat / 今日高潮一起懒重置）；
    # 今日被凿次数改由 estrus_chops 日志按天统计，无需新列。
    with op.batch_alter_table("estrus_states") as batch:
        batch.add_column(sa.Column("last_active_date", sa.Date()))
        batch.drop_column("last_climax_date")
    # /发情值排名 → /最受欢迎（今日最受欢迎榜）
    op.execute(
        "UPDATE command_definitions SET command = '/最受欢迎', "
        "syntax = '/最受欢迎', "
        "description = '查看今日最受欢迎榜前 5 名（按今日被凿次数）' "
        "WHERE command = '/发情值排名'"
    )


def downgrade() -> None:
    op.execute("DELETE FROM command_definitions WHERE command = '/最受欢迎'")
    with op.batch_alter_table("estrus_states") as batch:
        batch.add_column(sa.Column("last_climax_date", sa.Date()))
        batch.drop_column("last_active_date")

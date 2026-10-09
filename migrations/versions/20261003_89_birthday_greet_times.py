"""birthday greeting announcements three times a day

Revision ID: 20261003_89
Revises: 20261003_88
Create Date: 2026-10-03
"""

import sqlalchemy as sa
from alembic import op

revision: str = "20261003_89"
down_revision: str | None = "20261003_88"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 单一祝福时刻 → 多时刻公告（默认 09:00 / 12:00 / 17:00）
    with op.batch_alter_table("birthday_settings") as batch:
        batch.add_column(
            sa.Column(
                "greet_times",
                sa.JSON(),
                nullable=False,
                server_default='["09:00", "12:00", "17:00"]',
            )
        )
        batch.drop_column("greet_time")
    # 公告幂等：每天每个时刻只公告一次（礼金仍由 birthday_greetings 一年一次）
    op.create_table(
        "birthday_greet_announcements",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("announce_date", sa.Date(), nullable=False),
        sa.Column("slot", sa.String(length=5), nullable=False),
        sa.Column(
            "announced_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.UniqueConstraint("announce_date", "slot"),
    )


def downgrade() -> None:
    op.drop_table("birthday_greet_announcements")
    with op.batch_alter_table("birthday_settings") as batch:
        batch.add_column(
            sa.Column(
                "greet_time",
                sa.String(length=5),
                nullable=False,
                server_default="09:00",
            )
        )
        batch.drop_column("greet_times")

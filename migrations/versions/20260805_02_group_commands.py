"""Add basic group gameplay records."""

from collections.abc import Sequence
from datetime import datetime
from zoneinfo import ZoneInfo

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260805_02"
down_revision: str | None = "20260804_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True)
    now = datetime.now(ZoneInfo("Asia/Shanghai"))

    op.create_table(
        "command_definitions",
        sa.Column("command", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("command"),
    )
    op.bulk_insert(
        sa.table(
            "command_definitions",
            sa.column("command", sa.String()),
            sa.column("description", sa.Text()),
            sa.column("enabled", sa.Boolean()),
            sa.column("created_at", sa.DateTime(timezone=True)),
        ),
        [
            {"command": "/入职", "description": "登记群成员为摸鱼公司员工", "enabled": True, "created_at": now},
            {"command": "/我的物品", "description": "查看自己持有的物品", "enabled": True, "created_at": now},
            {"command": "/打卡", "description": "每日领取 5 摸鱼币", "enabled": True, "created_at": now},
            {"command": "/余额", "description": "查看当前摸鱼币余额", "enabled": True, "created_at": now},
            {"command": "/商店", "description": "查看当前上架物品", "enabled": True, "created_at": now},
        ],
    )

    op.create_table(
        "users",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("platform_id", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=64), nullable=False),
        sa.Column("balance", sa.Integer(), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("platform_id"),
    )
    op.create_table(
        "items",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("stock", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "daily_checkins",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("user_id", uuid_type, nullable=False),
        sa.Column("checkin_date", sa.Date(), nullable=False),
        sa.Column("checked_in_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "checkin_date"),
    )
    op.create_table(
        "user_items",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("user_id", uuid_type, nullable=False),
        sa.Column("item_id", uuid_type, nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "item_id"),
    )


def downgrade() -> None:
    op.drop_table("user_items")
    op.drop_table("daily_checkins")
    op.drop_table("items")
    op.drop_table("users")
    op.drop_table("command_definitions")

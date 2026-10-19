"""Make estrus heat tier values configurable and raise defaults.

- 新增 heat_value_0/1/2 三列：发情值三档概率命中后的实际数值（原硬编码 0/1/2，
  新默认 0/5/10）。
- g_spot_heat_bonus 旧默认 10 调整为 20：仅把仍等于 10 的行升到 20，
  保留管理员自定义值。
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20261016_105"
down_revision: str | None = "20261013_106"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


HEAT_VALUE_COLUMNS = (
    sa.Column("heat_value_0", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("heat_value_1", sa.Integer(), nullable=False, server_default="5"),
    sa.Column("heat_value_2", sa.Integer(), nullable=False, server_default="10"),
)


def upgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table("estrus_settings"):
        return
    existing = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("estrus_settings")
    }
    for column in HEAT_VALUE_COLUMNS:
        if column.name not in existing:
            op.add_column("estrus_settings", column)
    op.execute(
        "UPDATE estrus_settings SET g_spot_heat_bonus = 20 "
        "WHERE g_spot_heat_bonus = 10"
    )


def downgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table("estrus_settings"):
        return
    existing = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("estrus_settings")
    }
    for column in reversed(HEAT_VALUE_COLUMNS):
        if column.name in existing:
            op.drop_column("estrus_settings", column.name)

"""Rename the male and female charm honor titles."""

from collections.abc import Sequence
from copy import deepcopy

from alembic import op
import sqlalchemy as sa


revision: str = "20261020_108"
down_revision: str | None = "20261020_107"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


NEW_NAMES = {
    "charm_m": "公司最靓的仔",
    "charm_f": "公司最正的妞",
}
OLD_NAMES = {
    "charm_m": "最有魅力帅哥",
    "charm_f": "最有魅力美女",
}


def _renamed_snapshot(snapshot: dict, names: dict[str, str]) -> dict:
    result = deepcopy(snapshot)
    collections = [result.get("rules"), result.get("entries")]
    configuration = result.get("configuration")
    if isinstance(configuration, dict):
        collections.append(configuration.get("rules"))
    for items in collections:
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict) and item.get("key") in names:
                item["name"] = names[item["key"]]
    return result


def _rename(names: dict[str, str]) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("honor_awards"):
        awards = sa.table(
            "honor_awards",
            sa.column("title_key", sa.String()),
            sa.column("title_name", sa.String()),
        )
        for key, name in names.items():
            bind.execute(
                awards.update()
                .where(awards.c.title_key == key)
                .values(title_name=name)
            )
    for table_name in ("honor_configs", "honor_periods"):
        if not inspector.has_table(table_name):
            continue
        table = sa.table(
            table_name,
            sa.column("id"),
            sa.column("snapshot", sa.JSON()),
        )
        for row_id, snapshot in bind.execute(
            sa.select(table.c.id, table.c.snapshot)
        ):
            bind.execute(
                table.update()
                .where(table.c.id == row_id)
                .values(snapshot=_renamed_snapshot(snapshot, names))
            )


def upgrade() -> None:
    _rename(NEW_NAMES)


def downgrade() -> None:
    _rename(OLD_NAMES)

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("previous_bonus, expected_bonus", [(10, 20), (37, 37)])
def test_heat_values_migration_upgrades_without_equipment(
    tmp_path, monkeypatch, previous_bonus, expected_bonus
):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'estrus-heat.db'}"
    monkeypatch.setenv("DZMM_DATABASE_URL", database_url)
    engine = sa.create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(sa.text(
                "CREATE TABLE estrus_settings (id INTEGER PRIMARY KEY, "
                "g_spot_heat_bonus INTEGER NOT NULL, heat_p0 INTEGER NOT NULL)"
            ))
            connection.execute(sa.text(
                "INSERT INTO estrus_settings VALUES (1, :bonus, 42)"
            ), {"bonus": previous_bonus})

        config = Config(str(ROOT / "alembic.ini"))
        command.stamp(config, "20261013_106")
        command.upgrade(config, "head")

        with engine.connect() as connection:
            row = connection.execute(sa.text(
                "SELECT * FROM estrus_settings"
            )).mappings().one()
            assert (row["heat_value_0"], row["heat_value_1"], row["heat_value_2"]) == (0, 5, 10)
            assert row["g_spot_heat_bonus"] == expected_bonus
            assert row["heat_p0"] == 42
        assert not sa.inspect(engine).has_table("equipment_items")

        command.downgrade(config, "20261013_106")
        assert {column["name"] for column in sa.inspect(engine).get_columns("estrus_settings")} == {
            "id", "g_spot_heat_bonus", "heat_p0"
        }

        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert connection.scalar(sa.text(
                "SELECT g_spot_heat_bonus FROM estrus_settings"
            )) == expected_bonus
    finally:
        engine.dispose()


def test_heat_values_migration_is_the_only_head_after_main():
    script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))

    assert script.get_heads() == ["20261016_105"]
    assert script.get_revision("head").down_revision == "20261013_106"

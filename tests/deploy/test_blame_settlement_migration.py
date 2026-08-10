import importlib.util
from pathlib import Path

import sqlalchemy as sa


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    ROOT / "migrations/versions/20260810_33_blame_settlement_notices.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("blame_settlement_migration", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_blame_settlement_migration_upgrades_defaults_and_preserves_custom_copy():
    migration = _load_migration()
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata = sa.MetaData()
    templates = sa.Table(
        "command_reply_templates",
        metadata,
        sa.Column("command", sa.String(), nullable=False),
        sa.Column("scenario", sa.String(), nullable=False),
        sa.Column("template", sa.Text(), nullable=False),
    )
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(
            templates.insert(),
            [
                {"command": command, "scenario": scenario, "template": old}
                for command, scenario, old, _ in migration.TEMPLATE_UPDATES
            ],
        )
        migration.apply_template_updates(connection, migration.TEMPLATE_UPDATES)
        upgraded = list(
            connection.execute(
                sa.select(templates.c.command, templates.c.scenario, templates.c.template)
                .order_by(templates.c.command, templates.c.scenario)
            )
        )
        expected = sorted(
            (command, scenario, new)
            for command, scenario, _, new in migration.TEMPLATE_UPDATES
        )
        assert upgraded == expected

        connection.execute(templates.delete())
        customized = [
            (command, scenario, f"管理员自定义：{scenario}")
            for command, scenario, _, _ in migration.TEMPLATE_UPDATES
        ]
        connection.execute(
            templates.insert(),
            [
                {"command": command, "scenario": scenario, "template": template}
                for command, scenario, template in customized
            ],
        )
        migration.apply_template_updates(connection, migration.TEMPLATE_UPDATES)
        preserved = list(
            connection.execute(
                sa.select(templates.c.command, templates.c.scenario, templates.c.template)
                .order_by(templates.c.command, templates.c.scenario)
            )
        )

    assert preserved == sorted(customized)

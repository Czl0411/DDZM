import os
import subprocess
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


ROOT = Path(__file__).resolve().parents[2]


def test_unified_club_is_the_only_migration_head():
    scripts = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    assert scripts.get_heads() == ["20261021_113"]
    assert scripts.get_revision("20261021_113").down_revision == "20261020_112"


def test_unified_club_generates_postgresql_upgrade_sql():
    environment = {
        **os.environ,
        "DZMM_DATABASE_URL": "postgresql+psycopg://user:pass@localhost/database",
    }
    result = subprocess.run(
        [
            str(ROOT / ".venv/bin/alembic"),
            "upgrade",
            "20261020_112:20261021_113",
            "--sql",
        ],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=True,
    )
    assert "CREATE TABLE club_players" in result.stdout
    assert "REFERENCES club_players" in result.stdout
    assert "CREATE TABLE club_task_claims" in result.stdout
    assert "ALTER TABLE doudizhu_rooms ALTER COLUMN group_chat_id DROP NOT NULL" in result.stdout

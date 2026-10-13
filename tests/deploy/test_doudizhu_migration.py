from pathlib import Path
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def test_doudizhu_migration_preserves_existing_tables(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{tmp_path / 'migration.db'}"
    monkeypatch.setenv('DZMM_DATABASE_URL', url)
    engine = create_engine(url)
    with engine.begin() as c:
        c.execute(text('CREATE TABLE keep_existing (value INTEGER)'))
        c.execute(text('INSERT INTO keep_existing VALUES (42)'))
    config = Config(str(Path(__file__).resolve().parents[2] / 'alembic.ini'))
    command.stamp(config, '20261013_108')
    command.upgrade(config, 'head')
    assert {'doudizhu_rooms', 'doudizhu_rounds', 'doudizhu_requests', 'doudizhu_messages'} <= set(inspect(engine).get_table_names())
    command.downgrade(config, '20261013_108')
    assert 'doudizhu_rooms' not in inspect(engine).get_table_names()
    with engine.connect() as c:
        assert c.execute(text('SELECT value FROM keep_existing')).scalar_one() == 42

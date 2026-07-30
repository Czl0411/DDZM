import sqlite3
from pathlib import Path


class SQLiteSeenMessageStore:
    def __init__(self, database_path: Path):
        self._database_path = database_path
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._database_path) as connection:
            connection.execute(
                "create table if not exists seen_messages (message_id text primary key)"
            )

    def is_seen(self, message_id: str) -> bool:
        with sqlite3.connect(self._database_path) as connection:
            return connection.execute(
                "select 1 from seen_messages where message_id = ?", (message_id,)
            ).fetchone() is not None

    def mark_seen(self, message_id: str) -> None:
        with sqlite3.connect(self._database_path) as connection:
            connection.execute(
                "insert or ignore into seen_messages (message_id) values (?)", (message_id,)
            )

import sqlite3
import time
from pathlib import Path


class SQLiteSeenMessageStore:
    def __init__(self, database_path: Path, claim_ttl_seconds: int = 300):
        self._database_path = database_path
        self._claim_ttl_seconds = claim_ttl_seconds
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._database_path) as connection:
            connection.execute(
                "create table if not exists seen_messages (message_id text primary key)"
            )
            connection.execute(
                "create table if not exists message_claims (message_id text primary key, claimed_at integer not null)"
            )

    def claim(self, message_id: str) -> bool:
        now = int(time.time())
        with sqlite3.connect(self._database_path) as connection:
            connection.execute("begin immediate")
            if connection.execute(
                "select 1 from seen_messages where message_id = ?", (message_id,)
            ).fetchone():
                return False
            connection.execute(
                "delete from message_claims where claimed_at < ?", (now - self._claim_ttl_seconds,)
            )
            return connection.execute(
                "insert or ignore into message_claims (message_id, claimed_at) values (?, ?)",
                (message_id, now),
            ).rowcount == 1

    def mark_seen(self, message_id: str) -> None:
        with sqlite3.connect(self._database_path) as connection:
            connection.execute(
                "insert or ignore into seen_messages (message_id) values (?)", (message_id,)
            )
            connection.execute("delete from message_claims where message_id = ?", (message_id,))

    def release_claim(self, message_id: str) -> None:
        with sqlite3.connect(self._database_path) as connection:
            connection.execute("delete from message_claims where message_id = ?", (message_id,))

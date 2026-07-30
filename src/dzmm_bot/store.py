import sqlite3
import time
import secrets
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
                "create table if not exists message_claims (message_id text primary key, claim_token text, claimed_at integer not null)"
            )
            columns = {row[1] for row in connection.execute("pragma table_info(message_claims)")}
            if "claim_token" not in columns:
                connection.execute("alter table message_claims add column claim_token text")

    def claim(self, message_id: str) -> str | None:
        now = int(time.time())
        claim_token = secrets.token_urlsafe(16)
        with sqlite3.connect(self._database_path) as connection:
            connection.execute("begin immediate")
            if connection.execute(
                "select 1 from seen_messages where message_id = ?", (message_id,)
            ).fetchone():
                return False
            connection.execute(
                "delete from message_claims where claimed_at < ?", (now - self._claim_ttl_seconds,)
            )
            if connection.execute(
                "insert or ignore into message_claims (message_id, claim_token, claimed_at) values (?, ?, ?)",
                (message_id, claim_token, now),
            ).rowcount == 1:
                return claim_token
            return None

    def mark_seen(self, message_id: str, claim_token: str) -> bool:
        with sqlite3.connect(self._database_path) as connection:
            connection.execute("begin immediate")
            if connection.execute(
                "delete from message_claims where message_id = ? and claim_token = ?",
                (message_id, claim_token),
            ).rowcount != 1:
                return False
            connection.execute(
                "insert or ignore into seen_messages (message_id) values (?)", (message_id,)
            )
            return True

    def release_claim(self, message_id: str, claim_token: str) -> None:
        with sqlite3.connect(self._database_path) as connection:
            connection.execute(
                "delete from message_claims where message_id = ? and claim_token = ?",
                (message_id, claim_token),
            )

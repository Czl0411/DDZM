from base64 import urlsafe_b64decode, urlsafe_b64encode
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import scrypt, sha256
from hmac import compare_digest
from secrets import token_bytes, token_urlsafe
from typing import TypeVar
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from dzmm_bot.core.schema import (
    AdminAccountRecord,
    AdminConfigRevisionRecord,
    AdminIdempotencyRecord,
    AdminSessionRecord,
    MistrealmChannelMessageRecord,
    MistrealmPlayerRecord,
    MistrealmRoomRecord,
)


_SESSION_TTL = timedelta(hours=12)
_IDEMPOTENCY_TTL = timedelta(hours=1)


@dataclass(frozen=True)
class AdminIdentity:
    account_id: UUID | None
    username: str
    role: str


class IdempotencyInProgressError(RuntimeError):
    pass


class ConfigVersionConflictError(RuntimeError):
    def __init__(self, current_version: int) -> None:
        self.current_version = current_version
        super().__init__("configuration was updated by another administrator")


T = TypeVar("T")


class AdminRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def create_account(self, username: str, password: str) -> AdminAccountRecord:
        with self._session_factory.begin() as session:
            record = AdminAccountRecord(
                username=username,
                password_hash=_hash_password(password),
            )
            session.add(record)
            session.flush()
            return record

    def list_accounts(self) -> list[AdminAccountRecord]:
        with self._session_factory.begin() as session:
            return list(
                session.scalars(
                    select(AdminAccountRecord).order_by(AdminAccountRecord.created_at)
                )
            )

    def authenticate(self, username: str, password: str) -> AdminAccountRecord | None:
        with self._session_factory.begin() as session:
            record = session.scalar(
                select(AdminAccountRecord).where(AdminAccountRecord.username == username)
            )
            if record is None or not record.active:
                return None
            return record if _password_matches(record.password_hash, password) else None

    def create_session(self, account_id: UUID, now: datetime) -> str:
        token = token_urlsafe(32)
        with self._session_factory.begin() as session:
            session.add(
                AdminSessionRecord(
                    account_id=account_id,
                    token_hash=_digest(token),
                    expires_at=now + _SESSION_TTL,
                )
            )
        return token

    def resolve_session(self, token: str, now: datetime) -> AdminIdentity | None:
        with self._session_factory.begin() as session:
            record = session.execute(
                select(AdminSessionRecord, AdminAccountRecord)
                .join(AdminAccountRecord, AdminSessionRecord.account_id == AdminAccountRecord.id)
                .where(AdminSessionRecord.token_hash == _digest(token))
            ).first()
            if record is None:
                return None
            session_record, account = record
            if not account.active or session_record.expires_at <= now:
                session.delete(session_record)
                return None
            return AdminIdentity(account.id, account.username, "admin")

    def revoke_session(self, token: str) -> None:
        with self._session_factory.begin() as session:
            session.execute(
                delete(AdminSessionRecord).where(
                    AdminSessionRecord.token_hash == _digest(token)
                )
            )

    def set_account_active(self, account_id: UUID, active: bool) -> AdminAccountRecord | None:
        with self._session_factory.begin() as session:
            record = session.get(AdminAccountRecord, account_id)
            if record is None:
                return None
            record.active = active
            if not active:
                session.execute(
                    delete(AdminSessionRecord).where(
                        AdminSessionRecord.account_id == account_id
                    )
                )
            session.flush()
            return record

    def reset_password(self, account_id: UUID, password: str) -> AdminAccountRecord | None:
        with self._session_factory.begin() as session:
            record = session.get(AdminAccountRecord, account_id)
            if record is None:
                return None
            record.password_hash = _hash_password(password)
            session.execute(
                delete(AdminSessionRecord).where(AdminSessionRecord.account_id == account_id)
            )
            session.flush()
            return record

    def delete_account(self, account_id: UUID) -> bool:
        with self._session_factory.begin() as session:
            record = session.get(AdminAccountRecord, account_id)
            if record is None:
                return False
            session.execute(
                delete(AdminSessionRecord).where(AdminSessionRecord.account_id == account_id)
            )
            session.delete(record)
            return True

    def reserve_idempotency_key(
        self, actor_key: str, key: str, now: datetime
    ) -> tuple[int, dict] | None:
        key_hash = _digest(key)
        try:
            with self._session_factory.begin() as session:
                session.execute(
                    delete(AdminIdempotencyRecord).where(
                        AdminIdempotencyRecord.expires_at <= now
                    )
                )
                record = session.scalar(
                    select(AdminIdempotencyRecord).where(
                        AdminIdempotencyRecord.actor_key == actor_key,
                        AdminIdempotencyRecord.key_hash == key_hash,
                    )
                )
                if record is not None:
                    return _idempotency_result(record)
                session.add(
                    AdminIdempotencyRecord(
                        actor_key=actor_key,
                        key_hash=key_hash,
                        expires_at=now + _IDEMPOTENCY_TTL,
                    )
                )
                session.flush()
                return None
        except IntegrityError:
            with self._session_factory.begin() as session:
                record = session.scalar(
                    select(AdminIdempotencyRecord).where(
                        AdminIdempotencyRecord.actor_key == actor_key,
                        AdminIdempotencyRecord.key_hash == key_hash,
                    )
                )
                if record is None:
                    raise
                return _idempotency_result(record)

    def complete_idempotency_key(
        self,
        actor_key: str,
        key: str,
        status_code: int,
        response_body: dict,
        now: datetime,
    ) -> None:
        with self._session_factory.begin() as session:
            record = session.scalar(
                select(AdminIdempotencyRecord).where(
                    AdminIdempotencyRecord.actor_key == actor_key,
                    AdminIdempotencyRecord.key_hash == _digest(key),
                )
            )
            if record is None:
                raise RuntimeError("idempotency reservation disappeared")
            record.status_code = status_code
            record.response_body = response_body
            record.expires_at = now + _IDEMPOTENCY_TTL

    def release_idempotency_key(self, actor_key: str, key: str) -> None:
        with self._session_factory.begin() as session:
            session.execute(
                delete(AdminIdempotencyRecord).where(
                    AdminIdempotencyRecord.actor_key == actor_key,
                    AdminIdempotencyRecord.key_hash == _digest(key),
                    AdminIdempotencyRecord.status_code.is_(None),
                )
            )

    def config_version(self) -> int:
        with self._session_factory.begin() as session:
            record = session.get(AdminConfigRevisionRecord, 1)
            if record is None:
                record = AdminConfigRevisionRecord(id=1, version=0)
                session.add(record)
                session.flush()
            return record.version

    def update_configuration(
        self, expected_version: int, operation: Callable[[], T]
    ) -> tuple[T, int]:
        with self._session_factory.begin() as session:
            record = session.get(AdminConfigRevisionRecord, 1, with_for_update=True)
            if record is None:
                record = AdminConfigRevisionRecord(id=1, version=0)
                session.add(record)
                session.flush()
            if record.version != expected_version:
                raise ConfigVersionConflictError(record.version)
            result = operation()
            record.version += 1
            session.flush()
            return result, record.version

    def mistrealm_channel_overview(self, limit: int = 100) -> dict:
        with self._session_factory.begin() as session:
            messages = list(
                session.scalars(
                    select(MistrealmChannelMessageRecord)
                    .order_by(
                        MistrealmChannelMessageRecord.created_at.desc(),
                        MistrealmChannelMessageRecord.id.desc(),
                    )
                    .limit(limit)
                )
            )
            items = []
            for message in messages:
                player = session.get(MistrealmPlayerRecord, message.player_id)
                room = (
                    session.get(MistrealmRoomRecord, message.room_id)
                    if message.room_id
                    else None
                )
                items.append(
                    {
                        "id": str(message.id),
                        "kind": message.kind,
                        "text": message.text,
                        "created_at": message.created_at.isoformat(),
                        "deleted": message.deleted_at is not None,
                        "player": {
                            "id": str(player.id),
                            "uid": player.platform_uid,
                            "name": player.name,
                            "muted_until": (
                                player.channel_muted_until.isoformat()
                                if player.channel_muted_until
                                else None
                            ),
                        },
                        "room_status": room.phase if room else None,
                    }
                )
            return {"items": items}

    def delete_mistrealm_channel_message(self, message_id: UUID, now: datetime) -> bool:
        with self._session_factory.begin() as session:
            message = session.get(MistrealmChannelMessageRecord, message_id)
            if message is None:
                return False
            message.deleted_at = now
            return True

    def mute_mistrealm_channel_player(
        self, player_id: UUID, minutes: int, now: datetime
    ) -> dict | None:
        with self._session_factory.begin() as session:
            player = session.get(MistrealmPlayerRecord, player_id)
            if player is None:
                return None
            player.channel_muted_until = (
                None if minutes == 0 else now + timedelta(minutes=minutes)
            )
            return {
                "id": str(player.id),
                "name": player.name,
                "muted_until": (
                    player.channel_muted_until.isoformat()
                    if player.channel_muted_until
                    else None
                ),
            }


def _hash_password(password: str) -> str:
    salt = token_bytes(16)
    digest = scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return "scrypt$%s$%s" % (_encode(salt), _encode(digest))


def _password_matches(stored: str, password: str) -> bool:
    try:
        algorithm, encoded_salt, encoded_digest = stored.split("$", 2)
        if algorithm != "scrypt":
            return False
        digest = scrypt(
            password.encode(), salt=_decode(encoded_salt), n=2**14, r=8, p=1
        )
        return compare_digest(digest, _decode(encoded_digest))
    except ValueError:
        return False


def _digest(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def _idempotency_result(record: AdminIdempotencyRecord) -> tuple[int, dict] | None:
    if record.status_code is None or record.response_body is None:
        raise IdempotencyInProgressError("request is already in progress")
    return record.status_code, record.response_body


def _encode(value: bytes) -> str:
    return urlsafe_b64encode(value).decode().rstrip("=")


def _decode(value: str) -> bytes:
    return urlsafe_b64decode(value + "=" * (-len(value) % 4))

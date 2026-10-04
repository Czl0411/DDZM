"""集成接口 /internal/integration/*：名字匹配 + 摸鱼币查/发/扣。"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from dzmm_bot.core.schema import (
    Base,
    BalanceTransactionRecord,
    UserRecord,
)


BEIJING = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 10, 4, 12, 0, tzinfo=BEIJING)


@dataclass
class AppContext:
    client: TestClient
    repository: object
    session_factory: object


@pytest.fixture
def app_context():
    from dzmm_bot.core.app import create_app
    from dzmm_bot.core.repository import CoreRepository
    from dzmm_bot.core.schema import Base as SchemaBase

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SchemaBase.metadata.create_all(engine)
    session_factory = sessionmaker(engine, expire_on_commit=False)
    repository = CoreRepository(session_factory)
    repository.list_ranks()
    app = create_app(repository, "test-core-token", clock=lambda: NOW)
    return AppContext(TestClient(app), repository, session_factory)


@pytest.fixture
def client(app_context):
    return app_context.client


@pytest.fixture
def headers():
    return {"X-Core-Token": "test-core-token"}


def _add_user(app_context, platform_id, display_name, number, *, nickname=None, balance=0):
    with app_context.session_factory.begin() as session:
        session.add(
            UserRecord(
                platform_id=platform_id,
                display_name=display_name,
                platform_nickname=nickname,
                employee_number=number,
                balance=balance,
                joined_at=NOW,
            )
        )


def _balance(app_context, platform_id):
    with app_context.session_factory() as session:
        return session.scalar(
            select(UserRecord.balance).where(
                UserRecord.platform_id == platform_id
            )
        )


# ---------------------------------------------------------------- 匹配

def test_match_by_display_name(client, headers, app_context):
    _add_user(app_context, "plat-1", "小明", 1, nickname="xiaoming")
    _add_user(app_context, "plat-2", "小红", 2)

    response = client.post(
        "/internal/integration/users/match",
        headers=headers,
        json={"name": "小明"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "matched"
    assert body["matches"][0]["platform_id"] == "plat-1"
    assert body["matches"][0]["employee_number"] == "#0001"
    assert body["matches"][0]["balance"] == 0


def test_match_by_nickname_and_employee_number(client, headers, app_context):
    _add_user(app_context, "plat-1", "小明", 1, nickname="xiaoming")

    by_nickname = client.post(
        "/internal/integration/users/match", headers=headers, json={"name": "xiaoming"}
    )
    by_hash_number = client.post(
        "/internal/integration/users/match",
        headers=headers,
        json={"employee_number": "#0001"},
    )
    by_plain_number = client.post(
        "/internal/integration/users/match",
        headers=headers,
        json={"employee_number": "0001"},
    )
    by_platform_id = client.post(
        "/internal/integration/users/match",
        headers=headers,
        json={"platform_id": "plat-1"},
    )

    for response in (by_nickname, by_hash_number, by_plain_number, by_platform_id):
        assert response.status_code == 200
        assert response.json()["status"] == "matched"
        assert response.json()["matches"][0]["platform_id"] == "plat-1"


def test_match_is_ambiguous_on_shared_nickname(client, headers, app_context):
    _add_user(app_context, "plat-1", "小明", 1, nickname="双子星")
    _add_user(app_context, "plat-2", "小红", 2, nickname="双子星")

    response = client.post(
        "/internal/integration/users/match", headers=headers, json={"name": "双子星"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ambiguous"
    assert {match["platform_id"] for match in body["matches"]} == {"plat-1", "plat-2"}


def test_match_not_found_and_invalid_request(client, headers, app_context):
    missing = client.post(
        "/internal/integration/users/match", headers=headers, json={"name": "路人"}
    )
    assert missing.status_code == 200
    assert missing.json()["status"] == "not_found"

    both = client.post(
        "/internal/integration/users/match",
        headers=headers,
        json={"name": "小明", "platform_id": "plat-1"},
    )
    assert both.status_code == 422

    none_provided = client.post(
        "/internal/integration/users/match", headers=headers, json={}
    )
    assert none_provided.status_code == 422


def test_match_requires_core_token(client):
    response = client.post("/internal/integration/users/match", json={"name": "小明"})
    assert response.status_code == 401


# ---------------------------------------------------------------- 余额

def test_balance_lookup(client, headers, app_context):
    _add_user(app_context, "plat-1", "小明", 1, balance=37)

    found = client.get(
        "/internal/integration/users/plat-1/balance", headers=headers
    )
    missing = client.get(
        "/internal/integration/users/plat-9/balance", headers=headers
    )

    assert found.status_code == 200
    assert found.json()["balance"] == 37
    assert found.json()["employee_number"] == "#0001"
    assert missing.status_code == 404


# ---------------------------------------------------------------- 发币

def test_grant_coins_records_memo_and_balance(client, headers, app_context):
    _add_user(app_context, "plat-1", "小明", 1, balance=10)

    response = client.post(
        "/internal/integration/coins/grant",
        headers=headers,
        json={
            "platform_id": "plat-1",
            "amount": 5,
            "reason": "直播抽奖",
            "idempotency_key": "grant-key-0001",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["balance_after"] == 15
    assert body["amount"] == 5
    assert _balance(app_context, "plat-1") == 15
    with app_context.session_factory() as session:
        record = session.scalar(select(BalanceTransactionRecord))
        assert record.source == "api_grant"
        assert record.amount == 5
        assert record.memo == "直播抽奖"


@pytest.mark.parametrize(
    "payload",
    [
        {"amount": 0, "reason": "x", "idempotency_key": "key-zero-00001"},
        {"amount": 10001, "reason": "x", "idempotency_key": "key-big-000001"},
        {"amount": 5, "reason": "", "idempotency_key": "key-noR-000001"},
        {"amount": 5, "reason": "x", "idempotency_key": "short"},
    ],
)
def test_grant_rejects_invalid_payload(client, headers, app_context, payload):
    _add_user(app_context, "plat-1", "小明", 1)
    full = {"platform_id": "plat-1", **payload}

    response = client.post(
        "/internal/integration/coins/grant", headers=headers, json=full
    )

    assert response.status_code == 422


def test_grant_missing_user_returns_404(client, headers, app_context):
    response = client.post(
        "/internal/integration/coins/grant",
        headers=headers,
        json={
            "platform_id": "plat-none",
            "amount": 5,
            "reason": "x",
            "idempotency_key": "grant-key-404x",
        },
    )
    assert response.status_code == 404


# ---------------------------------------------------------------- 扣币

def test_deduct_insufficient_balance_rejected_by_default(client, headers, app_context):
    _add_user(app_context, "plat-1", "小明", 1, balance=3)

    response = client.post(
        "/internal/integration/coins/deduct",
        headers=headers,
        json={
            "platform_id": "plat-1",
            "amount": 5,
            "reason": "兑换",
            "idempotency_key": "deduct-key-001",
        },
    )

    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "insufficient_balance"
    assert body["balance"] == 3
    assert body["requested"] == 5
    assert _balance(app_context, "plat-1") == 3


def test_deduct_with_allow_partial_clamps_to_zero(client, headers, app_context):
    _add_user(app_context, "plat-1", "小明", 1, balance=3)

    response = client.post(
        "/internal/integration/coins/deduct",
        headers=headers,
        json={
            "platform_id": "plat-1",
            "amount": 5,
            "reason": "兑换",
            "idempotency_key": "deduct-key-002",
            "allow_partial": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["actual_amount"] == 3
    assert body["balance_after"] == 0
    assert _balance(app_context, "plat-1") == 0


def test_deduct_success(client, headers, app_context):
    _add_user(app_context, "plat-1", "小明", 1, balance=10)

    response = client.post(
        "/internal/integration/coins/deduct",
        headers=headers,
        json={
            "platform_id": "plat-1",
            "amount": 4,
            "reason": "兑换",
            "idempotency_key": "deduct-key-003",
        },
    )

    assert response.status_code == 200
    assert response.json()["balance_after"] == 6
    with app_context.session_factory() as session:
        record = session.scalar(select(BalanceTransactionRecord))
        assert record.source == "api_deduct"
        assert record.amount == -4
        assert record.memo == "兑换"


# ---------------------------------------------------------------- 幂等

def test_idempotency_key_replays_first_response(client, headers, app_context):
    _add_user(app_context, "plat-1", "小明", 1, balance=10)
    payload = {
        "platform_id": "plat-1",
        "amount": 5,
        "reason": "抽奖",
        "idempotency_key": "idem-key-000001",
    }

    first = client.post("/internal/integration/coins/grant", headers=headers, json=payload)
    second = client.post("/internal/integration/coins/grant", headers=headers, json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == first.json()
    assert _balance(app_context, "plat-1") == 15  # 只发了一次


def test_idempotency_key_conflict_on_different_payload(client, headers, app_context):
    _add_user(app_context, "plat-1", "小明", 1, balance=10)
    base = {
        "platform_id": "plat-1",
        "reason": "抽奖",
        "idempotency_key": "idem-key-000002",
    }

    first = client.post(
        "/internal/integration/coins/grant",
        headers=headers,
        json={**base, "amount": 5},
    )
    conflict = client.post(
        "/internal/integration/coins/grant",
        headers=headers,
        json={**base, "amount": 6},
    )

    assert first.status_code == 200
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_conflict"
    assert _balance(app_context, "plat-1") == 15


def test_idempotency_key_is_global_across_actions(client, headers, app_context):
    """同一个 key 不能先扣后发混用：请求指纹含 action。"""
    _add_user(app_context, "plat-1", "小明", 1, balance=10)

    grant = client.post(
        "/internal/integration/coins/grant",
        headers=headers,
        json={
            "platform_id": "plat-1",
            "amount": 5,
            "reason": "x",
            "idempotency_key": "idem-key-000003",
        },
    )
    mixed = client.post(
        "/internal/integration/coins/deduct",
        headers=headers,
        json={
            "platform_id": "plat-1",
            "amount": 5,
            "reason": "x",
            "idempotency_key": "idem-key-000003",
        },
    )

    assert grant.status_code == 200
    assert mixed.status_code == 409
    assert _balance(app_context, "plat-1") == 15


# ---------------------------------------------------------------- 发起额度

def test_game_quota_unknown_user_returns_404(client, headers):
    response = client.get(
        "/internal/integration/users/plat-none/game-quota", headers=headers
    )
    assert response.status_code == 404


def test_game_quota_reports_rank_limit_and_daily_usage(client, headers, app_context):
    from dzmm_bot.core.schema import (
        BlameGameDailyStartRecord,
        RankRecord,
        ShopDailyBonusRecord,
        ShopMultiplayerDailyStartRecord,
        UserRecord,
    )

    with app_context.session_factory.begin() as session:
        rank = RankRecord(
            sort_order=98,
            name="测试主管",
            level_label="T9",
            promotion_price=100,
            checkin_reward=5,
            vote_weight=1,
            multiplayer_game_limit=2,
        )
        session.add(rank)
        session.flush()
        user = UserRecord(
            platform_id="plat-1",
            display_name="小明",
            employee_number=1,
            balance=0,
            joined_at=NOW,
            rank_id=rank.id,
        )
        session.add(user)
        session.flush()
        session.add(
            ShopMultiplayerDailyStartRecord(
                user_id=user.id,
                play_date=NOW.date(),
                game_type="number_bomb",
                count=1,
            )
        )
        session.add(
            BlameGameDailyStartRecord(
                user_id=user.id, play_date=NOW.date(), count=2
            )
        )
        session.add(
            ShopDailyBonusRecord(
                user_id=user.id,
                usage_date=NOW.date(),
                multiplayer_total=3,
                multiplayer_used=1,
            )
        )
    # 另一位无职级用户（对照 unlimited 分支）
    _add_user(app_context, "plat-2", "小红", 2)

    response = client.get(
        "/internal/integration/users/plat-1/game-quota", headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["rank_name"] == "测试主管"
    assert body["rank_limit"] == 2
    assert body["unlimited"] is False
    assert body["used_today"] == {"number_bomb": 1, "blame_game": 2, "texas_holdem": 0}
    assert body["used_today_total"] == 3
    assert body["bonus_remaining"] == 2
    assert body["remaining"]["number_bomb"] == 1
    assert body["remaining"]["blame_game"] == 0
    assert body["remaining"]["texas_holdem"] == 2


def test_game_quota_without_rank_reads_unlimited(client, headers, app_context):
    _add_user(app_context, "plat-1", "小明", 1)

    response = client.get(
        "/internal/integration/users/plat-1/game-quota", headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["rank_name"] is None
    assert body["rank_limit"] is None
    assert body["unlimited"] is True
    assert body["remaining"] is None
    assert body["used_today_total"] == 0


def test_game_quota_negative_rank_limit_means_unlimited(client, headers, app_context):
    from dzmm_bot.core.schema import RankRecord, UserRecord

    with app_context.session_factory.begin() as session:
        rank = RankRecord(
            sort_order=99,
            name="测试董事",
            level_label="T10",
            promotion_price=100,
            checkin_reward=5,
            vote_weight=1,
            multiplayer_game_limit=-1,
        )
        session.add(rank)
        session.flush()
        session.add(
            UserRecord(
                platform_id="plat-1",
                display_name="小明",
                employee_number=1,
                balance=0,
                joined_at=NOW,
                rank_id=rank.id,
            )
        )

    response = client.get(
        "/internal/integration/users/plat-1/game-quota", headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["rank_limit"] == -1
    assert body["unlimited"] is True
    assert body["remaining"] is None

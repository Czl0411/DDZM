from dataclasses import asdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from dzmm_bot.core.estrus import build_climax_messages
from dzmm_bot.core.schema import (
    BalanceTransactionRecord,
    EstrusChopRecord,
    PRIMARY_GROUP_CHAT_ID,
)
from dzmm_bot.runtime.contracts import InboundMessage, MessageReference


BEIJING = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 10, 3, 15, 0, tzinfo=BEIJING)


class _SeqRandom:
    """关联模式每次消耗两个抽样值；非关联模式再抽一次扣币。"""

    def __init__(self, values):
        self.values = list(values)

    def random(self) -> float:
        if not self.values:
            return 0.0
        return self.values.pop(0)

    def choice(self, seq):
        return seq[0]


def _service(*, estrus_random=None, estrus_text_client=None, default_gspot_off=True):
    from dzmm_bot.core.commands import GroupCommandHandler
    from dzmm_bot.core.repository import CoreRepository
    from dzmm_bot.core.schema import Base
    from dzmm_bot.core.service import CoreService

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    repository = CoreRepository(
        factory, estrus_random=estrus_random,
        estrus_text_client=estrus_text_client,
    )
    repository.bootstrap_primary_group(
        "https://www.aikda.com/chat?c=group-main", NOW
    )
    if default_gspot_off:
        # G 点默认概率 10% 会额外消耗随机序列；非 G 点用例统一关闭，G 点用例显式开启
        settings = asdict(repository.get_estrus_settings())
        settings["g_spot_percent"] = 0
        # 入职自动分配 LV1（默认配额 1 次/日）；给所有职级宽松配额，配额用例显式覆盖
        settings["chopper_rank_quotas"] = {
            str(rank.id): 50 for rank in repository.list_ranks()
        }
        repository.set_estrus_settings(**settings)
    return (
        CoreService(repository, GroupCommandHandler(repository)),
        repository,
        factory,
    )


def _receive(service, message_id, sender, content, received_at, **kwargs):
    kwargs.setdefault("chatroom_id", "group-main")
    kwargs.setdefault("source_type", "group")
    return service.receive_inbound(
        InboundMessage(message_id, sender, content, received_at, **kwargs)
    )


def _join(service, message_id, sender, name, now):
    return _receive(service, message_id, sender, f"/入职 {name}", now)


def _balance(factory, platform_id):
    from dzmm_bot.core.schema import UserRecord

    with factory() as session:
        user = session.scalar(
            select(UserRecord).where(UserRecord.platform_id == platform_id)
        )
        return user.balance


def _replies(factory, message_id=None):
    from dzmm_bot.core.schema import OutboundRecord

    with factory() as session:
        rows = session.scalars(select(OutboundRecord)).all()
        return [row.text for row in rows]


def _joined_text(factory, snippet):
    from dzmm_bot.core.schema import OutboundRecord

    with factory() as session:
        texts = [
            row.text
            for row in session.scalars(select(OutboundRecord)).all()
        ]
    return any(snippet in text for text in texts)


def test_chop_by_name_with_probabilistic_gains():
    service, repository, factory = _service(
        estrus_random=_SeqRandom([0.60, 0.60])  # 热值 1，币 1
    )
    _join(service, "j0", "user-0", "甲", NOW)
    _join(service, "j1", "user-1", "乙", NOW)

    _receive(service, "c1", "user-0", "/凿 乙 试一试", NOW)

    texts = _replies(factory, "c1")
    assert any("【凿】甲凿了一下乙（试一试）" in text for text in texts)
    assert any("乙 发情值 +1（当前 1/100），获得 1 摸鱼币。" in text for text in texts)
    assert any("甲 共被扣除 1 摸鱼币。" in text for text in texts)
    assert _balance(factory, "user-1") == _balance(factory, "user-0") + 2


def _configure_estrus_settings(repository, **changes):
    return repository.set_estrus_settings(
        **{**asdict(repository.get_estrus_settings()), **changes}
    )


def _rank_id(factory, sort_order):
    from dzmm_bot.core.schema import RankRecord

    with factory() as session:
        return session.scalar(
            select(RankRecord).where(RankRecord.sort_order == sort_order)
        ).id


def _assign_rank(repository, factory, platform_id, sort_order):
    """把用户挂到指定职级（list_ranks 负责种子默认职级）。"""
    from dzmm_bot.core.schema import RankRecord, UserRecord

    repository.list_ranks()
    with factory.begin() as session:
        rank = session.scalar(
            select(RankRecord).where(RankRecord.sort_order == sort_order)
        )
        user = session.scalar(
            select(UserRecord).where(UserRecord.platform_id == platform_id)
        )
        user.rank_id = rank.id


@pytest.mark.parametrize(
    ("coin_roll", "expected_coins"),
    [(0.0, 0), (0.499, 0), (0.50, 1), (0.799, 1), (0.80, 2), (0.999, 2)],
)
def test_linked_chop_shares_coin_roll_and_records_both_sides(coin_roll, expected_coins):
    random = _SeqRandom([0.0, coin_roll, 0.42])
    service, repository, factory = _service(estrus_random=random)
    _join(service, "j0", "user-0", "甲", NOW)
    _join(service, "j1", "user-1", "乙", NOW)
    _configure_estrus_settings(
        repository, chopper_coin_p0=100, chopper_coin_p1=0, chopper_coin_p2=0
    )
    chopper_before = _balance(factory, "user-0")
    target_before = _balance(factory, "user-1")

    _receive(service, "c1", "user-0", "/凿 乙", NOW)

    assert _balance(factory, "user-0") == chopper_before - expected_coins
    assert _balance(factory, "user-1") == target_before + expected_coins
    assert random.values == [0.42]
    assert _joined_text(factory, f"甲 共被扣除 {expected_coins} 摸鱼币。")
    with factory() as session:
        chop = session.scalar(select(EstrusChopRecord))
        assert chop.coins == expected_coins
        assert chop.coins_deducted == expected_coins
        transactions = session.scalars(
            select(BalanceTransactionRecord).where(
                BalanceTransactionRecord.source.in_(("estrus_gain", "estrus_chop_cost"))
            )
        ).all()
        assert sorted((entry.source, entry.amount) for entry in transactions) == (
            [("estrus_chop_cost", -expected_coins), ("estrus_gain", expected_coins)]
            if expected_coins else []
        )


@pytest.mark.parametrize(
    ("gain_roll", "deduction_roll", "gain", "deduction"),
    [(0.0, 0.60, 0, 1), (0.60, 0.0, 1, 0), (0.90, 0.60, 2, 1), (0.60, 0.90, 1, 2)],
)
def test_unlinked_chop_rolls_coins_independently(gain_roll, deduction_roll, gain, deduction):
    random = _SeqRandom([0.0, gain_roll, deduction_roll, 0.42])
    service, repository, factory = _service(estrus_random=random)
    _join(service, "j0", "user-0", "甲", NOW)
    _join(service, "j1", "user-1", "乙", NOW)
    _configure_estrus_settings(repository, coins_linked=False)
    chopper_before = _balance(factory, "user-0")
    target_before = _balance(factory, "user-1")

    _receive(service, "c1", "user-0", "/凿 乙", NOW)

    assert _balance(factory, "user-0") == chopper_before - deduction
    assert _balance(factory, "user-1") == target_before + gain
    assert random.values == [0.42]
    assert _joined_text(factory, f"甲 共被扣除 {deduction} 摸鱼币。")
    with factory() as session:
        chop = session.scalar(select(EstrusChopRecord))
        assert (chop.coins, chop.coins_deducted) == (gain, deduction)


@pytest.mark.parametrize(
    ("probabilities", "expected_deduction"),
    [((100, 0, 0), 0), ((0, 100, 0), 1), ((0, 0, 100), 2)],
)
def test_unlinked_chop_respects_custom_deduction_probabilities(probabilities, expected_deduction):
    service, repository, factory = _service(estrus_random=_SeqRandom([0.0, 0.60, 0.60]))
    _join(service, "j0", "user-0", "甲", NOW)
    _join(service, "j1", "user-1", "乙", NOW)
    _configure_estrus_settings(
        repository,
        coins_linked=False,
        chopper_coin_p0=probabilities[0],
        chopper_coin_p1=probabilities[1],
        chopper_coin_p2=probabilities[2],
    )
    chopper_before = _balance(factory, "user-0")

    _receive(service, "c1", "user-0", "/凿 乙", NOW)

    assert _balance(factory, "user-0") == chopper_before - expected_deduction
    with factory() as session:
        chop = session.scalar(select(EstrusChopRecord))
        assert (chop.coins, chop.coins_deducted) == (1, expected_deduction)


@pytest.mark.parametrize("coins_linked", [True, False])
@pytest.mark.parametrize(
    ("chopper_fixed", "target_fixed", "rolls", "deduction", "gain"),
    [
        (5, None, [0.60, 0.90], 5, 2),
        (None, 7, [0.60, 0.60], 1, 7),
        (5, 7, [0.60], 5, 7),
        (0, 0, [0.60], 0, 0),
        (0, None, [0.60, 0.90], 0, 2),
        (None, 0, [0.60, 0.90], 2, 0),
        (99999, 99999, [0.60], 99999, 99999),
    ],
)
def test_fixed_chop_coins_override_random_and_linked_rolls(
    coins_linked, chopper_fixed, target_fixed, rolls, deduction, gain
):
    random = _SeqRandom([*rolls, 0.42])
    service, repository, factory = _service(estrus_random=random)
    _join(service, "j0", "user-0", "甲", NOW)
    _join(service, "j1", "user-1", "乙", NOW)
    _configure_estrus_settings(
        repository,
        coins_linked=coins_linked,
        chopper_fixed_coins=chopper_fixed,
        target_fixed_coins=target_fixed,
    )
    chopper_before = _balance(factory, "user-0")
    target_before = _balance(factory, "user-1")

    _receive(service, "c1", "user-0", "/凿 乙", NOW)

    assert random.values == [0.42]
    assert _balance(factory, "user-0") == chopper_before - deduction
    assert _balance(factory, "user-1") == target_before + gain
    assert _joined_text(factory, f"甲 共被扣除 {deduction} 摸鱼币。")
    if gain > 0:
        assert _joined_text(factory, f"获得 {gain} 摸鱼币。")
    with factory() as session:
        chop = session.scalar(select(EstrusChopRecord))
        assert (chop.coins, chop.coins_deducted) == (gain, deduction)
        assert chop.heat_gain == 1
        transactions = session.scalars(
            select(BalanceTransactionRecord).where(
                BalanceTransactionRecord.source.in_(("estrus_gain", "estrus_chop_cost"))
            )
        ).all()
        expected_transactions = []
        if deduction:
            expected_transactions.append(("estrus_chop_cost", -deduction))
        if gain:
            expected_transactions.append(("estrus_gain", gain))
        assert sorted((entry.source, entry.amount) for entry in transactions) == expected_transactions


def test_disabling_fixed_coins_restores_existing_random_linked_settings():
    random = _SeqRandom([0.60, 0.60, 0.60, 0.42])
    service, repository, factory = _service(estrus_random=random)
    _join(service, "j0", "user-0", "甲", NOW)
    _join(service, "j1", "user-1", "乙", NOW)
    _configure_estrus_settings(repository, chopper_fixed_coins=5, target_fixed_coins=7)

    _receive(service, "fixed", "user-0", "/凿 乙", NOW)
    settings = _configure_estrus_settings(
        repository, chopper_fixed_coins=None, target_fixed_coins=None
    )
    _receive(service, "random", "user-0", "/凿 乙", NOW + timedelta(minutes=1))

    assert settings.coins_linked is True
    assert (settings.coin_p0, settings.coin_p1, settings.coin_p2) == (50, 30, 20)
    assert _balance(factory, "user-0") == -6
    assert _balance(factory, "user-1") == 8
    assert random.values == [0.42]


def test_default_chop_settings_link_coins_and_leave_target_unlimited():
    _, repository, _ = _service(default_gspot_off=False)
    settings = repository.get_estrus_settings()

    assert settings.coins_linked is True
    assert settings.target_daily_limit == 0
    assert settings.chopper_fixed_coins is None
    assert settings.target_fixed_coins is None
    assert settings.combo_chop_enabled is False
    assert settings.g_spot_percent == 10
    assert settings.g_spot_heat_bonus == 10
    assert settings.chopper_rank_quotas is None
    assert (settings.chopper_coin_p0, settings.chopper_coin_p1, settings.chopper_coin_p2) == (
        settings.coin_p0, settings.coin_p1, settings.coin_p2
    )


def test_chop_deducts_even_when_chopper_has_zero_balance():
    service, _, factory = _service(estrus_random=_SeqRandom([0.0, 0.90]))
    _join(service, "j0", "user-0", "甲", NOW)
    _join(service, "j1", "user-1", "乙", NOW)
    assert _balance(factory, "user-0") == 0

    _receive(service, "c1", "user-0", "/凿 乙", NOW)

    assert _balance(factory, "user-0") == -2
    assert _balance(factory, "user-1") == 2


@pytest.mark.parametrize(
    "rejection", ["self", "refused", "disabled", "cooldown", "chopper_limit", "target_limit"]
)
@pytest.mark.parametrize("fixed_coins", [False, True])
def test_rejected_chops_do_not_roll_charge_or_count(rejection, fixed_coins):
    random = _SeqRandom([0.0, 0.90, 0.90, 0.90])
    service, repository, factory = _service(estrus_random=random)
    _join(service, "j0", "user-0", "甲", NOW)
    _join(service, "j1", "user-1", "乙", NOW)
    if fixed_coins:
        _configure_estrus_settings(repository, chopper_fixed_coins=5, target_fixed_coins=7)
    if rejection == "refused":
        _receive(service, "refuse", "user-1", "/拒绝被凿", NOW)
    elif rejection == "disabled":
        _configure_estrus_settings(repository, enabled=False)
    elif rejection == "chopper_limit":
        # LV1 显式配额 1 次：首凿用掉，次凿被拒
        _assign_rank(repository, factory, "user-0", 1)
        _configure_estrus_settings(
            repository,
            chopper_rank_quotas={str(_rank_id(factory, 1)): 1},
        )
        _receive(service, "first", "user-0", "/凿 乙", NOW)
    elif rejection in {"cooldown", "target_limit"}:
        _receive(service, "first", "user-0", "/凿 乙", NOW)
        changes = {
            "cooldown": {"chop_cooldown_seconds": 60},
            "target_limit": {"target_daily_limit": 1},
        }
        _configure_estrus_settings(repository, **changes[rejection])
    balances = (_balance(factory, "user-0"), _balance(factory, "user-1"))
    values_before = random.values.copy()
    info_before = repository.get_my_estrus("user-1", PRIMARY_GROUP_CHAT_ID, NOW)

    _receive(service, "rejected", "user-0", "/凿 甲" if rejection == "self" else "/凿 乙", NOW)

    assert (_balance(factory, "user-0"), _balance(factory, "user-1")) == balances
    assert random.values == values_before
    info_after = repository.get_my_estrus("user-1", PRIMARY_GROUP_CHAT_ID, NOW)
    assert info_after["chopped_count"] == info_before["chopped_count"]
    assert info_after["heat"] == info_before["heat"]
    with factory() as session:
        assert len(session.scalars(select(EstrusChopRecord)).all()) == (
            1 if rejection in {"cooldown", "chopper_limit", "target_limit"} else 0
        )


@pytest.mark.parametrize("fixed_coins", [False, True])
def test_replayed_chop_does_not_deduct_twice(fixed_coins):
    service, repository, factory = _service(estrus_random=_SeqRandom([0.60, 0.60]))
    _join(service, "j0", "user-0", "甲", NOW)
    _join(service, "j1", "user-1", "乙", NOW)
    if fixed_coins:
        _configure_estrus_settings(repository, chopper_fixed_coins=5, target_fixed_coins=7)

    _receive(service, "c1", "user-0", "/凿 乙", NOW)
    balances = (_balance(factory, "user-0"), _balance(factory, "user-1"))
    result = _receive(service, "c1", "user-0", "/凿 乙", NOW)

    assert result.inserted is False
    assert (_balance(factory, "user-0"), _balance(factory, "user-1")) == balances
    assert repository.get_my_estrus("user-1", PRIMARY_GROUP_CHAT_ID, NOW)["chopped_count"] == 1


@pytest.mark.parametrize("fixed_coins", [False, True])
def test_chop_deduction_failure_rolls_back_gain_and_chop(monkeypatch, fixed_coins):
    service, repository, factory = _service(estrus_random=_SeqRandom([0.60, 0.60]))
    _join(service, "j0", "user-0", "甲", NOW)
    _join(service, "j1", "user-1", "乙", NOW)
    if fixed_coins:
        _configure_estrus_settings(repository, chopper_fixed_coins=5, target_fixed_coins=7)
    balances = (_balance(factory, "user-0"), _balance(factory, "user-1"))
    apply_balance_change = repository._apply_balance_change

    def fail_deduction(user, amount, source, occurred_at, **kwargs):
        if source == "estrus_chop_cost":
            raise RuntimeError("deduction failed")
        return apply_balance_change(user, amount, source, occurred_at, **kwargs)

    monkeypatch.setattr(repository, "_apply_balance_change", fail_deduction)
    with pytest.raises(RuntimeError, match="deduction failed"):
        _receive(service, "c1", "user-0", "/凿 乙", NOW)

    assert (_balance(factory, "user-0"), _balance(factory, "user-1")) == balances
    with factory() as session:
        assert session.scalar(select(EstrusChopRecord)) is None
        assert session.scalar(
            select(BalanceTransactionRecord).where(
                BalanceTransactionRecord.source.in_(("estrus_gain", "estrus_chop_cost"))
            )
        ) is None
    info = repository.get_my_estrus("user-1", PRIMARY_GROUP_CHAT_ID, NOW)
    assert info["chopped_count"] == 0
    assert info["heat"] == 0


def test_target_daily_limit_counts_all_choppers_without_charging_blocked_chops():
    random = _SeqRandom([0.60, 0.60] * 3)
    service, repository, factory = _service(estrus_random=random)
    for index, name in enumerate(("甲", "乙", "丙", "丁")):
        _join(service, f"j{index}", f"user-{index}", name, NOW)
    _configure_estrus_settings(repository, target_daily_limit=2)

    _receive(service, "c1", "user-0", "/凿 乙", NOW)
    _receive(service, "c2", "user-2", "/凿 乙", NOW + timedelta(minutes=1))
    balances = (_balance(factory, "user-3"), _balance(factory, "user-1"))
    _receive(service, "c3", "user-3", "/凿 乙", NOW + timedelta(minutes=2))

    assert _joined_text(factory, "乙 今天已经被凿了 2 次，达到每日上限（2 次），明天再来吧。")
    assert (_balance(factory, "user-3"), _balance(factory, "user-1")) == balances
    assert random.values == [0.60, 0.60]
    info = repository.get_my_estrus("user-1", PRIMARY_GROUP_CHAT_ID, NOW)
    assert info["chopped_count"] == 2
    assert info["heat"] == 2

    _receive(service, "c4", "user-3", "/凿 甲", NOW + timedelta(minutes=3))

    assert random.values == []
    assert _balance(factory, "user-3") == balances[0] - 1


def test_target_daily_limit_resets_at_beijing_midnight():
    service, repository, factory = _service(estrus_random=_SeqRandom([0.60, 0.60] * 2))
    _join(service, "j0", "user-0", "甲", NOW)
    _join(service, "j1", "user-1", "乙", NOW)
    _configure_estrus_settings(repository, target_daily_limit=1)
    late = NOW.replace(hour=23, minute=59)

    _receive(service, "c1", "user-0", "/凿 乙", late)
    _receive(service, "c2", "user-0", "/凿 乙", late + timedelta(seconds=30))
    _receive(service, "c3", "user-0", "/凿 乙", late + timedelta(minutes=1))

    assert _joined_text(factory, "乙 今天已经被凿了 1 次，达到每日上限（1 次）")
    info = repository.get_my_estrus("user-1", PRIMARY_GROUP_CHAT_ID, late + timedelta(minutes=1))
    assert info["chopped_count"] == 2
    assert info["heat"] == 2  # 发情值跨天不清零：两次各 +2


def test_target_daily_limit_is_isolated_by_group_and_zero_disables_it():
    service, repository, factory = _service(estrus_random=_SeqRandom([0.60, 0.60] * 3))
    _join(service, "j0", "user-0", "甲", NOW)
    _join(service, "j1", "user-1", "乙", NOW)
    group = repository.create_group_chat(
        "二群", "https://www.aikda.com/chat?c=group-second", True, True, True, True, NOW
    )
    _configure_estrus_settings(repository, target_daily_limit=1)

    _receive(service, "c1", "user-0", "/凿 乙", NOW)
    _receive(service, "c2", "user-0", "/凿 乙", NOW, chatroom_id="group-second")

    assert repository.get_my_estrus("user-1", PRIMARY_GROUP_CHAT_ID, NOW)["chopped_count"] == 1
    assert repository.get_my_estrus("user-1", group.id, NOW)["chopped_count"] == 1
    _configure_estrus_settings(repository, target_daily_limit=0)
    _receive(service, "c3", "user-0", "/凿 乙", NOW)
    assert repository.get_my_estrus("user-1", PRIMARY_GROUP_CHAT_ID, NOW)["chopped_count"] == 2


def test_chop_with_zero_gains_reads_as_nothing():
    service, repository, factory = _service(
        estrus_random=_SeqRandom([0.0, 0.0])  # 热值 0，币 0
    )
    _join(service, "j0", "user-0", "甲", NOW)
    _join(service, "j1", "user-1", "乙", NOW)

    _receive(service, "c1", "user-0", "/凿 乙", NOW)

    assert _joined_text(factory, "乙 发情值 +0（当前 0/100），一无所获。")


def test_chop_reply_reference_form_wins():
    service, repository, factory = _service(
        estrus_random=_SeqRandom([0.90, 0.90])  # 热值 2，币 2
    )
    _join(service, "j0", "user-0", "甲", NOW)
    _join(service, "j1", "user-1", "乙", NOW)
    reference = MessageReference(
        sender_platform_id="user-1",
        message_id="ref-1",
        content_type="text",
    )

    _receive(
        service, "c1", "user-0", "/凿 接招", NOW, reference=reference
    )

    texts = _replies(factory, "c1")
    assert any("【凿】甲凿了一下乙（接招）" in text for text in texts)
    assert any("乙 发情值 +2（当前 2/100）" in text for text in texts)


def test_chop_climax_triggers_resets_and_counts():
    # 阈值校验下限 10：热值恒为 2，连凿 5 次第 5 次触发
    service, repository, factory = _service(
        estrus_random=_SeqRandom([0.90, 0.0] * 5)
    )
    _join(service, "j0", "user-0", "甲", NOW)
    _join(service, "j1", "user-1", "乙", NOW)
    _configure_estrus_settings(
        repository,
        climax_threshold=10,
        heat_p0=50,
        heat_p1=30,
        heat_p2=20,
        coin_p0=50,
        coin_p1=30,
        coin_p2=20,
        chop_cooldown_seconds=0,
    )
    for index in range(4):
        _receive(
            service, f"c{index}", "user-0", "/凿 乙",
            NOW + timedelta(minutes=index),
        )
    final_index = 4
    _receive(
        service, f"c{final_index}", "user-0", "/凿 乙",
        NOW + timedelta(minutes=final_index),
    )

    texts = _replies(factory)
    assert any("🔥 乙 发情值爆表！" in text for text in texts)
    assert any("（今日第 1 次 / 总第 1 次）" in text for text in texts)
    assert any("发情值爆表" in text for text in texts)
    # AI 未配置 → unknown 兜底文案库第一条
    assert any("被凿得浑身一激灵" in text for text in texts)

    info = repository.get_my_estrus(
        "user-1", PRIMARY_GROUP_CHAT_ID, NOW
    )
    assert info["heat"] == 0
    assert info["today_climaxes"] == 1
    assert info["total_climaxes"] == 1


def test_refused_target_public_poke_back():
    service, repository, factory = _service(estrus_random=_SeqRandom([]))
    _join(service, "j0", "user-0", "甲", NOW)
    _join(service, "j1", "user-1", "乙", NOW)

    _receive(service, "c0", "user-1", "/拒绝被凿", NOW)
    assert _joined_text(factory, "已开启拒绝被凿")

    _receive(service, "c1", "user-0", "/凿 乙", NOW)
    assert _joined_text(factory, "乙 拒绝了 甲 的凿，并且给了 甲 一杵子。")


def test_allow_back_after_refusal():
    service, repository, factory = _service(
        estrus_random=_SeqRandom([0.60, 0.60])
    )
    _join(service, "j0", "user-0", "甲", NOW)
    _join(service, "j1", "user-1", "乙", NOW)

    _receive(service, "c0", "user-1", "/拒绝被凿", NOW)
    _receive(service, "c1", "user-0", "/凿 乙", NOW)
    assert _joined_text(factory, "乙 拒绝了 甲 的凿")

    _receive(service, "c2", "user-1", "/允许被凿", NOW)
    assert _joined_text(factory, "已开启允许被凿")

    _receive(service, "c3", "user-0", "/凿 乙", NOW)
    assert _joined_text(factory, "【凿】甲凿了一下乙")


def test_chop_self_and_unguarded_cases():
    service, repository, factory = _service(estrus_random=_SeqRandom([]))
    _join(service, "j0", "user-0", "甲", NOW)

    _receive(service, "c1", "user-0", "/凿 甲", NOW)
    assert _joined_text(factory, "不能凿自己。")

    _receive(service, "c2", "user-9", "/凿 甲", NOW)
    assert _joined_text(factory, "请先用 /入职")

    _receive(service, "c3", "user-0", "/凿 路人", NOW)
    assert _joined_text(factory, "没找到员工「路人」。")

    _receive(service, "c4", "user-0", "/凿", NOW)
    assert _joined_text(factory, "用法：引用对方消息发送 /凿")


def test_chopper_cooldown_blocks_second_chop():
    service, repository, factory = _service(
        estrus_random=_SeqRandom([0.60, 0.60, 0.60, 0.60])
    )
    _join(service, "j0", "user-0", "甲", NOW)
    _join(service, "j1", "user-1", "乙", NOW)
    _join(service, "j2", "user-2", "丙", NOW)
    repository.set_estrus_settings(
        enabled=True,
        climax_threshold=100,
        heat_p0=50,
        heat_p1=30,
        heat_p2=20,
        coin_p0=50,
        coin_p1=30,
        coin_p2=20,
        chop_cooldown_seconds=600,
        g_spot_percent=0,
    )

    _receive(service, "c1", "user-0", "/凿 乙", NOW)
    _receive(
        service, "c2", "user-0", "/凿 丙", NOW + timedelta(seconds=5)
    )
    assert _joined_text(factory, "凿冷却中，请")


def test_my_estrus_and_popularity_ranking():
    service, repository, factory = _service(
        estrus_random=_SeqRandom([0.90, 0.60, 0.90, 0.60])
    )
    _join(service, "j0", "user-0", "甲", NOW)
    _join(service, "j1", "user-1", "乙", NOW)

    _receive(service, "c1", "user-0", "/凿 乙", NOW)
    _receive(service, "c2", "user-0", "/凿 乙", NOW + timedelta(minutes=1))

    _receive(service, "q1", "user-1", "/我的凿", NOW)
    texts = _replies(factory)
    assert any("【我的凿】" in text for text in texts)
    assert any("发情值：4/100" in text for text in texts)
    assert any("被凿：今日 2 次 / 累计 2 次" in text for text in texts)
    assert any("凿人：今日 0 次 / 累计 0 次" in text for text in texts)
    assert any("状态：允许被凿" in text for text in texts)

    # 甲凿了两次：凿人次数统计
    _receive(service, "q2", "user-0", "/我的凿", NOW)
    assert any("被凿：今日 0 次 / 累计 0 次" in text for text in _replies(factory))
    assert any("凿人：今日 2 次 / 累计 2 次" in text for text in _replies(factory))

    _receive(service, "q3", "user-0", "/人气榜", NOW)
    texts = _replies(factory)
    assert any("【人气榜】" in text for text in texts)
    assert any("乙：今日被凿2次" in text for text in texts)
    # 旧指令归一化到新榜 / 新查询
    _receive(service, "q4", "user-0", "/最受欢迎", NOW)
    assert any("【人气榜】" in text for text in _replies(factory))
    _receive(service, "q5", "user-1", "/我的发情值", NOW)
    assert any("【我的凿】" in text for text in _replies(factory))


def test_popularity_board_counts_today_only_and_keeps_heat():
    service, repository, factory = _service(
        estrus_random=_SeqRandom([0.90, 0.60] * 6)
    )
    _join(service, "j0", "user-0", "甲", NOW)
    _join(service, "j1", "user-1", "乙", NOW)
    _join(service, "j2", "user-2", "丙", NOW)

    # 昨天：乙被凿 2 次（发情值 4）
    _receive(service, "c1", "user-0", "/凿 乙", NOW)
    _receive(service, "c2", "user-0", "/凿 乙", NOW + timedelta(minutes=1))
    # 今天：乙被凿 1 次、丙被凿 1 次
    tomorrow = NOW + timedelta(days=1)
    _receive(service, "c3", "user-0", "/凿 乙", tomorrow)
    _receive(service, "c4", "user-1", "/凿 丙", tomorrow)

    _receive(service, "q1", "user-0", "/最受欢迎", tomorrow)
    texts = _replies(factory)
    assert any("乙：今日被凿1次" in text for text in texts)
    assert any("丙：今日被凿1次" in text for text in texts)
    assert not any("今日被凿2次" in text for text in texts)

    # 发情值跨天不清零：乙昨天 4，今天再 +2 → 6
    info = repository.get_my_estrus("user-1", PRIMARY_GROUP_CHAT_ID, tomorrow)
    assert info["heat"] == 6
    assert info["chopped_count"] == 3  # 累计不清零
    assert info["today_chopped"] == 1

    # 甲/乙昨天的高潮计数在今日榜里不再参与（榜单只剩今日被凿）


def test_heat_persists_across_days_without_chop():
    service, repository, factory = _service(
        estrus_random=_SeqRandom([0.90, 0.60])
    )
    _join(service, "j0", "user-0", "甲", NOW)
    _join(service, "j1", "user-1", "乙", NOW)

    _receive(service, "c1", "user-0", "/凿 乙", NOW)
    tomorrow = NOW + timedelta(days=1)
    info = repository.get_my_estrus("user-1", PRIMARY_GROUP_CHAT_ID, tomorrow)
    assert info["heat"] == 2  # 发情值跨天不清零
    assert info["today_climaxes"] == 0  # 今日高潮仍跨天重置
    assert info["chopped_count"] == 1


def test_chopper_rank_quota_blocks_and_counts():
    service, repository, factory = _service(
        estrus_random=_SeqRandom([0.60, 0.60] * 6)
    )
    _join(service, "j0", "user-0", "甲", NOW)
    _join(service, "j1", "user-1", "乙", NOW)
    _join(service, "j2", "user-2", "丙", NOW)
    _assign_rank(repository, factory, "user-0", 1)  # LV1
    rank_key = str(_rank_id(factory, 1))
    repository.set_estrus_settings(
        enabled=True,
        climax_threshold=100,
        heat_p0=50,
        heat_p1=30,
        heat_p2=20,
        coin_p0=50,
        coin_p1=30,
        coin_p2=20,
        chop_cooldown_seconds=0,
        chopper_rank_quotas={rank_key: 1},
        g_spot_percent=0,
    )

    _receive(service, "c1", "user-0", "/凿 乙", NOW)
    _receive(service, "c2", "user-0", "/凿 丙", NOW + timedelta(minutes=1))

    texts = _replies(factory)
    assert any("你今天已经凿了 1 次，达到职级配额（1 次），明天再来吧。" in text for text in texts)
    # 第 2 凿被拒：乙只被凿 1 次（被拒的不计入）
    info = repository.get_my_estrus("user-1", PRIMARY_GROUP_CHAT_ID, NOW)
    assert info["chopped_count"] == 1
    assert info["heat"] == 1

    # 甲自己的凿人统计：今日 1 次（被拒的不计）
    _receive(service, "q1", "user-0", "/我的凿", NOW)
    assert any("凿人：今日 1 次 / 累计 1 次" in text for text in _replies(factory))

    # 显式职级配额覆盖：LV1 提高到 3 次后可继续凿
    settings = asdict(repository.get_estrus_settings())
    settings["chopper_rank_quotas"] = {rank_key: 3}
    repository.set_estrus_settings(**settings)
    _receive(service, "c3", "user-0", "/凿 乙", NOW + timedelta(minutes=2))
    _receive(service, "c4", "user-0", "/凿 丙", NOW + timedelta(minutes=3))
    assert any("【凿】甲凿了一下丙" in text for text in _replies(factory))
    with factory() as session:
        assert len(session.scalars(select(EstrusChopRecord)).all()) == 3


def test_combo_chop_disabled_by_default():
    service, repository, factory = _service(estrus_random=_SeqRandom([0.60, 0.60]))
    _join(service, "j0", "user-0", "甲", NOW)
    _join(service, "j1", "user-1", "乙", NOW)
    balances = (_balance(factory, "user-0"), _balance(factory, "user-1"))

    _receive(service, "c1", "user-0", "/凿 乙 3", NOW)

    assert _joined_text(factory, "连续凿未开启，甲 只能一下一下地凿")
    assert (_balance(factory, "user-0"), _balance(factory, "user-1")) == balances
    with factory() as session:
        assert session.scalar(select(EstrusChopRecord)) is None


def test_combo_chop_executes_and_aggregates_reply():
    random = _SeqRandom([0.60, 0.60] * 3)
    service, repository, factory = _service(estrus_random=random)
    _join(service, "j0", "user-0", "甲", NOW)
    _join(service, "j1", "user-1", "乙", NOW)
    _configure_estrus_settings(repository, combo_chop_enabled=True)

    _receive(service, "c1", "user-0", "/凿 乙 3", NOW)

    texts = _replies(factory)
    assert any("【凿】甲凿了 3 次乙" in text for text in texts)
    assert any("甲 共被扣除 3 摸鱼币。" in text for text in texts)
    assert any("乙 发情值 +3（当前 3/100），获得 3 摸鱼币。" in text for text in texts)
    assert _balance(factory, "user-1") == _balance(factory, "user-0") + 6
    assert random.values == []
    with factory() as session:
        assert len(session.scalars(select(EstrusChopRecord)).all()) == 3


def test_combo_chop_named_form_with_note_and_count():
    random = _SeqRandom([0.60, 0.60] * 2)
    service, repository, factory = _service(estrus_random=random)
    _join(service, "j0", "user-0", "甲", NOW)
    _join(service, "j1", "user-1", "乙", NOW)
    _configure_estrus_settings(repository, combo_chop_enabled=True)

    _receive(service, "c1", "user-0", "/凿 乙 接招 2", NOW)

    assert any("【凿】甲凿了 2 次乙（接招）" in text for text in _replies(factory))
    assert random.values == []


def test_combo_chop_reference_form():
    random = _SeqRandom([0.90, 0.0] * 2)
    service, repository, factory = _service(estrus_random=random)
    _join(service, "j0", "user-0", "甲", NOW)
    _join(service, "j1", "user-1", "乙", NOW)
    _configure_estrus_settings(repository, combo_chop_enabled=True)
    reference = MessageReference(
        sender_platform_id="user-1",
        message_id="ref-1",
        content_type="text",
    )

    _receive(service, "c1", "user-0", "/凿 2", NOW, reference=reference)

    texts = _replies(factory)
    assert any("【凿】甲凿了 2 次乙" in text for text in texts)
    assert any("乙 发情值 +4（当前 4/100），一无所获。" in text for text in texts)


def test_combo_chop_truncated_by_target_daily_limit():
    random = _SeqRandom([0.60, 0.60] * 4)
    service, repository, factory = _service(estrus_random=random)
    _join(service, "j0", "user-0", "甲", NOW)
    _join(service, "j1", "user-1", "乙", NOW)
    _configure_estrus_settings(repository, combo_chop_enabled=True, target_daily_limit=2)

    _receive(service, "c1", "user-0", "/凿 乙 5", NOW)

    texts = _replies(factory)
    assert any("【凿】甲凿了 2 次乙" in text for text in texts)
    assert any("（连续凿提前停止：乙 今日被凿次数已达上限）" in text for text in texts)
    assert random.values == [0.60, 0.60] * 2


def test_combo_chop_truncated_by_rank_quota():
    random = _SeqRandom([0.60, 0.60] * 3)
    service, repository, factory = _service(estrus_random=random)
    _join(service, "j0", "user-0", "甲", NOW)
    _join(service, "j1", "user-1", "乙", NOW)
    _assign_rank(repository, factory, "user-0", 1)  # LV1
    _configure_estrus_settings(
        repository,
        combo_chop_enabled=True,
        chopper_rank_quotas={str(_rank_id(factory, 1)): 1},
    )

    _receive(service, "c1", "user-0", "/凿 乙 5", NOW)

    # 连凿自动截断到职级剩余配额：只执行 1 次
    assert any("【凿】甲凿了一下乙" in text for text in _replies(factory))
    assert random.values == [0.60, 0.60] * 2


def test_g_spot_hit_grants_bonus_heat():
    random = _SeqRandom([0.0, 0.60])  # G 点 roll 0 → 命中；币 roll 0.60 → 1
    service, repository, factory = _service(estrus_random=random)
    _join(service, "j0", "user-0", "甲", NOW)
    _join(service, "j1", "user-1", "乙", NOW)
    _configure_estrus_settings(repository, g_spot_percent=100, g_spot_heat_bonus=10)

    _receive(service, "c1", "user-0", "/凿 乙", NOW)

    texts = _replies(factory)
    assert any("🎯 凿中G点 1 次！" in text for text in texts)
    assert any("乙 发情值 +10（当前 10/100），获得 1 摸鱼币。" in text for text in texts)
    assert _balance(factory, "user-1") == 1
    assert _balance(factory, "user-0") == -1
    with factory() as session:
        chop = session.scalar(select(EstrusChopRecord))
        assert chop.heat_gain == 10


def test_chop_special_targets_get_dedicated_replies():
    service, repository, factory = _service(estrus_random=_SeqRandom([]))
    _join(service, "j0", "user-0", "甲", NOW)
    _join(service, "j1", "user-1", "乙", NOW)

    _receive(service, "c1", "user-0", "/凿 所有人", NOW)
    assert _joined_text(factory, "你有几个牛子？还想凿这么多！")

    _receive(service, "c2", "user-0", "/凿 全体员工", NOW)
    assert _joined_text(factory, "你有几个牛子？还想凿这么多！")

    for word in ("全体的家人们", "所有人！！", "家人们", "挨个凿一遍", "全部"):
        _receive(service, f"c2-{word}", "user-0", f"/凿 {word}", NOW)
        assert _joined_text(factory, "你有几个牛子？还想凿这么多！")

    _receive(service, "c3", "user-0", "/凿 我", NOW)
    assert _joined_text(factory, "不能凿自己。")

    _receive(service, "c4", "user-0", "/凿 机器人", NOW)
    assert _joined_text(
        factory, "机器人大工没法被凿——TA 只负责看戏，偶尔扣你工资。"
    )

    _receive(service, "c4b", "user-0", "/凿 总监事", NOW)
    assert _joined_text(
        factory, "机器人大工没法被凿——TA 只负责看戏，偶尔扣你工资。"
    )

    _receive(service, "c5", "user-0", "/凿 老板", NOW)
    assert _joined_text(
        factory, "胆子不小，连 TA 都敢凿？不过 TA 还没入职摸鱼公司。"
    )

    _receive(service, "c6", "user-0", "/凿 /我", NOW)
    assert _joined_text(factory, "那是指令，不是人名。")

    # 正常目标不受影响，被拒的特殊目标不产生任何记录
    _receive(service, "c7", "user-0", "/凿 乙", NOW)
    assert _joined_text(factory, "【凿】甲凿了一下乙")
    with factory() as session:
        records = session.scalars(select(EstrusChopRecord)).all()
        assert len(records) == 1


def test_me_shows_birthday_and_gender_with_reminders():
    service, repository, factory = _service(estrus_random=_SeqRandom([]))
    _join(service, "j0", "user-0", "甲", NOW)

    _receive(service, "m0", "user-0", "/我", NOW)
    texts = _replies(factory)
    assert any(
        "生日：未设置，用 /设置生日 月-日 告诉人事吧" in text for text in texts
    )
    assert any(
        "性别：未设置，用 /设置性别 男 或 女 标记一下" in text for text in texts
    )

    _receive(service, "g1", "user-0", "/设置性别 女", NOW)
    _receive(service, "b1", "user-0", "/设置生日 12-25", NOW)
    _receive(service, "m1", "user-0", "/我", NOW)
    texts = _replies(factory)
    assert any("生日：12 月 25 日（还有" in text for text in texts)
    assert any("性别：女" in text for text in texts)
    # 顺序：工号 → 性别 → 生日 → 职位 → 部门 → 余额 → 活跃度 → 收益 → 打卡
    me_text = [
        text
        for text in texts
        if "工号：" in text and "今日活跃度：" in text
    ][-1]
    positions = [
        me_text.index("工号："),
        me_text.index("性别："),
        me_text.index("生日："),
        me_text.index("职位："),
        me_text.index("部门："),
        me_text.index("当前余额："),
        me_text.index("今日活跃度："),
        me_text.index("今日收益："),
        me_text.index("连续打卡："),
    ]
    assert positions == sorted(positions)


def test_set_gender_command():
    service, repository, factory = _service(estrus_random=_SeqRandom([]))
    _join(service, "j0", "user-0", "甲", NOW)

    _receive(service, "g1", "user-0", "/设置性别 女", NOW)
    assert _joined_text(factory, "已将你的性别设置为女。")
    info = repository.get_my_estrus("user-0", PRIMARY_GROUP_CHAT_ID, NOW)
    assert info["gender"] == "female"

    _receive(service, "g2", "user-0", "/修改性别 男", NOW)
    assert _joined_text(factory, "已将你的性别设置为男。")

    _receive(service, "g3", "user-0", "/设置性别 火箭", NOW)
    assert _joined_text(factory, "性别只能填 男 或 女。")

    _receive(service, "g4", "user-9", "/设置性别 男", NOW)
    assert _joined_text(factory, "请先用 /入职")


def test_climax_prompt_splits_by_gender():
    system_male, _ = build_climax_messages("小明", "male")
    system_female, _ = build_climax_messages("小红", "female")
    system_unknown, _ = build_climax_messages("小灰", "unknown")
    assert "男性员工" in system_male
    assert "女性员工" in system_female
    assert "性别未知" in system_unknown


def test_sync_platform_genders_fills_unknown_only():
    service, repository, factory = _service()
    _join(service, "j0", "user-0", "甲", NOW)
    _join(service, "j1", "user-1", "乙", NOW)
    repository.set_user_gender("user-0", "male")  # 显式档案优先

    updated = repository.sync_platform_genders(
        {
            "user-0": "female",
            "user-1": "female",
            "user-9": "male",
            "user-1x": "???",
        }
    )

    assert updated == 1
    assert repository.get_my_estrus("user-0", PRIMARY_GROUP_CHAT_ID, NOW)["gender"] == "male"
    assert repository.get_my_estrus("user-1", PRIMARY_GROUP_CHAT_ID, NOW)["gender"] == "female"


class _FakeClimaxClient:
    def __init__(self, text):
        self.text = text
        self.calls = []

    def complete(
        self, system_prompt, user_content, *, history_messages=(),
        max_chars, timeout_seconds, temperature=None,
    ):
        self.calls.append(
            {
                "system": system_prompt,
                "user": user_content,
                "max_chars": max_chars,
            }
        )
        return self.text


def test_climax_ai_text_merged_into_single_paragraph():
    # v3 质量门要求正文里有器官词 + 体液/拟声词，假文本按真实尺度给
    client = _FakeClimaxClient(
        "第一段：穴口被凿得又软又烫，穴肉一层层绞上来。"
        "\n\n第二段：汁水喷了一桌面，粘腻的水声还没停。\n第三段收尾。"
    )
    service, repository, factory = _service(
        estrus_random=_SeqRandom([0.90, 0.0] * 5), estrus_text_client=client
    )
    _join(service, "j0", "user-0", "甲", NOW)
    _join(service, "j1", "user-1", "乙", NOW)
    _configure_estrus_settings(
        repository,
        climax_threshold=10,
        heat_p0=50,
        heat_p1=30,
        heat_p2=20,
        coin_p0=50,
        coin_p1=30,
        coin_p2=20,
        chop_cooldown_seconds=0,
    )
    for index in range(5):
        _receive(
            service, f"c{index}", "user-0", "/凿 乙",
            NOW + timedelta(minutes=index),
        )

    assert client.calls, "AI client should be called on climax"
    assert client.calls[0]["max_chars"] == 1000
    # 凿者进入 prompt，可出场互动
    assert "最后一凿的人：甲" in client.calls[0]["user"]
    # 换行全部合并，整段单条发出
    assert not any("\n\n第二段：" in text for text in _replies(factory))
    assert any(
        "第一段：穴口被凿得又软又烫，穴肉一层层绞上来。"
        "第二段：汁水喷了一桌面，粘腻的水声还没停。第三段收尾。" in text
        for text in _replies(factory)
    )

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from dzmm_bot.core.estrus import build_climax_messages
from dzmm_bot.core.schema import PRIMARY_GROUP_CHAT_ID
from dzmm_bot.runtime.contracts import InboundMessage, MessageReference


BEIJING = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 10, 3, 15, 0, tzinfo=BEIJING)


class _SeqRandom:
    """按序列吐 random() 值：_roll_estrus_pair 每次凿消耗两个（先热后币）。"""

    def __init__(self, values):
        self.values = list(values)

    def random(self) -> float:
        if not self.values:
            return 0.0
        return self.values.pop(0)

    def choice(self, seq):
        return seq[0]


def _service(*, estrus_random=None):
    from dzmm_bot.core.commands import GroupCommandHandler
    from dzmm_bot.core.repository import CoreRepository
    from dzmm_bot.core.schema import Base
    from dzmm_bot.core.service import CoreService

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    repository = CoreRepository(factory, estrus_random=estrus_random)
    repository.bootstrap_primary_group(
        "https://www.aikda.com/chat?c=group-main", NOW
    )
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
    # 乙 = 甲的入职奖励 + 1 枚被凿币（两人入职奖励相同）
    assert _balance(factory, "user-1") == _balance(factory, "user-0") + 1


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
    repository.set_estrus_settings(
        enabled=True,
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
    )

    _receive(service, "c1", "user-0", "/凿 乙", NOW)
    _receive(
        service, "c2", "user-0", "/凿 丙", NOW + timedelta(seconds=5)
    )
    assert _joined_text(factory, "凿冷却中，请")


def test_my_estrus_and_ranking():
    service, repository, factory = _service(
        estrus_random=_SeqRandom([0.90, 0.60, 0.90, 0.60])
    )
    _join(service, "j0", "user-0", "甲", NOW)
    _join(service, "j1", "user-1", "乙", NOW)

    _receive(service, "c1", "user-0", "/凿 乙", NOW)
    _receive(service, "c2", "user-0", "/凿 乙", NOW + timedelta(minutes=1))

    _receive(service, "q1", "user-1", "/我的发情值", NOW)
    texts = _replies(factory)
    assert any("当前发情值：4" in text for text in texts)
    assert any("被凿次数：2" in text for text in texts)
    assert any("状态：允许被凿" in text for text in texts)

    _receive(service, "q2", "user-0", "/发情值排名", NOW)
    texts = _replies(factory)
    assert any("【发情值排名】" in text for text in texts)
    assert any("1. 乙 · 发情 4 · 被凿 2" in text for text in texts)


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

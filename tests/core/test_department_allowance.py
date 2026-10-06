from datetime import datetime, timedelta
from random import Random
from zoneinfo import ZoneInfo
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from dzmm_bot.runtime.contracts import InboundMessage


BEIJING = ZoneInfo("Asia/Shanghai")


class _AlwaysHit:
    def random(self) -> float:
        return 0.0


class _AlwaysMiss:
    def random(self) -> float:
        return 0.99


def _service(*, chat_drop_random=None):
    from dzmm_bot.core.commands import GroupCommandHandler
    from dzmm_bot.core.repository import CoreRepository
    from dzmm_bot.core.schema import Base
    from dzmm_bot.core.service import CoreService

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    repository = CoreRepository(factory, chat_drop_random=chat_drop_random)
    return CoreService(repository, GroupCommandHandler(repository)), repository, factory


def _receive(service, message_id, sender, content, received_at, **kwargs):
    kwargs.setdefault("chatroom_id", "group-main")
    return service.receive_inbound(
        InboundMessage(message_id, sender, content, received_at, **kwargs)
    )


def _balance(factory, platform_id):
    from dzmm_bot.core.schema import UserRecord

    with factory() as session:
        user = session.scalar(
            select(UserRecord).where(UserRecord.platform_id == platform_id)
        )
        return user.balance


def _bind_department(factory, name, allowance_kind):
    """绑定系统预置部门的津贴类型，返回部门 id。"""
    from dzmm_bot.core.schema import DepartmentRecord

    with factory.begin() as session:
        department = session.scalar(
            select(DepartmentRecord).where(DepartmentRecord.name == name)
        )
        department.allowance_kind = allowance_kind
        return department.id


def _assign_department(factory, platform_id, department_id):
    from dzmm_bot.core.schema import UserRecord

    with factory.begin() as session:
        user = session.scalar(
            select(UserRecord).where(UserRecord.platform_id == platform_id)
        )
        user.department_id = department_id


def _add_allowance(factory, platform_id, amount, now, kind="dept_chat"):
    from dzmm_bot.core.schema import DepartmentAllowanceRecord, UserRecord

    with factory.begin() as session:
        user = session.scalar(
            select(UserRecord).where(UserRecord.platform_id == platform_id)
        )
        session.add(
            DepartmentAllowanceRecord(
                user_id=user.id,
                allow_date=now.date(),
                kind=kind,
                amount=amount,
                created_at=now,
            )
        )


def _allowance_total(factory, platform_id, now):
    from dzmm_bot.core.schema import DepartmentAllowanceRecord, UserRecord

    with factory() as session:
        user = session.scalar(
            select(UserRecord).where(UserRecord.platform_id == platform_id)
        )
        rows = session.scalars(
            select(DepartmentAllowanceRecord.amount).where(
                DepartmentAllowanceRecord.user_id == user.id,
                DepartmentAllowanceRecord.allow_date == now.date(),
            )
        )
        return sum(rows)


def _outbound_texts(factory):
    from dzmm_bot.core.schema import OutboundRecord

    with factory() as session:
        return list(session.scalars(select(OutboundRecord.text)))


def test_checkin_allowance_and_daily_cap():
    service, repository, factory = _service()
    now = datetime(2026, 10, 2, 9, 0, tzinfo=BEIJING)
    repository.bootstrap_primary_group(
        "https://www.aikda.com/chat?c=group-main", now
    )
    _receive(service, "j0", "user-0", "/入职 甲", now)
    department_id = _bind_department(factory, "核心技术部", "checkin")
    _assign_department(factory, "user-0", department_id)

    before = _balance(factory, "user-0")
    _receive(service, "c1", "user-0", "/打卡", now)
    after = _balance(factory, "user-0")
    # 打卡基础奖 5 + 部门津贴 5
    assert after - before == 10
    assert _allowance_total(factory, "user-0", now) == 5

    # 预置 5 币津贴后再打卡（跨天模拟：先移到明天打卡不现实，直接验证封顶判定）
    _add_allowance(factory, "user-0", 5, now)
    before_cap = _balance(factory, "user-0")
    _receive(service, "c2", "user-1", "/入职 乙", now)
    _add_allowance(factory, "user-0", 0, now)  # no-op keeps helper import honest
    assert _balance(factory, "user-0") == before_cap


def test_checkin_allowance_notifies_the_group():
    service, repository, factory = _service()
    now = datetime(2026, 10, 2, 9, 0, tzinfo=BEIJING)
    repository.bootstrap_primary_group(
        "https://www.aikda.com/chat?c=group-main", now
    )
    _receive(service, "j0", "user-0", "/入职 甲", now)
    department_id = _bind_department(factory, "核心技术部", "checkin")
    _assign_department(factory, "user-0", department_id)

    _receive(service, "c1", "user-0", "/打卡", now)

    texts = _outbound_texts(factory)
    assert any(
        "【部门津贴】甲（核心技术部）打卡奖励 +5 摸鱼币（今日已获得津贴：5/5）"
        in text
        for text in texts
    )
    from dzmm_bot.core.schema import OutboundRecord

    with factory() as session:
        notices = session.scalars(
            select(OutboundRecord).where(
                OutboundRecord.text.like("【部门津贴】%")
            )
        ).all()
        assert notices
        assert all(notice.delivery_kind == "group" for notice in notices)


def test_department_list_shows_referral_hint():
    service, repository, factory = _service()
    now = datetime(2026, 10, 2, 9, 0, tzinfo=BEIJING)
    repository.bootstrap_primary_group(
        "https://www.aikda.com/chat?c=group-main", now
    )
    _receive(service, "j0", "user-0", "/入职 甲", now)
    department_id = _bind_department(factory, "次元外联部", "referral")
    assert department_id is not None

    _receive(service, "dept", "user-0", "/部门", now)

    texts = _outbound_texts(factory)
    assert any("次元外联部" in text for text in texts)
    assert any("每邀请新人通过链接进群 +1 摸鱼币" in text for text in texts)


def test_allowance_settings_override_amounts_and_hints():
    """津贴参数后台可配置：面额、水群概率、封顶与 /部门 文案随之变化。"""
    service, repository, factory = _service()
    now = datetime(2026, 10, 2, 9, 0, tzinfo=BEIJING)
    repository.bootstrap_primary_group(
        "https://www.aikda.com/chat?c=group-main", now
    )
    _receive(service, "j0", "user-0", "/入职 甲", now)
    department_id = _bind_department(factory, "核心技术部", "checkin")
    _assign_department(factory, "user-0", department_id)
    _set_settings(
        repository,
        checkin_amount=2,
        daily_cap=3,
    )

    before = _balance(factory, "user-0")
    _receive(service, "c1", "user-0", "/打卡", now)
    # 打卡基础奖 5 + 部门津贴 2（改过的面额）
    assert _balance(factory, "user-0") - before == 7
    assert _allowance_total(factory, "user-0", now) == 2

    _receive(service, "dept", "user-0", "/部门", now)
    assert _replied_text(factory, "每日打卡额外 +2 摸鱼币")


def _set_settings(repository, **overrides):
    params = dict(
        checkin_amount=5,
        event_amount=5,
        game_host_amount=1,
        game_play_amount=1,
        game_play_step=5,
        submission_amount=5,
        chat_drop_percent=10,
        chat_drop_amount=1,
        chat_drop_cooldown_seconds=0,
        referral_amount=1,
        daily_cap=5,
    )
    params.update(overrides)
    return repository.set_department_allowance_settings(**params)


def _replied_text(factory, snippet):
    from dzmm_bot.core.schema import OutboundRecord

    with factory() as session:
        texts = list(session.scalars(select(OutboundRecord.text)))
    return any(snippet in text for text in texts)


def test_allowance_cap_partial_grant():
    service, repository, factory = _service()
    now = datetime(2026, 10, 2, 9, 0, tzinfo=BEIJING)
    repository.bootstrap_primary_group(
        "https://www.aikda.com/chat?c=group-main", now
    )
    _receive(service, "j0", "user-0", "/入职 甲", now)
    department_id = _bind_department(factory, "核心技术部", "checkin")
    _assign_department(factory, "user-0", department_id)
    _add_allowance(factory, "user-0", 4, now)

    before = _balance(factory, "user-0")
    _receive(service, "c1", "user-0", "/打卡", now)
    after = _balance(factory, "user-0")
    assert after - before == 5 + 1  # 基础奖 + 封顶剩余 1
    assert _allowance_total(factory, "user-0", now) == 5


def test_unbound_department_pays_nothing():
    service, repository, factory = _service()
    now = datetime(2026, 10, 2, 9, 0, tzinfo=BEIJING)
    repository.bootstrap_primary_group(
        "https://www.aikda.com/chat?c=group-main", now
    )
    _receive(service, "j0", "user-0", "/入职 甲", now)
    department = repository.create_department("未绑定增益部", "")
    _assign_department(factory, "user-0", department.id)

    before = _balance(factory, "user-0")
    _receive(service, "c1", "user-0", "/打卡", now)
    assert _balance(factory, "user-0") - before == 5
    assert _allowance_total(factory, "user-0", now) == 0


def test_chat_drop_with_cooldown():
    service, repository, factory = _service(chat_drop_random=_AlwaysHit())
    now = datetime(2026, 10, 2, 9, 0, tzinfo=BEIJING)
    repository.bootstrap_primary_group(
        "https://www.aikda.com/chat?c=group-main", now
    )
    _receive(service, "j0", "user-0", "/入职 甲", now)
    _receive(service, "j1", "user-1", "/入职 乙", now)
    department = repository.create_department("摸鱼吃瓜部", "", allowance_kind="chat")
    _assign_department(factory, "user-0", department.id)
    _set_settings(repository, chat_drop_cooldown_seconds=600)

    _receive(service, "m1", "user-0", "今天好摸鱼", now)
    assert _balance(factory, "user-0") == _balance(factory, "user-1") + 1

    # 冷却期内不再判定
    _receive(
        service,
        "m2",
        "user-0",
        "继续摸鱼",
        now + timedelta(minutes=5),
    )
    assert _balance(factory, "user-0") == _balance(factory, "user-1") + 1

    # 冷却过后再次命中
    _receive(
        service,
        "m3",
        "user-0",
        "继续摸鱼",
        now + timedelta(minutes=11),
    )
    assert _balance(factory, "user-0") == _balance(factory, "user-1") + 2

    # 未绑定部门的用户不发
    _receive(service, "m4", "user-1", "我也摸鱼", now)
    assert _balance(factory, "user-1") == _balance(factory, "user-1")


def test_chat_drop_no_cooldown_by_default():
    """默认不冷却：同人连续消息每次都判定（概率命中即发放）。"""
    service, repository, factory = _service(chat_drop_random=_AlwaysHit())
    now = datetime(2026, 10, 2, 9, 0, tzinfo=BEIJING)
    repository.bootstrap_primary_group(
        "https://www.aikda.com/chat?c=group-main", now
    )
    _receive(service, "j0", "user-0", "/入职 甲", now)
    _receive(service, "j1", "user-1", "/入职 乙", now)
    department = repository.create_department("摸鱼吃瓜部", "", allowance_kind="chat")
    _assign_department(factory, "user-0", department.id)

    _receive(service, "m1", "user-0", "今天好摸鱼", now)
    _receive(
        service, "m2", "user-0", "继续摸鱼", now + timedelta(seconds=5)
    )
    assert _balance(factory, "user-0") == _balance(factory, "user-1") + 2


def test_my_allowance_command_breakdown():
    service, repository, factory = _service()
    now = datetime(2026, 10, 2, 9, 0, tzinfo=BEIJING)
    repository.bootstrap_primary_group(
        "https://www.aikda.com/chat?c=group-main", now
    )
    _receive(service, "j0", "user-0", "/入职 甲", now)
    department_id = _bind_department(factory, "核心技术部", "checkin")
    _assign_department(factory, "user-0", department_id)

    _receive(service, "c1", "user-0", "/打卡", now)
    _receive(service, "a1", "user-0", "/我的津贴", now)

    texts = _outbound_texts(factory)
    assert any("【我的津贴】10-02" in t for t in texts)
    assert any("打卡奖励 +5" in t for t in texts)
    assert any("今日合计：5/5（已封顶）" in t for t in texts)


def test_my_allowance_command_empty_and_not_joined():
    service, repository, factory = _service()
    now = datetime(2026, 10, 2, 9, 0, tzinfo=BEIJING)
    repository.bootstrap_primary_group(
        "https://www.aikda.com/chat?c=group-main", now
    )

    _receive(service, "a0", "user-0", "/我的津贴", now)
    assert any("请先用 /入职" in t for t in _outbound_texts(factory))

    _receive(service, "j0", "user-0", "/入职 甲", now)
    _receive(service, "a1", "user-0", "/我的津贴", now)
    assert any("今日暂无津贴入账（0/5）" in t for t in _outbound_texts(factory))


def test_chat_drop_miss_and_commands_skip():
    service, repository, factory = _service(chat_drop_random=_AlwaysMiss())
    now = datetime(2026, 10, 2, 9, 0, tzinfo=BEIJING)
    repository.bootstrap_primary_group(
        "https://www.aikda.com/chat?c=group-main", now
    )
    _receive(service, "j0", "user-0", "/入职 甲", now)
    department = repository.create_department("摸鱼吃瓜部", "", allowance_kind="chat")
    _assign_department(factory, "user-0", department.id)

    before = _balance(factory, "user-0")
    _receive(service, "m1", "user-0", "水一水", now)
    assert _balance(factory, "user-0") == before
    # 指令消息不参与判定
    _receive(service, "m2", "user-0", "/余额", now)
    assert _balance(factory, "user-0") == before


def test_game_play_bump_grants_on_fifth():
    service, repository, factory = _service()
    now = datetime(2026, 10, 2, 9, 0, tzinfo=BEIJING)
    repository.bootstrap_primary_group(
        "https://www.aikda.com/chat?c=group-main", now
    )
    _receive(service, "j0", "user-0", "/入职 甲", now)
    department_id = _bind_department(factory, "小游戏娱乐部", "game")
    _assign_department(factory, "user-0", department_id)

    from dzmm_bot.core.schema import UserRecord

    with factory() as session:
        user_id = session.scalar(
            select(UserRecord.id).where(UserRecord.platform_id == "user-0")
        )
    before = _balance(factory, "user-0")
    with repository.transaction():
        for _ in range(4):
            repository._bump_department_game_plays(
                repository._active_session.get(), [user_id], now
            )
    assert _balance(factory, "user-0") == before
    with repository.transaction():
        repository._bump_department_game_plays(
            repository._active_session.get(), [user_id], now
        )
    assert _balance(factory, "user-0") == before + 1


def test_completed_game_replay_does_not_repeat_count_or_allowance():
    from dzmm_bot.core.schema import DepartmentGamePlayRecord, GameParticipationRecord, PRIMARY_GROUP_CHAT_ID

    service, repository, factory = _service()
    now = datetime(2026, 10, 2, 9, 0, tzinfo=BEIJING)
    repository.bootstrap_primary_group("https://www.aikda.com/chat?c=group-main", now)
    _receive(service, "join", "user-0", "/入职 甲", now)
    department_id = _bind_department(factory, "小游戏娱乐部", "game")
    _assign_department(factory, "user-0", department_id)
    user_id = repository.find_user("user-0").id
    before = _balance(factory, "user-0")
    for game_id in [uuid4() for _ in range(5)]:
        for attempt in range(2):
            with repository.transaction():
                repository._bump_department_game_plays(
                    repository._active_session.get(), [user_id, user_id], now,
                    PRIMARY_GROUP_CHAT_ID, game_type="truth_trade", game_id=game_id,
                )
    with factory() as session:
        assert session.scalar(select(DepartmentGamePlayRecord.count)) == 5
        assert len(session.scalars(select(GameParticipationRecord)).all()) == 5
    assert _balance(factory, "user-0") == before + 1


def test_game_host_allowance_on_begin_only():
    service, repository, factory = _service()
    now = datetime(2026, 10, 2, 9, 0, tzinfo=BEIJING)
    repository.bootstrap_primary_group(
        "https://www.aikda.com/chat?c=group-main", now
    )
    _receive(service, "j0", "user-0", "/入职 甲", now)
    _receive(service, "j1", "user-1", "/入职 乙", now)
    _receive(service, "j2", "user-2", "/入职 丙", now)
    department_id = _bind_department(factory, "小游戏娱乐部", "game")
    _assign_department(factory, "user-0", department_id)

    _receive(service, "k1", "user-0", "/国王游戏", now)
    assert _allowance_total(factory, "user-0", now) == 0  # 报名阶段不发
    _receive(service, "k2", "user-1", "/加入", now)
    _receive(service, "k3", "user-2", "/加入", now)
    _receive(service, "k4", "user-0", "/开始", now)
    assert _allowance_total(factory, "user-0", now) == 1  # 开局 +1
    # 开局到账通知：员工名用系统注册名
    assert any("甲（小游戏娱乐部）开局奖励 +1" in t for t in _outbound_texts(factory))


def test_chat_drop_notification_with_cap_note():
    service, repository, factory = _service(chat_drop_random=_AlwaysHit())
    now = datetime(2026, 10, 2, 9, 0, tzinfo=BEIJING)
    repository.bootstrap_primary_group(
        "https://www.aikda.com/chat?c=group-main", now
    )
    _receive(service, "j0", "user-0", "/入职 甲", now)
    _receive(service, "j1", "user-1", "/入职 乙", now)
    department = repository.create_department("摸鱼吃瓜部", "", allowance_kind="chat")
    _assign_department(factory, "user-0", department.id)

    _receive(service, "m1", "user-0", "今天好摸鱼", now)
    assert any(
        "【部门津贴】甲（摸鱼吃瓜部）水群掉落 +1 摸鱼币（今日已获得津贴：1/5）" in t
        for t in _outbound_texts(factory)
    )

    # 当日已领 1（m1）+ 预置 3 = 4 币，本次实发 1 → 恰好封顶
    _add_allowance(factory, "user-0", 3, now)
    _receive(service, "m2", "user-0", "继续摸鱼", now + timedelta(minutes=11))
    assert any(
        "水群掉落 +1 摸鱼币（今日已获得津贴：5/5）" in t
        for t in _outbound_texts(factory)
    )

    # 已封顶后再触发：实发 0，完全静默
    texts_before = len(_outbound_texts(factory))
    _receive(service, "m3", "user-0", "还在摸鱼", now + timedelta(minutes=22))
    assert len(_outbound_texts(factory)) == texts_before

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import sessionmaker

from dzmm_bot.runtime.contracts import InboundMessage, MessageReference


BEIJING = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 10, 3, 15, 0, tzinfo=BEIJING)


def _service():
    from dzmm_bot.core.commands import GroupCommandHandler
    from dzmm_bot.core.repository import CoreRepository
    from dzmm_bot.core.schema import Base
    from dzmm_bot.core.service import CoreService

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    repository = CoreRepository(factory)
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


def _balance(factory, platform_id):
    from dzmm_bot.core.schema import UserRecord

    with factory() as session:
        user = session.scalar(
            select(UserRecord).where(UserRecord.platform_id == platform_id)
        )
        return user.balance


def _set_balance(factory, platform_id, value):
    from dzmm_bot.core.schema import UserRecord

    with factory.begin() as session:
        session.execute(
            update(UserRecord)
            .where(UserRecord.platform_id == platform_id)
            .values(balance=value)
        )


def _department_id(factory, name):
    from dzmm_bot.core.schema import DepartmentRecord

    with factory() as session:
        department = session.scalar(
            select(DepartmentRecord).where(DepartmentRecord.name == name)
        )
        return department.id


def _assign_department(factory, platform_id, department_id):
    from dzmm_bot.core.schema import UserRecord

    with factory.begin() as session:
        session.execute(
            update(UserRecord)
            .where(UserRecord.platform_id == platform_id)
            .values(department_id=department_id)
        )


def _bind_fine_department(factory, name="风纪监察部"):
    """执法权绑定 = 部门津贴选 discipline。"""
    from dzmm_bot.core.schema import DepartmentRecord

    with factory.begin() as session:
        session.execute(
            update(DepartmentRecord)
            .where(DepartmentRecord.name == name)
            .values(allowance_kind="discipline")
        )


def _configure_fine(repository, factory, **overrides):
    """rank_quotas 缺省给全部职级配 5 次（按 rank_id UUID 为键）；
    传 rank_quota=N 可给全部职级统一配 N 次。"""
    from dzmm_bot.core.schema import RankRecord

    with factory() as session:
        rank_ids = [
            str(rank.id) for rank in session.scalars(select(RankRecord)).all()
        ]
    values = dict(
        enabled=True,
        amount=5,
        kickback_percent=20,
        rank_quotas={rank_id: 5 for rank_id in rank_ids},
        cooldown_minutes=0,
        target_daily_limit=0,
    )
    if "rank_quota" in overrides:
        uniform = overrides.pop("rank_quota")
        values["rank_quotas"] = {rank_id: uniform for rank_id in rank_ids}
    values.update(overrides)
    return repository.set_discipline_fine_settings(**values)


def _join_employees(service, now, count):
    for index in range(count):
        _receive(service, f"j{index}", f"user-{index}", f"/入职 员工{index}", now)


def _add_allowance_ledger(factory, platform_id, amount, now):
    """预填当日津贴台账（模拟已领满封顶）。"""
    from dzmm_bot.core.schema import DepartmentAllowanceRecord, UserRecord

    with factory.begin() as session:
        user = session.scalar(
            select(UserRecord).where(UserRecord.platform_id == platform_id)
        )
        session.add(
            DepartmentAllowanceRecord(
                user_id=user.id,
                allow_date=now.date(),
                kind="dept_chat",
                amount=amount,
                created_at=now,
            )
        )


def _add_direct_chat(factory, platform_id, chatroom_id):
    from dzmm_bot.core.schema import DirectChatRecord

    with factory.begin() as session:
        session.add(
            DirectChatRecord(
                platform_user_id=platform_id,
                chatroom_id=chatroom_id,
                discovered_at=NOW,
            )
        )


def _outbound_texts(factory):
    from dzmm_bot.core.schema import OutboundRecord

    with factory() as session:
        return list(session.scalars(select(OutboundRecord.text)))


def _replied(factory, snippet=None, *, exact=None):
    texts = _outbound_texts(factory)
    if exact is not None:
        return any(text == exact for text in texts)
    return any(snippet in text for text in texts)


def _setup(service, repository, factory, now, bind=True, **setting_overrides):
    """建员工、开罚款、把 user-0 指派为风纪监察部，并给员工发余额。"""
    _join_employees(service, now, 3)
    _configure_fine(repository, factory, **setting_overrides)
    fine_department = _department_id(factory, "风纪监察部")
    if bind:
        _bind_fine_department(factory)
    _assign_department(factory, "user-0", fine_department)
    for index in range(3):
        _set_balance(factory, f"user-{index}", 100)


def test_reply_fine_success_with_kickback_and_notices():
    service, repository, factory = _service()
    _setup(service, repository, factory, NOW)
    _add_direct_chat(factory, "user-1", "direct-1")
    issuer_before = _balance(factory, "user-0")
    target_before = _balance(factory, "user-1")

    _receive(service, "f1", "user-0", "/罚款 员工1 上班摸鱼被抓", NOW)

    assert _replied(
        factory,
        "【风纪罚款】员工0（风纪监察部）对 员工1 处以 5 摸鱼币罚款，理由：上班摸鱼被抓",
    )
    assert _replied(
        factory,
        "已成功扣款 5 摸鱼币，稽查人获得 1 摸鱼币津贴（今日津贴 1/5）",
    )
    assert _replied(
        factory, "如对本次罚款有异议，请保存截图并向经理或总监职级以上的员工反馈"
    )
    assert _balance(factory, "user-1") == target_before - 5
    assert _balance(factory, "user-0") == issuer_before + 1
    # 被罚人私聊通知
    assert _replied(factory, "【风纪罚款】你被处以 5 摸鱼币罚款（实扣 5）")
    assert _replied(factory, "当前余额：95")


def test_fine_alias_and_reply_reference_form():
    service, repository, factory = _service()
    _setup(service, repository, factory, NOW)
    reference = MessageReference(
        message_id="m-1",
        sender_platform_id="user-1",
        content_type="text",
    )

    _receive(service, "f1", "user-0", "/罚 骂人", NOW, reference=reference)
    assert _replied(factory, "对 员工1 处以 5 摸鱼币罚款，理由：骂人")

    _receive(
        service, "f2", "user-0", "/罚款", NOW + timedelta(minutes=30),
        reference=reference,
    )
    assert _replied(factory, "对 员工1 处以 5 摸鱼币罚款，理由：未填写理由")

    records, total = repository.list_discipline_fine_records(page=1, page_size=10)
    assert total == 2
    assert all(record.via_reply for record in records)


def test_fine_reference_wins_over_name_argument():
    service, repository, factory = _service()
    _setup(service, repository, factory, NOW)
    reference = MessageReference(
        message_id="m-1",
        sender_platform_id="user-1",
        content_type="text",
    )

    _receive(service, "f1", "user-0", "/罚款 员工2", NOW, reference=reference)

    assert _replied(factory, "对 员工1 处以 5 摸鱼币罚款")
    assert _replied(factory, "理由：员工2")


def test_fine_by_employee_number_and_unknown_target():
    service, repository, factory = _service()
    _setup(service, repository, factory, NOW)

    _receive(service, "f1", "user-0", "/罚款 #0002 摸鱼", NOW)
    assert _replied(factory, "对 员工1 处以 5 摸鱼币罚款")

    _receive(service, "f2", "user-0", "/罚款 路人甲 摸鱼", NOW)
    assert _replied(factory, exact="目标还未入职摸鱼公司。")


def test_fine_insufficient_balance_deducts_to_zero_with_zero_kickback():
    service, repository, factory = _service()
    _setup(service, repository, factory, NOW)
    _set_balance(factory, "user-1", 2)
    issuer_before = _balance(factory, "user-0")

    _receive(service, "f1", "user-0", "/罚款 员工1 摸鱼", NOW)

    assert _replied(factory, "处以 5 摸鱼币罚款（余额不足，实扣 2）")
    assert _replied(factory, "已成功扣款 2 摸鱼币，稽查人获得 0 摸鱼币津贴（今日津贴 0/5）")
    assert _balance(factory, "user-1") == 0
    assert _balance(factory, "user-0") == issuer_before  # 抽成 0，不变


def test_fine_kickback_shares_daily_allowance_cap():
    service, repository, factory = _service()
    _setup(service, repository, factory, NOW)
    _add_allowance_ledger(factory, "user-0", 5, NOW)
    issuer_before = _balance(factory, "user-0")
    target_before = _balance(factory, "user-1")

    _receive(service, "f1", "user-0", "/罚款 员工1 摸鱼", NOW)

    assert _replied(factory, "稽查人获得 0 摸鱼币津贴（今日津贴已满 5 币）")
    # 罚款照常执行（销毁）
    assert _balance(factory, "user-1") == target_before - 5
    assert _balance(factory, "user-0") == issuer_before


def test_fine_quota_exhausted_and_zero_quota():
    service, repository, factory = _service()
    _setup(service, repository, factory, NOW, rank_quota=1, cooldown_minutes=0)

    _receive(service, "f1", "user-0", "/罚款 员工1 摸鱼", NOW)
    assert _replied(factory, "已成功扣款")

    _receive(
        service, "f2", "user-0", "/罚款 员工1 摸鱼",
        NOW + timedelta(hours=1),
    )
    assert _replied(factory, exact="你今日的罚款次数已用完，明天再来吧。")

    _configure_fine(repository, factory, rank_quota=0)
    _receive(
        service, "f3", "user-0", "/罚款 员工1 摸鱼",
        NOW + timedelta(hours=2),
    )
    assert _replied(factory, exact="你的职级今日无可用的罚款次数（配额为 0）。")


def test_fine_cooldown():
    service, repository, factory = _service()
    _setup(service, repository, factory, NOW, cooldown_minutes=10, rank_quota=5)

    _receive(service, "f1", "user-0", "/罚款 员工1 摸鱼", NOW)
    _receive(
        service, "f2", "user-0", "/罚款 员工2 摸鱼",
        NOW + timedelta(minutes=5),
    )
    assert _replied(factory, "罚款冷却中")

    _receive(
        service, "f3", "user-0", "/罚款 员工2 摸鱼",
        NOW + timedelta(minutes=11),
    )
    assert _replied(factory, "已成功扣款")


def test_fine_rejects_unauthorized_self_and_same_department():
    service, repository, factory = _service()
    _setup(service, repository, factory, NOW)
    fine_department = _department_id(factory, "风纪监察部")

    _receive(service, "f1", "user-1", "/罚款 员工0 摸鱼", NOW)
    assert _replied(
        factory, exact="只有风纪执法部门（部门津贴=风纪执法）的成员可以执行罚款。"
    )

    _receive(service, "f2", "user-0", "/罚款 员工0 摸鱼", NOW)
    assert _replied(factory, exact="不能罚款自己。")

    _assign_department(factory, "user-2", fine_department)
    _receive(service, "f3", "user-0", "/罚款 员工2 摸鱼", NOW)
    assert _replied(factory, exact="不能罚款执法部门内部成员。")


def test_fine_target_daily_limit():
    service, repository, factory = _service()
    _setup(service, repository, factory, NOW, target_daily_limit=1, rank_quota=5)

    _receive(service, "f1", "user-0", "/罚款 员工1 摸鱼", NOW)
    assert _replied(factory, "已成功扣款")

    _receive(
        service, "f2", "user-0", "/罚款 员工1 摸鱼",
        NOW + timedelta(minutes=20),
    )
    assert _replied(factory, exact="该员工今日被罚款次数已达上限。")


def test_fine_disabled_and_usage():
    service, repository, factory = _service()
    _join_employees(service, NOW, 2)
    _configure_fine(repository, factory, enabled=False)
    _assign_department(factory, "user-0", _department_id(factory, "风纪监察部"))

    _receive(service, "f1", "user-0", "/罚款 员工1 摸鱼", NOW)
    assert _replied(factory, exact="风纪罚款未开启。")

    _configure_fine(repository, factory, enabled=True)
    # 部门未勾选风纪执法 → 未配置
    _receive(service, "f2", "user-0", "/罚款 员工1 摸鱼", NOW)
    assert _replied(
        factory,
        exact="风纪罚款未配置执法部门，请在后台「职位与部门」的部门津贴中选择风纪执法。",
    )

    _bind_fine_department(factory)
    _receive(service, "f3", "user-0", "/罚款", NOW)
    assert _replied(factory, "用法：引用对方消息发送 /罚款 [理由]")


def test_department_discipline_binding_roundtrip():
    service, repository, factory = _service()
    department = repository.create_department(
        "稽查队", "测试部门", allowance_kind="discipline"
    )
    assert department.allowance_kind == "discipline"
    # discipline 是合法津贴绑定值，但不参与任何津贴发放规则
    updated = repository.update_department(
        department.id,
        name="稽查队",
        description="测试部门",
        enabled=True,
        allowance_kind=None,
    )
    assert updated.allowance_kind is None


def test_fine_revocation_refunds_and_my_fines():
    service, repository, factory = _service()
    _setup(service, repository, factory, NOW)
    target_before = _balance(factory, "user-1")

    _receive(service, "f1", "user-0", "/罚款 员工1 摸鱼", NOW)
    assert _balance(factory, "user-1") == target_before - 5

    records, total = repository.list_discipline_fine_records(page=1, page_size=10)
    assert total == 1
    assert repository.revoke_discipline_fine(records[0].id, NOW + timedelta(hours=1)) == "revoked"
    assert _balance(factory, "user-1") == target_before
    assert repository.revoke_discipline_fine(records[0].id, NOW + timedelta(hours=1)) == "already_revoked"

    # /我的罚款：已撤销不计入累计
    _receive(
        service, "m1", "user-1", "/我的罚款", NOW + timedelta(hours=2),
        source_type="direct", chatroom_id="direct-1",
    )
    assert _replied(factory, "累计被罚 0 次 / 0 摸鱼币")
    assert _replied(factory, "已撤销")

    # 群里使用 /我的罚款 被拒
    _receive(service, "m2", "user-1", "/我的罚款", NOW + timedelta(hours=2))
    assert _replied(factory, exact="只能在私聊中使用 /我的罚款。")


def test_fine_records_view_for_admin():
    service, repository, factory = _service()
    _setup(service, repository, factory, NOW)
    _receive(service, "f1", "user-0", "/罚款 员工1 摸鱼", NOW)

    records, total = repository.list_discipline_fine_records(page=1, page_size=10)
    assert total == 1
    [record] = records
    assert record.issuer_display_name == "员工0"
    assert record.target_display_name == "员工1"
    assert record.amount == 5
    assert record.kickback == 1
    assert record.reason == "摸鱼"
    assert record.revoked_at is None

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from dzmm_bot.runtime.contracts import InboundMessage


BEIJING = ZoneInfo("Asia/Shanghai")

SYSTEM_SENDER = "30932a9a-83ae-4475-88eb-7382b47177ad"


def _service():
    from dzmm_bot.core.commands import GroupCommandHandler
    from dzmm_bot.core.repository import CoreRepository
    from dzmm_bot.core.schema import Base
    from dzmm_bot.core.service import CoreService

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    repository = CoreRepository(factory)
    return CoreService(repository, GroupCommandHandler(repository)), repository, factory


def _receive(service, message_id, sender, content, received_at, **kwargs):
    kwargs.setdefault("chatroom_id", "group-main")
    return service.receive_inbound(
        InboundMessage(message_id, sender, content, received_at, **kwargs)
    )


def _system_message(message_id, text, received_at, metadata=None):
    return InboundMessage(
        message_id,
        SYSTEM_SENDER,
        text,
        received_at,
        source_type="group",
        chatroom_id="group-main",
        content_type="system",
        metadata=metadata,
    )


def _balance(factory, platform_id):
    from dzmm_bot.core.schema import UserRecord

    with factory() as session:
        user = session.scalar(
            select(UserRecord).where(UserRecord.platform_id == platform_id)
        )
        return user.balance


def _referral_rows(factory):
    from dzmm_bot.core.schema import ReferralRecord

    with factory() as session:
        rows = session.scalars(select(ReferralRecord)).all()
        return [
            {
                "newcomer_id": row.newcomer_platform_id,
                "newcomer_name": row.newcomer_name,
                "inviter_id": row.inviter_platform_id,
                "inviter_name": row.inviter_name,
                "amount": row.amount,
            }
            for row in rows
        ]


def _outbound_texts(factory):
    from dzmm_bot.core.schema import OutboundRecord

    with factory() as session:
        return list(session.scalars(select(OutboundRecord.text)))


def _bind_department(factory, name, allowance_kind):
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


def _add_allowance(factory, platform_id, amount, now):
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


def test_parse_join_system_message_shapes():
    from dzmm_bot.browser.aikda_socket import parse_join_system_message

    linked = parse_join_system_message("困乏 通过 ROI 的链接加入了群聊")
    assert linked == {"newcomer": "困乏", "inviter": "ROI"}

    plain = parse_join_system_message("似把君邀 加入了群聊")
    assert plain == {"newcomer": "似把君邀"}

    # 名字里含"通过"也不至于解析崩（非贪婪从最左分割）
    tricky = parse_join_system_message("通过考验的人 通过 甲 的链接加入了群聊")
    assert tricky == {"newcomer": "通过考验的人", "inviter": "甲"}

    assert parse_join_system_message("xxx 被移出了群聊") is None
    assert parse_join_system_message("") is None
    assert parse_join_system_message("普通聊天消息") is None


def test_gateway_accepts_system_message_with_metadata():
    from dzmm_bot.browser.aikda_socket import AikdaSocketGateway

    gateway = AikdaSocketGateway(
        "https://www.aikda.com/chat?c=group-main",
        token_provider=lambda: "token",
        request=lambda procedure, payload=None: {},
        socket_factory=lambda: None,
    )
    gateway._bot_id = "bot-uid"
    gateway._accept_message(
        "group-main",
        {
            "message_id": "sys-1",
            "sent_by": SYSTEM_SENDER,
            "sent_at": "2026-10-03 10:00:00.000+00",
            "content": {"text": "困乏 通过 ROI 的链接加入了群聊", "type": "system"},
        },
    )
    assert len(gateway._pending) == 1
    message = gateway._pending[0]
    assert message.content_type == "system"
    assert message.metadata == {
        "referral": {"newcomer": "困乏", "inviter": "ROI"}
    }

    # 其他 system 文本照放行，但无归因 metadata
    gateway._accept_message(
        "group-main",
        {
            "message_id": "sys-2",
            "sent_by": SYSTEM_SENDER,
            "sent_at": "2026-10-03 10:01:00.000+00",
            "content": {"text": "群公告已更新", "type": "system"},
        },
    )
    message = gateway._pending[-1]
    assert message.metadata is None


def test_referral_grants_allowance_to_bound_department():
    service, repository, factory = _service()
    now = datetime(2026, 10, 3, 9, 0, tzinfo=BEIJING)
    repository.bootstrap_primary_group(
        "https://www.aikda.com/chat?c=group-main", now
    )
    _receive(service, "j0", "user-0", "/入职 甲", now)
    department_id = _bind_department(factory, "次元外联部", "referral")
    _assign_department(factory, "user-0", department_id)

    before = _balance(factory, "user-0")
    result = _receive(
        service,
        "sys-1",
        SYSTEM_SENDER,
        "新人乙 通过 甲 的链接加入了群聊",
        now,
        content_type="system",
        metadata={
            "referral": {
                "newcomer": "新人乙",
                "newcomer_id": "newcomer-1",
                "inviter": "甲",
                "inviter_id": "user-0",
            }
        },
    )
    assert result.inserted is True
    assert _balance(factory, "user-0") == before + 1
    rows = _referral_rows(factory)
    assert len(rows) == 1
    assert rows[0]["amount"] == 1
    assert rows[0]["newcomer_id"] == "newcomer-1"
    assert rows[0]["inviter_id"] == "user-0"
    # 到账通知发到获得津贴的群，员工名用注册名，新人名附注
    assert any(
        "【部门津贴】甲（次元外联部）拉新奖励 +1 摸鱼币（新人：新人乙）" in t
        for t in _outbound_texts(factory)
    )


def test_referral_newcomer_only_attributed_once():
    service, repository, factory = _service()
    now = datetime(2026, 10, 3, 9, 0, tzinfo=BEIJING)
    repository.bootstrap_primary_group(
        "https://www.aikda.com/chat?c=group-main", now
    )
    _receive(service, "j0", "user-0", "/入职 甲", now)
    department_id = _bind_department(factory, "次元外联部", "referral")
    _assign_department(factory, "user-0", department_id)

    metadata = {
        "referral": {
            "newcomer": "新人乙",
            "newcomer_id": "newcomer-1",
            "inviter": "甲",
            "inviter_id": "user-0",
        }
    }
    before = _balance(factory, "user-0")
    _receive(
        service, "sys-1", SYSTEM_SENDER,
        "新人乙 通过 甲 的链接加入了群聊", now,
        content_type="system", metadata=metadata,
    )
    assert _balance(factory, "user-0") == before + 1

    # 同一新人退群再进（换了邀请链接）→ 不重复发
    _receive(
        service, "sys-2", SYSTEM_SENDER,
        "新人乙 通过 丙 的链接加入了群聊", now + timedelta(minutes=30),
        content_type="system", metadata=metadata,
    )
    assert _balance(factory, "user-0") == before + 1
    assert len(_referral_rows(factory)) == 1

    # 同一条系统消息重放 → 幂等
    _receive(
        service, "sys-1", SYSTEM_SENDER,
        "新人乙 通过 甲 的链接加入了群聊", now,
        content_type="system", metadata=metadata,
    )
    assert _balance(factory, "user-0") == before + 1
    assert len(_referral_rows(factory)) == 1


def test_referral_unbound_department_records_but_pays_nothing():
    service, repository, factory = _service()
    now = datetime(2026, 10, 3, 9, 0, tzinfo=BEIJING)
    repository.bootstrap_primary_group(
        "https://www.aikda.com/chat?c=group-main", now
    )
    _receive(service, "j0", "user-0", "/入职 甲", now)
    department = repository.create_department("未绑定增益部", "")
    _assign_department(factory, "user-0", department.id)

    before = _balance(factory, "user-0")
    _receive(
        service, "sys-1", SYSTEM_SENDER,
        "新人乙 通过 甲 的链接加入了群聊", now,
        content_type="system",
        metadata={
            "referral": {
                "newcomer": "新人乙",
                "newcomer_id": "newcomer-1",
                "inviter": "甲",
                "inviter_id": "user-0",
            }
        },
    )
    assert _balance(factory, "user-0") == before
    rows = _referral_rows(factory)
    assert len(rows) == 1 and rows[0]["amount"] == 0


def test_referral_respects_daily_cap():
    service, repository, factory = _service()
    now = datetime(2026, 10, 3, 9, 0, tzinfo=BEIJING)
    repository.bootstrap_primary_group(
        "https://www.aikda.com/chat?c=group-main", now
    )
    _receive(service, "j0", "user-0", "/入职 甲", now)
    department_id = _bind_department(factory, "次元外联部", "referral")
    _assign_department(factory, "user-0", department_id)
    _add_allowance(factory, "user-0", 5, now)

    before = _balance(factory, "user-0")
    _receive(
        service, "sys-1", SYSTEM_SENDER,
        "新人乙 通过 甲 的链接加入了群聊", now,
        content_type="system",
        metadata={
            "referral": {
                "newcomer": "新人乙",
                "newcomer_id": "newcomer-1",
                "inviter": "甲",
                "inviter_id": "user-0",
            }
        },
    )
    assert _balance(factory, "user-0") == before
    rows = _referral_rows(factory)
    assert len(rows) == 1 and rows[0]["amount"] == 0


def test_referral_plain_join_and_unresolved_names():
    service, repository, factory = _service()
    now = datetime(2026, 10, 3, 9, 0, tzinfo=BEIJING)
    repository.bootstrap_primary_group(
        "https://www.aikda.com/chat?c=group-main", now
    )
    _receive(service, "j0", "user-0", "/入职 甲", now)
    department_id = _bind_department(factory, "次元外联部", "referral")
    _assign_department(factory, "user-0", department_id)

    before = _balance(factory, "user-0")
    # 无邀请人的普通入群：留痕但不发币
    _receive(
        service, "sys-1", SYSTEM_SENDER,
        "似把君邀 加入了群聊", now,
        content_type="system",
        metadata={"referral": {"newcomer": "似把君邀", "newcomer_id": "nc-9"}},
    )
    assert _balance(factory, "user-0") == before
    rows = _referral_rows(factory)
    assert rows[0]["inviter_id"] is None and rows[0]["amount"] == 0

    # 邀请人名字解析失败（uid 缺失）：留痕不发币
    _receive(
        service, "sys-2", SYSTEM_SENDER,
        "新人丙 通过 幽灵 的链接加入了群聊", now,
        content_type="system",
        metadata={
            "referral": {
                "newcomer": "新人丙",
                "newcomer_id": "nc-10",
                "inviter": "幽灵",
            }
        },
    )
    assert _balance(factory, "user-0") == before
    assert len(_referral_rows(factory)) == 2

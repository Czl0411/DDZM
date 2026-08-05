from zoneinfo import ZoneInfo

from dzmm_bot.runtime.contracts import InboundMessage

from .reply_templates import render_template, template_definition
from .repository import CoreRepository


_BEIJING = ZoneInfo("Asia/Shanghai")
_COMMANDS = {
    "/入职", "/我的物品", "/打卡", "/余额", "/我", "/商店", "/帮助", "/加入", "/退出"
}


class GroupCommandHandler:
    def __init__(self, repository: CoreRepository) -> None:
        self._repository = repository

    def handle(self, message: InboundMessage) -> str | None:
        content = message.content.strip()
        if not content:
            return None
        command = content.split(maxsplit=1)[0]
        if command == "/me":
            command = "/我"
        if command not in _COMMANDS:
            return None
        self._repository.ensure_command_definitions()
        if not self._repository.is_command_enabled(command):
            return None
        received_at = message.received_at.astimezone(_BEIJING)
        if command == "/入职":
            return self._join(message.sender_platform_id, content, received_at)
        if command == "/打卡":
            return self._check_in(message.sender_platform_id, received_at)
        if command == "/余额":
            return self._balance(message.sender_platform_id, received_at)
        if command == "/我":
            return self._me(message.sender_platform_id, received_at)
        if command == "/我的物品":
            return self._inventory(message.sender_platform_id, received_at)
        if command == "/商店":
            return self._shop(received_at)
        if command == "/加入":
            return self._event_join(message.sender_platform_id, content, received_at)
        if command == "/退出":
            return self._event_leave(message.sender_platform_id, received_at)
        return self._help(received_at)

    def _join(self, platform_id: str, content: str, received_at) -> str:
        parts = content.split(maxsplit=1)
        if len(parts) != 2 or not parts[1].strip():
            return self._reply("/入职", "missing_name", received_at)
        settings = self._repository.get_game_settings()
        employee, created = self._repository.create_user(
            platform_id, parts[1].strip(), received_at, settings.onboarding_bonus
        )
        if not created:
            return self._reply(
                "/入职",
                "already_joined",
                received_at,
                {"{昵称}": employee.display_name, "{余额}": employee.balance},
            )
        return self._reply(
            "/入职",
            "joined",
            received_at,
            {"{昵称}": employee.display_name, "{余额}": employee.balance},
        )

    def _check_in(self, platform_id: str, received_at) -> str:
        employee = self._repository.find_user(platform_id)
        if employee is None:
            return self._reply("/打卡", "not_joined", received_at)
        settings = self._repository.get_game_settings()
        if not self._repository.check_in(employee, received_at, settings.checkin_reward):
            return self._reply(
                "/打卡", "already_checked_in", received_at, {"{昵称}": employee.display_name}
            )
        return self._reply(
            "/打卡",
            "checked_in",
            received_at,
            {
                "{昵称}": employee.display_name,
                "{余额}": employee.balance,
                "{打卡奖励}": settings.checkin_reward,
            },
        )

    def _balance(self, platform_id: str, received_at) -> str:
        employee = self._repository.find_user(platform_id)
        if employee is None:
            return self._reply("/余额", "not_joined", received_at)
        return self._reply(
            "/余额",
            "shown",
            received_at,
            {"{昵称}": employee.display_name, "{余额}": employee.balance},
        )

    def _me(self, platform_id: str, received_at) -> str:
        employee = self._repository.find_user(platform_id)
        if employee is None:
            return self._reply("/我", "not_joined", received_at)
        activity = self._repository.personal_activity(platform_id, received_at)
        if activity is None:
            raise RuntimeError("employee disappeared")
        return self._reply(
            "/我",
            "shown",
            received_at,
            {
                "{昵称}": employee.display_name,
                "{余额}": employee.balance,
                "{活跃等级}": f"LV{activity.level}",
                "{今日收益}": self._repository.today_income(employee.id, received_at),
            },
        )

    def _inventory(self, platform_id: str, received_at) -> str:
        employee = self._repository.find_user(platform_id)
        if employee is None:
            return self._reply("/我的物品", "not_joined", received_at)
        items = self._repository.list_user_items(employee.id)
        return self._reply(
            "/我的物品",
            "shown",
            received_at,
            {
                "{昵称}": employee.display_name,
                "{物品列表}": "暂时空空如也。"
                if not items
                else "\n".join(f"{name} × {quantity}" for name, quantity in items),
            },
        )

    def _shop(self, received_at) -> str:
        items = self._repository.list_active_items()
        if not items:
            return self._reply("/商店", "empty", received_at)
        currency_name = self._repository.get_game_settings().currency_name
        return self._reply(
            "/商店",
            "items_available",
            received_at,
            {
                "{商店列表}": "\n".join(
                    f"{item.name}（{item.price} {currency_name}，库存 {item.stock}）"
                    for item in items
                )
            },
        )

    def _event_join(self, platform_id: str, content: str, received_at) -> str:
        parts = content.split(maxsplit=1)
        if len(parts) != 2 or not parts[1].strip():
            return self._reply("/加入", "invalid", received_at)
        status = self._repository.join_random_event(
            platform_id, parts[1].strip(), received_at
        )
        employee = self._repository.find_user(platform_id)
        if status == "not_joined":
            return self._reply("/加入", status, received_at)
        if status == "no_event":
            return self._reply("/加入", status, received_at)
        if status == "joined":
            return self._reply(
                "/加入", status, received_at,
                {"{昵称}": employee.display_name, "{角色}": parts[1].strip()},
            )
        if status == "started":
            return self._reply(
                "/加入", status, received_at, {"{昵称}": employee.display_name}
            )
        reasons = {
            "event_started": "随机事件已经开始，无法再报名。",
            "already_joined": "你已经报名了当前随机事件。",
            "unknown_role": "这个角色不在当前随机事件的可选席位中。",
            "role_full": "这个角色的席位已经满了。",
        }
        return self._reply("/加入", "failed", received_at, {"{原因}": reasons[status]})

    def _event_leave(self, platform_id: str, received_at) -> str:
        status = self._repository.leave_random_event(platform_id, received_at)
        if status == "not_joined":
            return self._reply("/退出", status, received_at)
        if status == "no_event":
            return self._reply("/退出", status, received_at)
        employee = self._repository.find_user(platform_id)
        if status == "rewarded":
            return self._reply(
                "/退出", status, received_at,
                {
                    "{昵称}": employee.display_name,
                    "{事件奖励}": self._event_reward(platform_id),
                },
            )
        if status == "left_signup":
            return self._reply(
                "/退出", "signup_left", received_at, {"{昵称}": employee.display_name}
            )
        if status == "left_without_reward":
            return self._reply(
                "/退出", "left", received_at, {"{昵称}": employee.display_name}
            )
        return self._reply(
            "/退出", "failed", received_at,
            {"{原因}": "你没有加入当前随机事件。"},
        )

    def _event_reward(self, platform_id: str) -> int:
        return self._repository.last_random_event_reward(platform_id)

    def _help(self, received_at) -> str:
        commands = self._repository.list_enabled_command_definitions()
        settings = self._repository.get_game_settings()
        descriptions = {
            "/打卡": f"每日领取 {settings.checkin_reward} {settings.currency_name}"
        }
        return self._reply(
            "/帮助",
            "shown",
            received_at,
            {
                "{指令列表}": "\n".join(
                    f"{item.command}：{descriptions.get(item.command, item.description)}"
                    for item in commands
                )
            },
        )

    def _reply(self, command: str, scenario: str, received_at, values=None) -> str:
        definition = template_definition(command, scenario)
        template_record = self._repository.get_reply_template(command, scenario)
        template = template_record.template if template_record is not None else definition.default
        context = {
            "{日期}": received_at.date().isoformat(),
            "{货币}": self._repository.get_game_settings().currency_name,
            **(values or {}),
        }
        try:
            return render_template(definition, template, context)
        except ValueError:
            return render_template(definition, definition.default, context)

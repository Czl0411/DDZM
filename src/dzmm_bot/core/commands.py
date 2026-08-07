from zoneinfo import ZoneInfo

from dzmm_bot.runtime.contracts import InboundMessage

from .reply_templates import render_template, template_definition
from .repository import CoreRepository
from .service import CommandReply


_BEIJING = ZoneInfo("Asia/Shanghai")
_COMMANDS = {
    "/入职", "/我的物品", "/打卡", "/余额", "/我", "/商店", "/帮助", "/加入", "/退出", "/摸鱼躲猫猫", "/记忆考核", "/继续", "/收手", "/投降", "/部门", "/加入部门", "/切换部门", "/部门申请列表", "/同意部门", "/全部同意部门", "/拒绝部门", "/全部拒绝部门", "/职位", "/晋升", "/晋升申请列表", "/同意", "/全部同意", "/拒绝", "/全部拒绝"
}


class GroupCommandHandler:
    def __init__(self, repository: CoreRepository) -> None:
        self._repository = repository

    def handle(self, message: InboundMessage) -> str | list[str] | None:
        content = message.content.strip()
        if not content:
            return None
        command = content.split(maxsplit=1)[0]
        if command == "/摸鱼躲猫猫":
            return None
        if command in {"/开始摸鱼躲藏", "/躲"}:
            command = "/摸鱼躲猫猫"
        if command == "/me":
            command = "/我"
        if command == "/答案":
            parts = content.split(maxsplit=1)
            if len(parts) != 2 or not parts[1].strip():
                return None
            return self._memory_assessment_answer(
                message.sender_platform_id, parts[1].strip(), message.received_at.astimezone(_BEIJING)
            )
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
        if command == "/部门":
            return self._departments(received_at)
        if command == "/加入部门":
            return self._join_department(message.sender_platform_id, content, received_at)
        if command == "/切换部门":
            return self._switch_department(message.sender_platform_id, content, received_at)
        if command == "/部门申请列表":
            return self._department_request_list(message.sender_platform_id, received_at)
        if command in {"/同意部门", "/拒绝部门", "/全部同意部门", "/全部拒绝部门"}:
            return self._department_decision(
                message.sender_platform_id, command, content, received_at
            )
        if command == "/职位":
            return self._positions(received_at)
        if command == "/晋升":
            return self._request_promotion(message.sender_platform_id, received_at)
        if command == "/晋升申请列表":
            return self._promotion_list(message.sender_platform_id, received_at)
        if command in {"/同意", "/拒绝", "/全部同意", "/全部拒绝"}:
            return self._promotion_decision(
                message.sender_platform_id, command, content, received_at
            )
        if command == "/加入":
            return self._event_join(message.sender_platform_id, content, received_at)
        if command == "/退出":
            return self._event_leave(message.sender_platform_id, received_at)
        if command == "/摸鱼躲猫猫":
            return self._hide_and_seek(message.sender_platform_id, content, received_at)
        if command == "/记忆考核":
            return self._memory_assessment_start(
                message.sender_platform_id, content, received_at
            )
        if command == "/继续":
            return self._memory_assessment_continue(message.sender_platform_id, received_at)
        if command == "/收手":
            return self._memory_assessment_cash_out(message.sender_platform_id, received_at)
        if command == "/投降":
            return self._memory_assessment_surrender(message.sender_platform_id, received_at)
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
        profile = self._repository.get_user_profile(platform_id)
        if profile is None:
            return self._reply("/我", "not_joined", received_at)
        employee = profile.user
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
                "{连续打卡天数}": self._repository.consecutive_checkin_days(
                    employee.id, received_at
                ),
                "{职位}": profile.rank.name,
                "{职级}": profile.rank.level_label,
                "{部门}": profile.department.name,
            },
        )

    def _join_department(self, platform_id: str, content: str, received_at) -> str:
        parts = content.split(maxsplit=1)
        if len(parts) != 2 or not parts[1].strip():
            return self._reply("/加入部门", "usage", received_at)
        profile = self._repository.get_user_profile(platform_id)
        if profile is None:
            return self._reply("/加入部门", "not_joined", received_at)
        if not profile.department.is_default:
            return self._reply("/加入部门", "already_assigned", received_at)
        result = self._repository.request_department_change(
            platform_id, parts[1].strip(), received_at
        )
        if result.status == "not_joined":
            return self._reply("/加入部门", "not_joined", received_at)
        if result.status == "requested":
            return self._reply(
                "/加入部门",
                "requested",
                received_at,
                {"{昵称}": profile.user.display_name, "{部门}": parts[1].strip()},
            )
        if result.status == "already_pending":
            return self._reply("/加入部门", "already_pending", received_at)
        return self._reply("/加入部门", "unknown_department", received_at)

    def _switch_department(self, platform_id: str, content: str, received_at) -> str:
        parts = content.split(maxsplit=1)
        if len(parts) != 2 or not parts[1].strip():
            return self._reply("/切换部门", "usage", received_at)
        profile = self._repository.get_user_profile(platform_id)
        if profile is None:
            return self._reply("/切换部门", "not_joined", received_at)
        if profile.department.is_default:
            return self._reply("/切换部门", "must_join_first", received_at)
        result = self._repository.request_department_change(
            platform_id, parts[1].strip(), received_at
        )
        if result.status == "requested":
            return self._reply(
                "/切换部门",
                "requested",
                received_at,
                {"{昵称}": profile.user.display_name, "{部门}": parts[1].strip()},
            )
        if result.status == "already_in_department":
            return self._reply("/切换部门", "already_in_department", received_at)
        if result.status == "already_pending":
            return self._reply("/切换部门", "already_pending", received_at)
        return self._reply("/切换部门", "unknown_department", received_at)

    def _departments(self, received_at) -> str:
        lines = [
            f"{department.name}：{department.description or '暂无说明'}"
            for department in self._repository.list_departments()
            if department.enabled and not department.is_default
        ]
        return self._reply(
            "/部门", "shown", received_at, {"{部门列表}": "\n".join(lines)}
        )

    def _department_request_list(self, platform_id: str, received_at) -> str:
        requests = self._repository.list_approvable_department_requests(
            platform_id, received_at
        )
        if not requests:
            return self._reply("/部门申请列表", "empty", received_at)
        lines = [
            f"{request.number}. {request.applicant_name}：{request.source_department_name} → {request.target_department_name}（剩余 {max(0, int((request.expires_at - received_at).total_seconds() // 3600))} 小时）"
            for request in requests
        ]
        return self._reply(
            "/部门申请列表", "shown", received_at, {"{申请列表}": "\n".join(lines)}
        )

    def _department_decision(
        self, platform_id: str, command: str, content: str, received_at
    ) -> str:
        decision = "approved" if "同意" in command else "rejected"
        requests = self._repository.list_approvable_department_requests(
            platform_id, received_at
        )
        if command.startswith("/全部"):
            numbers = [request.number for request in requests]
        else:
            parts = content.split()[1:]
            if not parts or any(not part.isdigit() or int(part) < 1 for part in parts):
                return self._reply(command, "usage", received_at)
            numbers = [int(part) for part in parts]
        if not numbers:
            return self._reply(command, "empty", received_at)
        request_by_number = {request.number: request for request in requests}
        results = self._repository.decide_department_requests(
            platform_id, numbers, decision, received_at
        )
        replies: list[str] = []
        for result in results:
            request = request_by_number.get(result.number)
            if result.status == "approved" and request is not None:
                replies.append(
                    self._reply(
                        command,
                        "approved",
                        received_at,
                        {"{昵称}": request.applicant_name, "{部门}": request.target_department_name},
                    )
                )
            elif result.status == "rejected" and request is not None:
                replies.append(
                    self._reply(command, "rejected", received_at, {"{昵称}": request.applicant_name})
                )
            else:
                replies.append(self._reply(command, "unavailable", received_at))
        return "\n".join(replies)

    def _positions(self, received_at) -> str:
        currency_name = self._repository.get_game_settings().currency_name
        lines = []
        for rank in self._repository.list_ranks():
            if not rank.enabled:
                continue
            promotion = "不可申请" if rank.is_board else f"晋升价格 {rank.promotion_price} {currency_name}"
            games = "不限" if rank.multiplayer_game_limit < 0 else str(rank.multiplayer_game_limit)
            management = "可参与群内管理" if rank.has_group_management else "无群内管理权限"
            lines.append(
                f"{rank.name}（{rank.level_label}）：{promotion}；投票权益 {rank.vote_weight}；多人小游戏发起 {games} 次；{management}"
            )
        return self._reply(
            "/职位", "shown", received_at, {"{职位列表}": "\n".join(lines)}
        )

    def _request_promotion(self, platform_id: str, received_at) -> str:
        result = self._repository.request_promotion(platform_id, received_at)
        if result.status == "not_joined":
            return self._reply("/晋升", "not_joined", received_at)
        if result.status == "requested":
            profile = self._repository.get_user_profile(platform_id)
            if profile is None:
                raise RuntimeError("employee disappeared")
            target = next(
                rank
                for rank in self._repository.list_ranks()
                if rank.id == result.request.target_rank_id
            )
            return self._reply(
                "/晋升",
                "requested",
                received_at,
                {
                    "{昵称}": profile.user.display_name,
                    "{当前职位}": profile.rank.name,
                    "{目标职位}": target.name,
                    "{晋升价格}": result.request.price,
                    "{货币}": self._repository.get_game_settings().currency_name,
                },
            )
        if result.status == "already_pending":
            return self._reply("/晋升", "already_pending", received_at)
        return self._reply("/晋升", "no_next_rank", received_at)

    def _promotion_list(self, platform_id: str, received_at) -> str:
        requests = self._repository.list_approvable_promotions(platform_id, received_at)
        if not requests:
            return self._reply("/晋升申请列表", "empty", received_at)
        lines = [
            f"{request.number}. {request.applicant_name}：{request.source_rank_name} → {request.target_rank_name}（{request.price} {self._repository.get_game_settings().currency_name}，剩余 {max(0, int((request.expires_at - received_at).total_seconds() // 3600))} 小时）"
            for request in requests
        ]
        return self._reply(
            "/晋升申请列表", "shown", received_at, {"{申请列表}": "\n".join(lines)}
        )

    def _promotion_decision(
        self, platform_id: str, command: str, content: str, received_at
    ) -> str:
        decision = "approved" if "同意" in command else "rejected"
        requests = self._repository.list_approvable_promotions(platform_id, received_at)
        if command.startswith("/全部"):
            numbers = [request.number for request in requests]
        else:
            parts = content.split()[1:]
            if not parts or any(not part.isdigit() or int(part) < 1 for part in parts):
                return self._reply(command, "usage", received_at)
            numbers = [int(part) for part in parts]
        if not numbers:
            return self._reply(command, "empty", received_at)
        request_by_number = {request.number: request for request in requests}
        results = self._repository.decide_promotions(platform_id, numbers, decision, received_at)
        replies: list[str] = []
        for result in results:
            request = request_by_number.get(result.number)
            if result.status == "approved" and request is not None:
                replies.append(
                    self._reply(
                        command,
                        "approved",
                        received_at,
                        {
                            "{昵称}": request.applicant_name,
                            "{目标职位}": request.target_rank_name,
                            "{晋升价格}": request.price,
                            "{货币}": self._repository.get_game_settings().currency_name,
                        },
                    )
                )
            elif result.status == "rejected" and request is not None:
                replies.append(
                    self._reply(command, "rejected", received_at, {"{昵称}": request.applicant_name})
                )
            elif result.status == "insufficient_balance":
                replies.append(self._reply(command, "insufficient_balance", received_at))
            else:
                replies.append(self._reply(command, "unavailable", received_at))
        return "\n".join(replies)

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
            duel = self._repository.join_memory_assessment_duel(platform_id, received_at)
            if duel.status == "duel_started":
                return self._memory_assessment_round_reply(
                    "/记忆考核", "duel_started", duel, received_at
                )
            if duel.status == "not_joined":
                return self._reply("/加入", "not_joined", received_at)
            if duel.status == "random_event_active":
                return self._reply("/记忆考核", "random_event_active", received_at)
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
                {
                    "{昵称}": employee.display_name,
                    "{角色}": parts[1].strip(),
                    "{剩余席位}": self._repository.random_event_open_seats(),
                },
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

    def _hide_and_seek(self, platform_id: str, content: str, received_at) -> str | list[str]:
        parts = content.split()
        if content == "/开始摸鱼躲藏":
            result = self._repository.start_hide_and_seek(platform_id, received_at)
            if result.status == "started":
                return self._reply(
                    "/摸鱼躲猫猫",
                    "started",
                    received_at,
                    {
                        "{昵称}": result.display_name,
                        "{入场费}": result.entry_fee,
                        "{场景列表}": "\n".join(
                            f"{number}（{name}）"
                            for number, name in enumerate(result.candidates, start=1)
                        ),
                        "{选择超时分钟}": self._repository.get_hide_and_seek_settings().selection_timeout_minutes,
                    },
                )
            return self._hide_and_seek_status_reply(result.status, received_at)
        if len(parts) == 2 and parts[0] == "/躲" and parts[1].isdigit():
            result = self._repository.choose_hide_and_seek(
                platform_id, int(parts[1]), received_at
            )
            if result.status in {"won", "found"}:
                first_patrols = "、".join(
                    f"{number}（{name}）"
                    for number, name in zip(result.patrol_numbers[:3], result.patrol_scenes[:3])
                )
                values = {
                    "{昵称}": result.display_name,
                    "{巡查地点}": first_patrols,
                    "{巡查过程}": f"【系统巡查·第一轮】巡查 {first_patrols}",
                    "{奖励}": result.win_reward,
                    "{余额}": result.balance,
                    "{惩罚金额}": result.entry_fee,
                }
                if len(result.patrol_numbers) == 3:
                    return self._reply(
                        "/摸鱼躲猫猫", "found_first_round", received_at, values
                    )
                second_patrols = "、".join(
                    f"{number}（{name}）"
                    for number, name in zip(result.patrol_numbers[3:], result.patrol_scenes[3:])
                )
                values["{巡查地点}"] = second_patrols
                values["{巡查过程}"] = f"【系统巡查·第二轮】巡查 {second_patrols}"
                return [
                    self._reply(
                        "/摸鱼躲猫猫",
                        "first_round_missed",
                        received_at,
                        {
                            "{昵称}": result.display_name,
                            "{巡查地点}": first_patrols,
                            "{巡查过程}": f"【系统巡查·第一轮】巡查 {first_patrols}",
                        },
                    ),
                    self._reply("/摸鱼躲猫猫", result.status, received_at, values),
                ]
            return self._hide_and_seek_status_reply(result.status, received_at)
        return self._reply("/摸鱼躲猫猫", "usage", received_at)

    def _hide_and_seek_status_reply(self, status: str, received_at) -> str:
        scenarios = {
            "not_joined": "not_joined",
            "random_event_active": "blocked",
            "disabled": "disabled",
            "daily_limit": "daily_limit",
            "already_active": "already_active",
            "not_enough_scenes": "not_enough_scenes",
            "invalid_scene": "invalid_scene",
            "no_active_game": "no_active_game",
            "expired": "expired",
        }
        return self._reply("/摸鱼躲猫猫", scenarios[status], received_at)

    def _memory_assessment_start(
        self, platform_id: str, content: str, received_at
    ) -> str:
        if content == "/记忆考核 对战":
            result = self._repository.start_memory_assessment_duel(platform_id, received_at)
            if result.status == "waiting_opponent":
                return self._reply(
                    "/记忆考核",
                    "duel_waiting",
                    received_at,
                    {"{昵称}": result.display_name, "{等级}": result.level},
                )
            scenarios = {
                "not_joined": "not_joined",
                "disabled": "disabled",
                "already_active": "already_active",
            }
            return self._reply("/记忆考核", scenarios[result.status], received_at)
        if content != "/记忆考核":
            return self._reply("/记忆考核", "usage", received_at)
        result = self._repository.start_memory_assessment_single(platform_id, received_at)
        if result.status == "started":
            return self._memory_assessment_round_reply("/记忆考核", "started", result, received_at)
        scenarios = {
            "not_joined": "not_joined",
            "disabled": "disabled",
            "daily_limit": "daily_limit",
            "already_active": "already_active",
            "random_event_active": "random_event_active",
        }
        return self._reply("/记忆考核", scenarios[result.status], received_at)

    def _memory_assessment_answer(
        self, platform_id: str, content: str, received_at
    ) -> str | None:
        result = self._repository.answer_memory_assessment(platform_id, content, received_at)
        if result.status in {"no_active_game", "answer_not_ready"}:
            return None
        if result.status == "correct":
            return self._reply(
                "/记忆考核",
                "correct",
                received_at,
                {
                    "{昵称}": result.display_name,
                    "{等级}": result.level,
                    "{奖励}": result.reward,
                },
            )
        if result.status == "completed":
            return self._reply(
                "/记忆考核",
                "completed",
                received_at,
                {
                    "{昵称}": result.display_name,
                    "{等级}": result.level,
                    "{奖励}": result.reward,
                    "{余额}": result.balance,
                },
            )
        if result.status == "failed":
            return self._reply("/记忆考核", "failed", received_at)
        if result.status == "duel_won":
            return self._reply(
                "/记忆考核",
                "duel_won",
                received_at,
                {
                    "{昵称}": result.display_name,
                    "{奖励}": result.reward,
                    "{余额}": result.balance,
                },
            )
        if result.status == "duel_incorrect":
            return self._reply(
                "/记忆考核",
                "duel_incorrect",
                received_at,
                {"{惩罚金额}": self._repository.get_memory_assessment_settings().duel_wrong_freeze},
            )
        if result.status == "duel_disqualified":
            return self._reply("/记忆考核", "duel_disqualified", received_at)
        if result.status == "duel_collected":
            return self._reply("/记忆考核", "duel_collected", received_at)
        return None

    def _memory_assessment_continue(self, platform_id: str, received_at) -> str:
        result = self._repository.continue_memory_assessment(platform_id, received_at)
        if result.status == "continued":
            return self._memory_assessment_round_reply("/继续", "continued", result, received_at)
        return self._reply("/继续", "cannot_continue", received_at)

    def _memory_assessment_cash_out(self, platform_id: str, received_at) -> str:
        result = self._repository.cash_out_memory_assessment(platform_id, received_at)
        if result.status == "cashed_out":
            return self._reply(
                "/收手",
                "cashed_out",
                received_at,
                {
                    "{昵称}": result.display_name,
                    "{奖励}": result.reward,
                    "{余额}": result.balance,
                },
            )
        return self._reply("/收手", "cannot_cash_out", received_at)

    def _memory_assessment_surrender(self, platform_id: str, received_at) -> str:
        result = self._repository.surrender_memory_assessment_duel(platform_id, received_at)
        if result.status == "duel_won":
            return self._reply(
                "/投降",
                "lost",
                received_at,
                {
                    "{昵称}": self._repository.find_user(platform_id).display_name,
                    "{胜者}": result.display_name,
                    "{奖励}": result.reward,
                },
            )
        return self._reply("/投降", "cannot_surrender", received_at)

    def _memory_assessment_round_reply(self, command: str, scenario: str, result, received_at) -> CommandReply:
        return CommandReply(
            self._reply(
                command,
                scenario,
                received_at,
                {
                    "{昵称}": result.display_name,
                    "{等级}": result.level,
                    "{考核文本}": result.answer,
                    "{撤回秒数}": result.display_seconds,
                },
            ),
            recall_after_seconds=result.display_seconds,
            memory_round_id=result.round_id,
        )

    def _help(self, received_at) -> str:
        commands = self._repository.list_enabled_command_definitions()
        settings = self._repository.get_game_settings()
        descriptions = {
            "/打卡": f"每日领取 {settings.checkin_reward} {settings.currency_name}",
            "/摸鱼躲猫猫": "发起单人躲猫猫小游戏；选择时发送 /躲 序号",
            "/记忆考核": "发起单人挑战；答对后发送 /继续 或 /收手",
            "/投降": "退出正在进行的记忆考核对战",
        }
        return self._reply(
            "/帮助",
            "shown",
            received_at,
            {
                "{指令列表}": "\n".join(
                    f"{'/开始摸鱼躲藏' if item.command == '/摸鱼躲猫猫' else item.command}：{descriptions.get(item.command, item.description)}"
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

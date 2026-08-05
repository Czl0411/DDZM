from zoneinfo import ZoneInfo

from dzmm_bot.runtime.contracts import InboundMessage

from .repository import CoreRepository


_BEIJING = ZoneInfo("Asia/Shanghai")
_COMMANDS = {"/入职", "/我的物品", "/打卡", "/余额", "/商店"}


class GroupCommandHandler:
    def __init__(self, repository: CoreRepository) -> None:
        self._repository = repository

    def handle(self, message: InboundMessage) -> str | None:
        content = message.content.strip()
        if not content:
            return None
        command = content.split(maxsplit=1)[0]
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
            return self._balance(message.sender_platform_id)
        if command == "/我的物品":
            return self._inventory(message.sender_platform_id)
        return self._shop()

    def _join(self, platform_id: str, content: str, received_at) -> str:
        parts = content.split(maxsplit=1)
        if len(parts) != 2 or not parts[1].strip():
            return "请用 /入职 名字 加入摸鱼公司。"
        employee, created = self._repository.create_user(
            platform_id, parts[1].strip(), received_at
        )
        if not created:
            return f"{employee.display_name}已经在职，当前余额：{employee.balance} 摸鱼币。"
        return f"{employee.display_name}，欢迎入职摸鱼公司。当前余额：0 摸鱼币。"

    def _check_in(self, platform_id: str, received_at) -> str:
        employee = self._repository.find_user(platform_id)
        if employee is None:
            return "请先用 /入职 名字 加入摸鱼公司。"
        if not self._repository.check_in(employee, received_at):
            return "今天已经打过卡啦，明天再来。"
        return f"打卡成功，领取 5 摸鱼币。当前余额：{employee.balance} 摸鱼币。"

    def _balance(self, platform_id: str) -> str:
        employee = self._repository.find_user(platform_id)
        if employee is None:
            return "请先用 /入职 名字 加入摸鱼公司。"
        return f"{employee.display_name}，当前余额：{employee.balance} 摸鱼币。"

    def _inventory(self, platform_id: str) -> str:
        employee = self._repository.find_user(platform_id)
        if employee is None:
            return "请先用 /入职 名字 加入摸鱼公司。"
        items = self._repository.list_user_items(employee.id)
        if not items:
            return f"{employee.display_name}的物品：暂时空空如也。"
        return f"{employee.display_name}的物品：\n" + "\n".join(
            f"{name} × {quantity}" for name, quantity in items
        )

    def _shop(self) -> str:
        items = self._repository.list_active_items()
        if not items:
            return "总监事小卖部还没有上架商品。"
        return "总监事小卖部：\n" + "\n".join(
            f"{item.name}（{item.price} 摸鱼币，库存 {item.stock}）"
            for item in items
        )

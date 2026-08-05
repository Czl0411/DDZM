from dataclasses import dataclass
from collections.abc import Mapping
import re


_TEMPLATE_TOKEN = re.compile(r"\{([^{}]+)\}")
_MAX_TEMPLATE_LENGTH = 2000


@dataclass(frozen=True)
class TemplateDefinition:
    command: str
    scenario: str
    label: str
    default: str
    variables: tuple[str, ...]


TEMPLATE_DEFINITIONS = (
    TemplateDefinition("/入职", "joined", "入职成功", "{昵称}，欢迎入职摸鱼公司。当前余额：{余额} {货币}。", ("{昵称}", "{余额}", "{货币}", "{日期}")),
    TemplateDefinition("/入职", "already_joined", "已入职", "{昵称}已经在职，当前余额：{余额} {货币}。", ("{昵称}", "{余额}", "{货币}", "{日期}")),
    TemplateDefinition("/入职", "missing_name", "缺少昵称", "请用 /入职 名字 加入摸鱼公司。", ("{日期}",)),
    TemplateDefinition("/打卡", "checked_in", "打卡成功", "打卡成功，领取 {打卡奖励} {货币}。当前余额：{余额} {货币}。", ("{昵称}", "{余额}", "{打卡奖励}", "{货币}", "{日期}")),
    TemplateDefinition("/打卡", "already_checked_in", "今日已打卡", "今天已经打过卡啦，明天再来。", ("{昵称}", "{日期}")),
    TemplateDefinition("/打卡", "not_joined", "未入职", "请先用 /入职 名字 加入摸鱼公司。", ("{日期}",)),
    TemplateDefinition("/余额", "shown", "查询成功", "{昵称}，当前余额：{余额} {货币}。", ("{昵称}", "{余额}", "{货币}", "{日期}")),
    TemplateDefinition("/余额", "not_joined", "未入职", "请先用 /入职 名字 加入摸鱼公司。", ("{日期}",)),
    TemplateDefinition("/我", "shown", "个人状态", "{昵称}，当前余额：{余额} {货币}。\n今日活跃度：{活跃等级}。\n今日收益：{今日收益} {货币}。", ("{昵称}", "{余额}", "{货币}", "{活跃等级}", "{今日收益}", "{日期}")),
    TemplateDefinition("/我", "not_joined", "未入职", "请先用 /入职 名字 加入摸鱼公司。", ("{日期}",)),
    TemplateDefinition("/我的物品", "shown", "查询成功", "{昵称}的物品：\n{物品列表}", ("{昵称}", "{物品列表}", "{日期}")),
    TemplateDefinition("/我的物品", "not_joined", "未入职", "请先用 /入职 名字 加入摸鱼公司。", ("{日期}",)),
    TemplateDefinition("/商店", "items_available", "商店有货", "总监事小卖部：\n{商店列表}", ("{商店列表}", "{日期}")),
    TemplateDefinition("/商店", "empty", "商店为空", "总监事小卖部还没有上架商品。", ("{日期}",)),
    TemplateDefinition("/帮助", "shown", "帮助回复", "总监事指令簿：\n{指令列表}", ("{指令列表}", "{日期}")),
    TemplateDefinition("/加入", "joined", "报名成功", "{昵称}已加入随机事件，担任{角色}。", ("{昵称}", "{角色}", "{日期}")),
    TemplateDefinition("/加入", "started", "事件开始", "{昵称}已加入，人员已齐，随机事件开始。", ("{昵称}", "{日期}")),
    TemplateDefinition("/加入", "no_event", "暂无事件", "当前没有可报名的随机事件。", ("{日期}",)),
    TemplateDefinition("/加入", "not_joined", "未入职", "请先用 /入职 名字 加入摸鱼公司。", ("{日期}",)),
    TemplateDefinition("/加入", "invalid", "报名方式", "请用 /加入 角色 报名。", ("{日期}",)),
    TemplateDefinition("/加入", "failed", "报名失败", "{原因}", ("{原因}", "{日期}")),
    TemplateDefinition("/退出", "rewarded", "领取奖励", "{昵称}完成目标，领取 {事件奖励} {货币}。", ("{昵称}", "{事件奖励}", "{货币}", "{日期}")),
    TemplateDefinition("/退出", "left", "退出事件", "{昵称}已退出随机事件，未达到奖励条件。", ("{昵称}", "{日期}")),
    TemplateDefinition("/退出", "signup_left", "取消报名", "{昵称}已退出随机事件报名。", ("{昵称}", "{日期}")),
    TemplateDefinition("/退出", "no_event", "暂无事件", "当前没有可退出的随机事件。", ("{日期}",)),
    TemplateDefinition("/退出", "not_joined", "未入职", "请先用 /入职 名字 加入摸鱼公司。", ("{日期}",)),
    TemplateDefinition("/退出", "failed", "退出失败", "{原因}", ("{原因}", "{日期}")),
)


def template_definition(command: str, scenario: str) -> TemplateDefinition:
    for definition in TEMPLATE_DEFINITIONS:
        if definition.command == command and definition.scenario == scenario:
            return definition
    raise ValueError("未知模板场景")


def definitions_for_command(command: str) -> tuple[TemplateDefinition, ...]:
    return tuple(
        definition
        for definition in TEMPLATE_DEFINITIONS
        if definition.command == command
    )


def validate_template(command: str, scenario: str, template: str) -> None:
    definition = template_definition(command, scenario)
    if not template.strip():
        raise ValueError("模板不能为空")
    if len(template) > _MAX_TEMPLATE_LENGTH:
        raise ValueError("模板不能超过 2000 个字符")
    allowed = set(definition.variables)
    for token in _TEMPLATE_TOKEN.findall(template):
        if f"{{{token}}}" not in allowed:
            raise ValueError(f"模板变量不支持：{{{token}}}")


def render_template(
    definition: TemplateDefinition, template: str, values: Mapping[str, object]
) -> str:
    validate_template(definition.command, definition.scenario, template)
    rendered = template
    for variable in definition.variables:
        if variable not in rendered:
            continue
        if variable not in values:
            raise ValueError(f"模板变量缺少值：{variable}")
        rendered = rendered.replace(variable, str(values[variable]))
    return rendered

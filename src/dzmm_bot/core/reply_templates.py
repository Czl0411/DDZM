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
    TemplateDefinition("/我", "shown", "个人状态", "{昵称}，当前余额：{余额} {货币}。\n今日活跃度：{活跃等级}。\n今日收益：{今日收益} {货币}。\n连续打卡：{连续打卡天数} 天。", ("{昵称}", "{余额}", "{货币}", "{活跃等级}", "{今日收益}", "{连续打卡天数}", "{日期}")),
    TemplateDefinition("/我", "not_joined", "未入职", "请先用 /入职 名字 加入摸鱼公司。", ("{日期}",)),
    TemplateDefinition("/我的物品", "shown", "查询成功", "{昵称}的物品：\n{物品列表}", ("{昵称}", "{物品列表}", "{日期}")),
    TemplateDefinition("/我的物品", "not_joined", "未入职", "请先用 /入职 名字 加入摸鱼公司。", ("{日期}",)),
    TemplateDefinition("/商店", "items_available", "商店有货", "总监事小卖部：\n{商店列表}", ("{商店列表}", "{日期}")),
    TemplateDefinition("/商店", "empty", "商店为空", "总监事小卖部还没有上架商品。", ("{日期}",)),
    TemplateDefinition("/帮助", "shown", "帮助回复", "总监事指令簿：\n{指令列表}", ("{指令列表}", "{日期}")),
    TemplateDefinition("/加入", "joined", "报名成功", "{昵称} 已加入随机事件，担任 {角色}。\n剩余可选身份：{剩余席位}", ("{昵称}", "{角色}", "{剩余席位}", "{日期}")),
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
    TemplateDefinition("/摸鱼躲猫猫", "usage", "玩法说明", "请用 /开始摸鱼躲藏 发起游戏，再用 /躲 编号 选择地点。", ("{日期}",)),
    TemplateDefinition("/摸鱼躲猫猫", "not_joined", "未入职", "请先用 /入职 名字 加入摸鱼公司。", ("{日期}",)),
    TemplateDefinition("/摸鱼躲猫猫", "blocked", "随机事件进行中", "当前随机事件正在报名或进行中，暂时不能发起躲猫猫。", ("{日期}",)),
    TemplateDefinition("/摸鱼躲猫猫", "disabled", "玩法未开启", "躲猫猫玩法暂未开启。", ("{日期}",)),
    TemplateDefinition("/摸鱼躲猫猫", "daily_limit", "今日次数已用完", "你今天的躲猫猫次数已经用完了，明天再来。", ("{日期}",)),
    TemplateDefinition("/摸鱼躲猫猫", "already_active", "正在选择地点", "你有一局躲猫猫正在选择地点，请先用 /躲 编号 完成选择。", ("{日期}",)),
    TemplateDefinition("/摸鱼躲猫猫", "not_enough_scenes", "地点不足", "当前可用躲猫猫地点不足 7 个，请联系管理员配置。", ("{日期}",)),
    TemplateDefinition("/摸鱼躲猫猫", "started", "选择躲藏地点", "{昵称}，躲猫猫开始，开局不扣除。若被系统找到，将扣除 {入场费} {货币}。\n请选择一个地点：\n{场景列表}\n请在 {选择超时分钟} 分钟内发送 /躲 编号。", ("{昵称}", "{入场费}", "{货币}", "{场景列表}", "{选择超时分钟}", "{日期}")),
    TemplateDefinition("/摸鱼躲猫猫", "invalid_scene", "地点编号无效", "请输入本局展示的 1 至 7 号地点。", ("{日期}",)),
    TemplateDefinition("/摸鱼躲猫猫", "no_active_game", "没有进行中的游戏", "你当前没有等待选择地点的躲猫猫游戏。", ("{日期}",)),
    TemplateDefinition("/摸鱼躲猫猫", "expired", "游戏已取消", "选择已超时，本局已取消，次数已返还。", ("{日期}",)),
    TemplateDefinition("/摸鱼躲猫猫", "found", "被系统找到", "{巡查过程}\n你被系统找到了，本局扣除 {惩罚金额} {货币}。当前余额：{余额} {货币}。", ("{昵称}", "{巡查地点}", "{巡查过程}", "{惩罚金额}", "{余额}", "{货币}", "{日期}")),
    TemplateDefinition("/摸鱼躲猫猫", "won", "躲藏成功", "{巡查过程}\n躲藏成功，获得 {奖励} {货币}。当前余额：{余额} {货币}。", ("{昵称}", "{巡查地点}", "{巡查过程}", "{奖励}", "{余额}", "{货币}", "{日期}")),
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

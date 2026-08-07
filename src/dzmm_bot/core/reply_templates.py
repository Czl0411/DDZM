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
    TemplateDefinition("/我", "shown", "个人状态", "{昵称}\n职位：{职位}（{职级}）\n部门：{部门}\n当前余额：{余额} {货币}。\n今日活跃度：{活跃等级}。\n今日收益：{今日收益} {货币}。\n连续打卡：{连续打卡天数} 天。", ("{昵称}", "{职位}", "{职级}", "{部门}", "{余额}", "{货币}", "{活跃等级}", "{今日收益}", "{连续打卡天数}", "{日期}")),
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
    TemplateDefinition("/部门", "shown", "部门列表", "部门列表：\n{部门列表}", ("{部门列表}", "{日期}")),
    TemplateDefinition("/加入部门", "requested", "加入申请已提交", "{昵称}已提交加入{部门}申请，等待该部门更高职位成员审批。", ("{昵称}", "{部门}", "{日期}")),
    TemplateDefinition("/加入部门", "joined", "董事会直接加入", "{昵称}已直接加入{部门}。", ("{昵称}", "{部门}", "{日期}")),
    TemplateDefinition("/加入部门", "usage", "部门名称缺失", "请用 /加入部门 部门名 加入部门。", ("{日期}",)),
    TemplateDefinition("/加入部门", "not_joined", "未入职", "请先用 /入职 名字 加入摸鱼公司。", ("{日期}",)),
    TemplateDefinition("/加入部门", "already_assigned", "已有部门", "你已加入部门，请使用 /切换部门 部门名。", ("{日期}",)),
    TemplateDefinition("/加入部门", "unknown_department", "部门不可用", "该部门不存在或暂未开放。", ("{日期}",)),
    TemplateDefinition("/加入部门", "already_pending", "已有待审申请", "你已有一条待审批的部门申请，请耐心等待。", ("{日期}",)),
    TemplateDefinition("/切换部门", "requested", "切换申请已提交", "{昵称}已提交切换至{部门}申请，等待该部门更高职位成员审批。", ("{昵称}", "{部门}", "{日期}")),
    TemplateDefinition("/切换部门", "switched", "董事会直接切换", "{昵称}已直接切换至{部门}。", ("{昵称}", "{部门}", "{日期}")),
    TemplateDefinition("/切换部门", "usage", "部门名称缺失", "请用 /切换部门 部门名 切换部门。", ("{日期}",)),
    TemplateDefinition("/切换部门", "not_joined", "未入职", "请先用 /入职 名字 加入摸鱼公司。", ("{日期}",)),
    TemplateDefinition("/切换部门", "must_join_first", "尚未加入部门", "你当前尚未分配部门，请使用 /加入部门 部门名。", ("{日期}",)),
    TemplateDefinition("/切换部门", "already_in_department", "部门未变更", "你当前已在该部门。", ("{日期}",)),
    TemplateDefinition("/切换部门", "unknown_department", "部门不可用", "该部门不存在或暂未开放。", ("{日期}",)),
    TemplateDefinition("/切换部门", "already_pending", "已有待审申请", "你已有一条待审批的部门申请，请耐心等待。", ("{日期}",)),
    TemplateDefinition("/部门申请列表", "shown", "待审部门申请", "{申请列表}", ("{申请列表}", "{日期}")),
    TemplateDefinition("/部门申请列表", "empty", "暂无申请", "当前没有你可处理的部门申请。", ("{日期}",)),
    TemplateDefinition("/同意部门", "approved", "部门申请已同意", "{昵称}已加入{部门}。", ("{昵称}", "{部门}", "{日期}")),
    TemplateDefinition("/同意部门", "usage", "申请编号格式", "请用 /同意部门 1 2 3 审批申请。", ("{日期}",)),
    TemplateDefinition("/同意部门", "empty", "暂无申请", "当前没有你可处理的部门申请。", ("{日期}",)),
    TemplateDefinition("/同意部门", "unavailable", "申请不可处理", "该部门申请不可处理。", ("{日期}",)),
    TemplateDefinition("/全部同意部门", "approved", "部门申请已同意", "{昵称}已加入{部门}。", ("{昵称}", "{部门}", "{日期}")),
    TemplateDefinition("/全部同意部门", "empty", "暂无申请", "当前没有你可处理的部门申请。", ("{日期}",)),
    TemplateDefinition("/全部同意部门", "unavailable", "申请不可处理", "该部门申请不可处理。", ("{日期}",)),
    TemplateDefinition("/拒绝部门", "rejected", "已拒绝", "已拒绝{昵称}的部门申请。", ("{昵称}", "{日期}")),
    TemplateDefinition("/拒绝部门", "usage", "申请编号格式", "请用 /拒绝部门 1 2 3 审批申请。", ("{日期}",)),
    TemplateDefinition("/拒绝部门", "empty", "暂无申请", "当前没有你可处理的部门申请。", ("{日期}",)),
    TemplateDefinition("/拒绝部门", "unavailable", "申请不可处理", "该部门申请不可处理。", ("{日期}",)),
    TemplateDefinition("/全部拒绝部门", "rejected", "已拒绝", "已拒绝{昵称}的部门申请。", ("{昵称}", "{日期}")),
    TemplateDefinition("/全部拒绝部门", "empty", "暂无申请", "当前没有你可处理的部门申请。", ("{日期}",)),
    TemplateDefinition("/全部拒绝部门", "unavailable", "申请不可处理", "该部门申请不可处理。", ("{日期}",)),
    TemplateDefinition("/职位", "shown", "职位列表", "职位列表：\n{职位列表}", ("{职位列表}", "{日期}")),
    TemplateDefinition("/晋升", "requested", "晋升申请已提交", "{昵称}已提交晋升申请：{当前职位} → {目标职位}，需要 {晋升价格} {货币}。", ("{昵称}", "{当前职位}", "{目标职位}", "{晋升价格}", "{货币}", "{日期}")),
    TemplateDefinition("/晋升", "already_pending", "已有申请", "你已有一条待审批的晋升申请，请耐心等待。", ("{日期}",)),
    TemplateDefinition("/晋升", "no_next_rank", "不可晋升", "你当前没有可申请的下一档职位。", ("{日期}",)),
    TemplateDefinition("/晋升", "not_joined", "未入职", "请先用 /入职 名字 加入摸鱼公司。", ("{日期}",)),
    TemplateDefinition("/晋升申请列表", "shown", "待审申请", "{申请列表}", ("{申请列表}", "{日期}")),
    TemplateDefinition("/晋升申请列表", "empty", "暂无申请", "当前没有你可处理的晋升申请。", ("{日期}",)),
    TemplateDefinition("/同意", "approved", "晋升成功", "{昵称}已晋升为{目标职位}，扣除 {晋升价格} {货币}。", ("{昵称}", "{目标职位}", "{晋升价格}", "{货币}", "{日期}")),
    TemplateDefinition("/同意", "usage", "申请编号格式", "请用 /同意 1 2 3 审批申请。", ("{日期}",)),
    TemplateDefinition("/同意", "empty", "暂无申请", "当前没有你可处理的晋升申请。", ("{日期}",)),
    TemplateDefinition("/同意", "insufficient_balance", "余额不足", "你的摸鱼币不够呢。", ("{日期}",)),
    TemplateDefinition("/同意", "unavailable", "申请不可处理", "该晋升申请不可处理。", ("{日期}",)),
    TemplateDefinition("/全部同意", "approved", "晋升成功", "{昵称}已晋升为{目标职位}，扣除 {晋升价格} {货币}。", ("{昵称}", "{目标职位}", "{晋升价格}", "{货币}", "{日期}")),
    TemplateDefinition("/全部同意", "empty", "暂无申请", "当前没有你可处理的晋升申请。", ("{日期}",)),
    TemplateDefinition("/全部同意", "insufficient_balance", "余额不足", "你的摸鱼币不够呢。", ("{日期}",)),
    TemplateDefinition("/全部同意", "unavailable", "申请不可处理", "该晋升申请不可处理。", ("{日期}",)),
    TemplateDefinition("/拒绝", "rejected", "已拒绝", "已拒绝{昵称}的晋升申请。", ("{昵称}", "{日期}")),
    TemplateDefinition("/拒绝", "usage", "申请编号格式", "请用 /拒绝 1 2 3 审批申请。", ("{日期}",)),
    TemplateDefinition("/拒绝", "empty", "暂无申请", "当前没有你可处理的晋升申请。", ("{日期}",)),
    TemplateDefinition("/拒绝", "unavailable", "申请不可处理", "该晋升申请不可处理。", ("{日期}",)),
    TemplateDefinition("/全部拒绝", "rejected", "已拒绝", "已拒绝{昵称}的晋升申请。", ("{昵称}", "{日期}")),
    TemplateDefinition("/全部拒绝", "empty", "暂无申请", "当前没有你可处理的晋升申请。", ("{日期}",)),
    TemplateDefinition("/全部拒绝", "unavailable", "申请不可处理", "该晋升申请不可处理。", ("{日期}",)),
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
    TemplateDefinition("/摸鱼躲猫猫", "first_round_missed", "第一轮未命中", "【系统巡查·第一轮】巡查 {巡查地点}\n奇怪，人躲哪里去了.......", ("{昵称}", "{巡查地点}", "{巡查过程}", "{日期}")),
    TemplateDefinition("/摸鱼躲猫猫", "found_first_round", "第一轮被找到", "【系统巡查·第一轮】巡查 {巡查地点}\n你被系统找到了，本局扣除 {惩罚金额} {货币}。当前余额：{余额} {货币}。", ("{昵称}", "{巡查地点}", "{巡查过程}", "{惩罚金额}", "{余额}", "{货币}", "{日期}")),
    TemplateDefinition("/摸鱼躲猫猫", "found", "第二轮被找到", "【系统巡查·第二轮】巡查 {巡查地点}\n你被系统找到了，本局扣除 {惩罚金额} {货币}。当前余额：{余额} {货币}。", ("{昵称}", "{巡查地点}", "{巡查过程}", "{惩罚金额}", "{余额}", "{货币}", "{日期}")),
    TemplateDefinition("/摸鱼躲猫猫", "won", "躲藏成功", "【系统巡查·第二轮】巡查 {巡查地点}\n躲藏成功，获得 {奖励} {货币}。当前余额：{余额} {货币}。", ("{昵称}", "{巡查地点}", "{巡查过程}", "{奖励}", "{余额}", "{货币}", "{日期}")),
    TemplateDefinition("/记忆考核", "usage", "玩法说明", "发送 /记忆考核 发起单人挑战；答对后发送 /继续 或 /收手。", ("{日期}",)),
    TemplateDefinition("/记忆考核", "not_joined", "未入职", "请先用 /入职 名字 加入摸鱼公司。", ("{日期}",)),
    TemplateDefinition("/记忆考核", "disabled", "玩法未开启", "记忆考核暂未开启。", ("{日期}",)),
    TemplateDefinition("/记忆考核", "daily_limit", "今日次数已用完", "你今天已经完成过记忆考核挑战，明天再来。", ("{日期}",)),
    TemplateDefinition("/记忆考核", "already_active", "考核正在进行", "当前有一场记忆考核正在进行，请稍后再试。", ("{日期}",)),
    TemplateDefinition("/记忆考核", "random_event_active", "随机事件优先", "当前随机事件正在报名或进行中，暂不能发起或加入记忆考核。", ("{日期}",)),
    TemplateDefinition("/记忆考核", "started", "展示考题", "【记忆考核·第 {等级} 级】请记住：{考核文本}", ("{昵称}", "{等级}", "{考核文本}", "{撤回秒数}", "{日期}")),
    TemplateDefinition("/记忆考核", "duel_waiting", "等待对手", "{昵称} 发起了记忆考核对战，另一位员工请发送 /加入 入局。", ("{昵称}", "{等级}", "{日期}")),
    TemplateDefinition("/记忆考核", "duel_started", "对战考题", "【记忆考核对战·第 {等级} 级】请记住：{考核文本}", ("{昵称}", "{等级}", "{考核文本}", "{撤回秒数}", "{日期}")),
    TemplateDefinition("/记忆考核", "duel_won", "对战胜利", "{昵称} 最先答对，赢得奖池 {奖励} {货币}。当前余额：{余额} {货币}。", ("{昵称}", "{奖励}", "{余额}", "{货币}", "{日期}")),
    TemplateDefinition("/记忆考核", "duel_incorrect", "对战答错", "答案不正确，本次扣除 {惩罚金额} {货币} 并加入奖池。", ("{昵称}", "{惩罚金额}", "{货币}", "{日期}")),
    TemplateDefinition("/记忆考核", "duel_disqualified", "对战不合格", "已达到答错上限，判定不合格。另一位员工仍可继续作答。", ("{日期}",)),
    TemplateDefinition("/记忆考核", "duel_collected", "对战结束", "双方均未通过记忆考核，奖池已由系统回收。", ("{日期}",)),
    TemplateDefinition("/记忆考核", "correct", "本级通过", "第 {等级} 级通过。现在收手可获得 {奖励} {货币}，或发送 /继续 挑战下一层。", ("{昵称}", "{等级}", "{奖励}", "{货币}", "{日期}")),
    TemplateDefinition("/记忆考核", "completed", "全部通关", "恭喜 {昵称} 完成第 {等级} 级记忆考核，获得 {奖励} {货币}。当前余额：{余额} {货币}。", ("{昵称}", "{等级}", "{奖励}", "{余额}", "{货币}", "{日期}")),
    TemplateDefinition("/记忆考核", "failed", "考核失败", "答案不正确，本次记忆考核未获得奖励。", ("{昵称}", "{日期}")),
    TemplateDefinition("/记忆考核", "no_active_game", "没有进行中的考核", "当前没有可作答的记忆考核。", ("{日期}",)),
    TemplateDefinition("/继续", "continued", "下一层开始", "【记忆考核·第 {等级} 级】请记住：{考核文本}", ("{昵称}", "{等级}", "{考核文本}", "{撤回秒数}", "{日期}")),
    TemplateDefinition("/继续", "cannot_continue", "无法继续", "当前没有通过且等待继续的单人记忆考核。", ("{日期}",)),
    TemplateDefinition("/收手", "cashed_out", "结算成功", "{昵称} 收手成功，获得 {奖励} {货币}。当前余额：{余额} {货币}。", ("{昵称}", "{奖励}", "{余额}", "{货币}", "{日期}")),
    TemplateDefinition("/收手", "cannot_cash_out", "无法收手", "当前没有可收手结算的单人记忆考核。", ("{日期}",)),
    TemplateDefinition("/投降", "lost", "投降结束", "{昵称} 投降，{胜者} 赢得奖池 {奖励} {货币}。", ("{昵称}", "{胜者}", "{奖励}", "{货币}", "{日期}")),
    TemplateDefinition("/投降", "cannot_surrender", "无法投降", "当前没有可投降的记忆考核对战。", ("{日期}",)),
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

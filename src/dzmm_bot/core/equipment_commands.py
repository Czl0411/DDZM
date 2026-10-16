def handle_equipment_command(repository, message, command, group_chat_id, *, workstation_links=None):
    if message.source_type != "group" or group_chat_id is None:
        return "请在已启用的群聊中使用装备商城指令。"
    parts = message.content.strip().split()
    numbered = command in {"/购买装备", "/装备", "/卸下"}
    if (numbered and (len(parts) != 2 or not parts[1].isascii() or not parts[1].isdigit()
                     or len(parts[1]) > 9 or int(parts[1]) < 1)) or (not numbered and len(parts) != 1):
        return f"用法：{command}" + (" 装备编号；发送 /装备商城 查看编号。" if numbered else "。")
    currency = repository.get_game_settings().currency_name
    if numbered:
        number = int(parts[1])
        if command == "/购买装备":
            result = repository.purchase_equipment(
                message.platform_message_id, message.sender_platform_id,
                number, group_chat_id, message.received_at,
            )
        else:
            result = repository.set_equipment_equipped(message.sender_platform_id, number, command == "/装备")
        if result.status == "purchased":
            return (f"购买成功：#{number} {result.name}，花费 {result.price} {currency}。\n"
                    f"当前余额：{result.balance} {currency}。\n"
                    f"已存入装备库，发送 /装备 {number} 放入工位。")
        if result.status in {"equipped", "removed"}:
            income = sum(item.daily_income for item in repository.list_equipment(message.sender_platform_id) if item.equipped)
            return (f"已{'装备' if result.status == 'equipped' else '卸下'} {result.name}。\n"
                    f"预计工位日收入：{income} {currency}（自动结算尚未启用）。")
        return {
            "not_joined": "请先使用 /入职 名字 加入摸鱼公司。",
            "not_found": "装备编号不存在，请发送 /装备商城 查看。",
            "wrong_group": "请在已启用的群聊中购买装备。",
            "disabled": f"{result.name}已下架，暂时无法购买。",
            "already_owned": f"你已拥有{result.name}，无需重复购买；发送 /装备 {number} 使用。",
            "not_owned": f"你尚未拥有{result.name}，请先发送 /购买装备 {number}。",
            "already_equipped": f"{result.name}已经装备，无需重复操作。",
            "already_removed": f"{result.name}当前未装备。",
            "request_conflict": "这条消息已处理过其他装备购买，请重新发送购买指令。",
            "insufficient_balance": f"余额不足：购买{result.name}需要 {result.price} {currency}，当前余额 {result.balance} {currency}。",
        }.get(result.status, "操作失败，请稍后重试。")
    employee = repository.find_user(message.sender_platform_id)
    if command != "/装备商城" and employee is None:
        return "请先使用 /入职 名字 加入摸鱼公司。"
    items = repository.list_equipment(message.sender_platform_id)
    if command == "/装备商城":
        lines = ["【装备商城】", "永久装备，每件限购一次；购买后手动装备。"]
        for item in items:
            if item.enabled:
                state = "已装备" if item.equipped else "已拥有" if item.owned else "未购买"
                lines.append(f"#{item.number} {item.name}｜{item.price} {currency}｜预计 +{item.daily_income} {currency}/日｜{state}")
        if not any(item.enabled for item in items):
            lines.append("暂无上架装备。")
        lines.extend(("发送 /购买装备 编号 购买，/我的装备 查看装备库。", "收益为预览，自动结算尚未启用。"))
        return "\n".join(lines)
    owned = [item for item in items if item.owned]
    equipped = [item for item in owned if item.equipped]
    if command == "/我的装备":
        lines = [f"【{employee.display_name}的装备库】"]
        lines.extend(f"#{item.number} {item.name}｜{'已装备' if item.equipped else '未装备'}" for item in owned)
        if not owned:
            lines.append("暂无装备，发送 /装备商城 挑选。")
        lines.append("发送 /装备 编号 放入工位，/卸下 编号 收回装备库。")
        return "\n".join(lines)
    income = sum(item.daily_income for item in equipped)
    game_url = None if workstation_links is None else workstation_links.game_url
    url = None if workstation_links is None else game_url or workstation_links.url_for(employee.id)
    overview = "\n".join((
        f"【{employee.display_name}的工位】",
        *(["工位链接将在下一条消息发送。"]
          if url else ["工位网页暂未开放，请管理员配置公开访问地址。"]),
        *(["进入游戏后显示当前 DZMM 登录账号的工位，请使用本人账号登录。"] if game_url else []),
        f"已装备：{'、'.join(item.name for item in equipped) or '暂无，简陋工位'}",
        f"预计工位日收入：{income} {currency}（自动结算尚未启用）。",
        "装备库和工位状态跨群共享。发送 /我的装备 管理。",
    ))
    return [overview, url] if url else overview

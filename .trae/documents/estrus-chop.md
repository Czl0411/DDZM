# /凿 与发情值系统 —— 实施方案

状态：**决策点已全部拍板（2026-10-03），待用户下达开工命令。获批前不写任何代码。**

## 一、功能总览

群内娱乐玩法：用 `/凿` 凿别人，被凿者发情值随机上涨并获得随机摸鱼币；发情值攒满 100 触发"高潮"段落文字。带开关（/允许被凿、/拒绝被凿）、查询（/我的发情值）与排行榜（手动 + 每日定时推送）。

发情值机制参考 dzmm_nuo（`runtime/heat.py` + `runtime/climax.py`）：按群按用户累积、满阈值触发、触发后重置并计"今日第 N 次 / 总第 M 次"、排除机器人自己、功能可关。dzmm_nuo 中没有"凿"，/凿 是本项目新玩法。

## 二、数据模型（迁移 88）

### estrus_states（发情值状态，按群 × 用户）

| 列 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| group_chat_id | FK group_chats | 按群独立 |
| user_id | FK users | |
| heat | int, default 0 | 当前发情值（0-100） |
| chopped_count | int, default 0 | 被凿总次数 |
| total_climaxes | int, default 0 | 总高潮次数 |
| today_climaxes | int, default 0 | 今日高潮次数（跨天清零，靠 last_climax_date 判断） |
| last_climax_date | date, null | 今日次数重置基准 |
| opted_out | bool, default false | /拒绝被凿 开关（默认允许被凿） |
| UniqueConstraint(group_chat_id, user_id) | | |

### estrus_chops（凿击日志）

| 列 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| group_chat_id | FK | |
| chopper_user_id | FK users | 凿人者 |
| target_user_id | FK users | 被凿者 |
| heat_gain | int | 本次发情值增量（0-2） |
| coins | int | 本次被凿者获得摸鱼币（0-2） |
| climax_triggered | bool | 本次是否触发高潮 |
| created_at | BeijingDateTime | |

### estrus_settings（单行设置，参考风纪罚款模式）

| 字段 | 默认 | 说明 |
|---|---|---|
| enabled | true | 功能总开关 |
| climax_threshold | 100 | 高潮阈值（用户定 100） |
| heat_p0 / heat_p1 / heat_p2 | 50 / 30 / 20 | 发情值增量为 0/1/2 的概率（百分比，三者之和须 = 100），后台可调 |
| coin_p0 / coin_p1 / coin_p2 | 50 / 30 / 20 | 摸鱼币为 0/1/2 的概率（百分比，三者之和须 = 100），后台可调 |
| chop_cooldown_seconds | 0 | 同一凿者两次 /凿 的冷却（0 = 无限制，默认无限制），后台可调 |
| 后台面板 | | 「游戏运营」下新增「凿与发情值」卡片（照大话骰子面板模式） |

> 排行榜推送时刻不再单独配置：**跟随收益榜推送时段**（activity_settings.report_times），见第五节。

### users 表扩展：gender 列

- 新增 `users.gender`（String(16)，'male' / 'female' / 'unknown'，默认 unknown）
- **取值链路（参考 dzmm_nuo `_gender_of`）**：
  1. 用户显式设置 `/设置性别 男|女`（最高优先级，写入 users.gender）
  2. 平台资料推断：worker 现有 member_directory（chatroom.getMembers）返回的用户字段里取 gender（male/man/男/m → male；female/女/f → female），查到后写回 users.gender 缓存（实现时先用探针确认 getMembers 返回体是否含 gender 字段，含则接入，不含则跳过此级）
  3. 都拿不到 → unknown，用中性文案
- 后台员工管理编辑弹窗同样可设置
- 用途：高潮文字按性别生成；同时供后台查看

### /设置性别（群内或私聊均可）

- `/设置性别 男` 或 `/设置性别 女`（其他取值报错）
- 回执：`已将你的性别设置为男。`（重复设置允许覆盖）
- 需已入职；加入 _DIRECT_COMMANDS（私聊可用）

## 三、指令设计（回执句式：甲凿了一下乙）

### /凿（群内）

两种形态，解析逻辑**完全照抄 /罚款**（引用回复形态优先，payload 语义不同）：

| 形态 | 解析 | payload 语义 |
|---|---|---|
| 引用回复 + /凿 [附言] | 被引用者为目标 | 附言（可选，展示在回执里） |
| /凿 名字 [附言] | 首 token 为目标名（支持 @），剩余为附言 | 同上 |

执行流程：
1. 凿者必须已入职；目标必须已入职（未入职报错）
2. 目标 = 凿者自己 → 拒绝
3. 目标 opted_out=true → 回执"TA 关闭了被凿"
4. 同一凿者冷却内（cooldown 秒）→ 静默拒绝或提示（走设置值）
5. 随机 roll：heat_gain = rand(0, heat_gain_max)，coins = rand(0, coin_gain_max)
6. 写 estrus_chops 日志、累加状态（heat、chopped_count）
7. coins > 0 时 `_apply_balance_change(user, coins, "estrus_gain", now)` —— **不走部门津贴，不占每日 5 币封顶**（见待确认点 2）
8. heat 达到阈值 → 触发高潮：清零 heat、total_climaxes+1、today_climaxes+1、climax_triggered=true

### 回执文案（群内单条）

普通：
```
【凿】甲凿了一下乙（附言）
乙 发情值 +2（当前 57/100），获得 1 摸鱼币。
```
（coins=0 时后半句为"乙 一无所获。"）

高潮触发时追加：
```
🔥 乙 发情值爆表！
（高潮段落文字）
（今日第 1 次 / 总第 3 次）
```

### /允许被凿、/拒绝被凿（群内，作用于自己）

切换自己的 opted_out，回执确认：
- `/拒绝被凿` → "已关闭被凿，你不会再被任何人凿。"
- `/允许被凿` → "已开启被凿，欢迎来凿。"
- 重复设置时提示当前状态已变更/未变化

### /我的发情值（群内）

```
【我的发情值】
当前发情值：57/100
被凿次数：23 ｜ 高潮：今日 1 次 / 总 3 次
状态：允许被凿
```

### /发情值排名（群内）

```
【发情值排名】
1. 甲 · 发情 88 · 被凿 40 · 高潮 今2/总5
2. 乙 · 发情 57 · 被凿 23 · 高潮 今1/总3
（最多 5 行）
```
排序规则参考 dzmm_nuo：今日高潮 > 总高潮 > 发情值 > 被凿次数。**只显示前 5 名**（手动查询与定时推送一致）。

## 四、高潮文字生成（已定：AI 生成，区分男女，不带上下文）

- 按被凿者 `users.gender` 分男女两套 prompt（male / female / unknown 三档，unknown 用中性文风）
- prompt 只含目标昵称 + 性别，**不带入最近群聊上下文**（与 dzmm_nuo 的差异点）
- 调用方式与 DDZM 现有 AI 生成链路对齐（实现时以成人卡场景生成的实际调用方式为准），同步调用 + 10 秒超时
- **兜底**：AI 失败/超时/空结果时，按性别从固定文案库（男女各 5 条 + 中性 5 条）随机选一条，保证必有输出
- 回执标注：`🔥 {目标} 发情值爆表！（今日第 N 次 / 总第 M 次）`

## 五、定时排行榜推送（已定：跟随收益榜时段）

- **与收益榜同一触发点**：`_enqueue_due_income_reports` 的每个 report_time 推送循环里，收益榜入队后紧随入队【发情值排名】（前 5 名，带日期头）——时刻与收益榜完全一致，防重逻辑同链路天然幂等，无需独立时刻配置
- 推送目标群与收益榜相同（listening_enabled + announcements_enabled 的群）

## 六、边界与异常

- 随机源：repository 构造器注入 `estrus_random`（照 `chat_drop_random` 模式），测试可固定；roll 逻辑 = 按 heat_p0/p1/p2、coin_p0/p1/p2 权重取 0/1/2
- 频繁凿同一个人：无目标侧限制，仅凿者侧冷却（默认 0 = 不限，后台可调）
- 高潮跨天清零 today_climaxes：按 last_climax_date 懒重置（照风纪罚款冷却模式）
- 发 0 币：照常入日志，回执文案体现"一无所获"
- 私聊发 /凿：提示请在群内使用
- 消息流：/凿 是普通指令，群消息 → command_handler 路由，无 service 白名单需求
- users.gender 为 unknown 时高潮文字用中性文案；后台员工编辑弹窗提供性别设置

## 七、测试要点

- 两种形态解析（引用/名字）、payload 附言
- 未入职/凿自己/目标拒绝被凿（公开提示"XX 拒绝了 YY 的凿，并且给了 YY 一杵子。"）
- 冷却拦截（cooldown=0 时不拦截）与放行
- 固定随机下按概率分布累计 heat/coins、高潮触发、清零与次数计数、跨天重置
- 回执文案断言（"甲凿了一下乙"句式 + 高潮段落）
- /允许被凿 //拒绝被凿 切换与重复切换
- 排行榜前 5 截断与收益榜同步推送幂等（同日同时段只推一次）
- 设置端点 GET/PATCH + 422 越界（概率和 ≠100、冷却越界）

## 八、部署

- 迁移 88（三张表 + users.gender 列）+ core 四文件 + admin 四文件（app.py/core_client.py/admin.js/index.html）
- 常规部署脚本 + 重启清单（core → admin-web → 三 worker）

## 九、决策点（2026-10-03 两轮拍板，全部落定）

第一轮：
1. 高潮文字：**AI 生成**（DeepSeek，固定文案兜底）
2. 被凿获得摸鱼币：**不占**每日 5 币津贴封顶，独立发币（balance source: estrus_gain）
3. 防刷：凿者冷却，后台可调（0=无限制）
4. 每日排行榜定时推送：跟随收益榜时段
5. 目标拒绝被凿时：群里公开提示

第二轮修订（用户 2026-10-03 指示）：
1. 高潮文字**区分男女**（users.gender 新列，后台员工编辑可设；unknown 中性文案），**不结合群聊上下文**
2. 回执句式："甲凿了一下乙"
3. 发情值/摸鱼币改为**概率分布**（0/1/2 三档，默认 50%/30%/20%，后台可调，各自和=100）
4. 冷却**默认 0（无限制）**，后台可调
5. 排行榜**只显示前 5 名**（手动与推送一致）；**推送时刻跟随收益榜**（activity_settings.report_times），不单独配置

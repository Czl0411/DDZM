# 大话骰子（liar_dice）移植实施计划

## Context

任务四：把 D:\Deepseek\dzmm_nuo 中的"大话骰子"移植到 DDZM（d:\Deepseek\DDZM，分支 `nuo/feature-test`，基线 50f05c0 含生日功能）。

源实现：`dzmm_nuo/dice_game.py`（74 行纯规则引擎）+ `dzmm_nuo/runtime/dice.py`（317 行状态机）。目标：注册为 DDZM 第 10 种群游戏，每群一局，PostgreSQL 持久化，群内指令交互。

**已与用户确认的设计决策：**
1. 骰子私密性 → 复刻德州扑克私聊发牌链路（开局预检私聊会话，缺则拒绝；私聊发骰；私聊 `/看骰` 复查）
2. 保留原版**万能点**规则（每轮随机万能点 1~6，开牌顶任何点；被叫过即失效只算自身）
3. 输家惩罚 → 不接经济系统：开牌后系统公告输家，**赢家获得发令权**（像国王游戏一样用普通消息给输家出惩罚任务，系统不强制执行），并累计统计（受罚/拆穿次数）
4. 每群同时仅一局（active_key 部分唯一索引模式）

## 已核实的项目先例（实现时直接参照）

| 机制 | 参照位置 |
|------|---------|
| 私聊发牌+回执推进 | `repository.py:10284-10292`（德州 enqueue_system_outbound delivery_kind="direct"）、`27707`（mark_outbound_sent 分支） |
| 私聊缺失拒绝开局 | `repository.py:10210-10211` missing_direct_chats |
| 仅私聊可用的查询指令 | `commands.py:348-392`（/看牌） |
| 自由文本旁路解析 | `commands.py:97-98`（彩票草稿 `_company_lottery_draft_step`） |
| 共享指令按活跃对局路由 | `active_gameplay_summary` `repository.py:11148` + commands.py:413/637/670/724 分支 |
| 一局一行+唯一索引 | `schema.py:330-337`（undercover ux_one_active） |
| 惰性超时判定 | `run_daily_jobs` `repository.py:23225`，挂 `run_liar_dice_jobs`（仿 run_undercover_jobs L15858） |
| 统计从对局表派生 | king game `repository.py:12477/12604` |
| enabled_game_types 回填 | `migrations/versions/20260819_49_group_game_types.py` |

## 施工步骤（迁移号 77）

### 1. `src/dzmm_bot/core/liar_dice.py`（新建，~120 行）
移植 dice_game.py 纯函数：`roll_dice`（每人5骰）、`roll_wild`（万能点）、`count_point`、`is_legal_raise`（N'>N，或 N'=N且X'>X；首叫 N≥在场人数）、`judge_open`、`parse_call`（正则 `^/?(\d+)\s*个\s*([1-6])$`）。随机源用注入参数 `liar_dice_random: Random`（便于测试）。

### 2. `core/schema.py`（+~90 行）三张表
- `liar_dice_games`：group_chat_id + host_user_id + active_key('global') 部分唯一索引；state 枚举 `signup/dealing/calling/round_end/completed/cancelled/forced_ended`；round_number、current_call JSON、current_seat、turn_deadline、timeout_streak、signup_deadline、时间戳组
- `liar_dice_players`：UniqueConstraint(game_id,user_id)、(game_id,seat_number)；state `signup/active/left`、seat_number、**dice JSON**（每人当前 5 骰）、hand_delivery_state（pending/sent）、hand_outbound_id FK
- `liar_dice_rounds`：UniqueConstraint(game_id,sequence)；wild_face、wild_invalidated、opener/caller、call_n/call_x、actual_count、winner/loser_user_id、dice_snapshot JSON、state；**叫牌历史用 calls JSON 追加**（免子表 join，king game number_map 先例）
- 统计不建表，从 rounds 派生

### 3. `migrations/versions/20261002_77_liar_dice.py`（~90 行）
建三表；逐行 SELECT→Python 合并→UPDATE 各群 `enabled_game_types` 追加 `"liar_dice"`（勿整体覆盖 JSON）。

### 4. `core/repository.py`（大头，~450 行）
- `LiarDiceResult` dataclass；`__init__` 注入 liar_dice_random
- 方法：`liar_dice_start / join / leave / begin（预检私聊→洗座位→摇骰存 JSON→enqueue 私聊发骰 delivery_kind="liar_dice_hand"→state=dealing）/ call（is_legal_raise→万能点失效标记→calls 追加→轮转 seat→turn_deadline）/ open骰（count_point/judge_open→round resolved→群播报全场明牌+**赢家获得发令权**提示）/ continue / end / private_hands / statistics`
- 全员 `hand_delivery_state=sent` 才进 calling（仿德州 private_delivery_state）
- `run_liar_dice_jobs`：报名超时关局、turn_deadline 超时 move-to-tail 跳过、满圈轮空本轮 voided、剩 <2 人散局 → 挂进 `run_daily_jobs`（L23362 旁）
- `active_gameplay_summary` 与 `force_end_gameplay` 各加 liar_dice 分支
- `_active_liar_dice_game` 接入其他游戏的互斥冲突检查

### 5. `core/group_games.py`（4 行）
GroupGameType / GROUP_GAME_TYPES / GROUP_GAME_LABELS（"大话骰子"）/ GROUP_GAME_COMMANDS（仅入口 `/大话骰子`）各加一条。

### 6. `core/commands.py`（~150 行）
- `_COMMANDS` 加：`/大话骰子 /开骰 /看骰 /大话骰子数据`
- `/开始 /加入 /退出 /结束游戏 /继续` 各加 liar_dice 分支（经 active_gameplay_summary 路由）
- 在指令分发落空处（仿 L97-98 彩票旁路）插入 `_liar_dice_call_step`：正则解析 `N个X`，仅群聊+本群有活跃 liar_dice 局时调 `liar_dice_call`，否则返回 None 落回闲聊
- `/当前游戏` 的 game_name、state_name 映射补 liar_dice；`/帮助` 增大话骰子段
- 前置校验三段集（公演封锁 L283、games_enabled L300、enabled_game_types L306）补 `/大话骰子`

### 7. `core/reply_templates.py`（~60 行）
仅入口/校验类场景用 TemplateDefinition（disabled/usage/not_turn/not_your_game 等）；开局公告、开牌看板、结算榜直接拼串（仿 dice.py 文案，含万能点说明）。

### 8. 测试（~300 行）
- `tests/core/test_liar_dice.py`（新建）：规则引擎单测（parse_call / is_legal_raise / count_point 含 called_wild 分支 / judge_open）；`_receive` 流程测试：报名→私聊缺失拒开→注入 Random 开局→回执 sent 进 calling→叫数→非法加码拒绝→开牌→/继续→退出散局；jobs 超时跳尾与满圈作废；/看骰 仅私聊
- `tests/core/test_repository.py` 补：同群双开局撞唯一索引、叫数与超时 job 并发
- `tests/deploy/test_liar_dice_migration.py`：建表 + enabled_game_types 回填断言

## 关键指令清单

`/大话骰子`（建局报名）、`/加入`、`/退出`、`/开始`（开局预检+发骰）、`N个X`（叫数，自由文本）、`/开骰`（质疑开牌）、`/继续`（下一轮）、`/结束游戏`、`/牌局`（战况）、`/看骰`（仅私聊）、`/大话骰子数据`（统计）

## 验证方案

1. 单测：`python -m pytest tests/core/test_liar_dice.py tests/deploy/test_liar_dice_migration.py -q`
2. 迁移链单头校验（77 挂 76 之后）
3. 群内端到端（部署到 43.153.194.94 测试）：三人先各自私聊机器人 → `/大话骰子` → `/加入`×2 → `/开始` → 私聊收骰、群见万能点 → 轮流"N个X" → `/开骰` 看全场明牌与胜负公告 → `/继续` → `/退出` 至 <2 人散局 → `/大话骰子数据` 核对统计
4. 部署走既有流程：DB 备份 → 服务器 clone 同步 → deploy.sh（alembic 自动升 77）

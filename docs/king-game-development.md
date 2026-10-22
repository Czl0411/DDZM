# 国王游戏开发文档

本文档描述 DZMM Bot 当前 `king_game` 玩法的产品规则、状态机、数据结构、接口、部署与测试方式。内容以仓库当前实现为准，基线提交为 `80410e5`。

## 1. 功能范围

国王游戏是群聊内的多人轮次玩法：

- 仅已入职员工可以创建和参与。
- 每局至少 3 人。
- 每轮随机产生一名国王，并将 `1..N` 随机分配给本轮玩家。
- 国王在群内自行发布命令，再用 `/公开 编号` 公开号码与玩家的完整对应关系。
- 机器人只管理报名、轮次、国王、编号、公开、退出和统计，不解析、不审核、不保存国王发送的普通命令内容。
- 玩法本身不设置下注、输赢奖励或直接摸鱼币结算。
- 开局时会复用公司的“小游戏开局津贴”规则；整局正常或强制结束后会计入部门小游戏参与统计。

玩法标识固定为：

```text
king_game
```

## 2. 玩家操作

所有玩法指令都必须在已监听、已启用国王游戏的群聊中发送。

| 指令 | 使用者 | 阶段 | 作用 |
| --- | --- | --- | --- |
| `/国王游戏` | 任一已入职员工 | 无活跃互斥玩法时 | 创建报名局，创建者自动加入并成为发起者 |
| `/加入` | 任一已入职员工 | 报名中 | 加入当前报名局 |
| `/加入` | 未在本局中的已入职员工 | 对局中 | 加入下一轮候选队列 |
| `/开始` | 发起者 | 报名中且至少 3 人 | 开始第一轮 |
| `/公开 2 5` | 当前国王 | 国王阶段 | 公开本轮完整编号映射，并记录 2、5 号为本轮被选中玩家 |
| `/继续` | 任一当前参与者 | 已公开 | 开始下一轮 |
| `/退出` | 当前参与者 | 报名中 | 立即退出报名；发起者退出时转交发起权 |
| `/退出` | 当前参与者 | 对局中 | 登记退出，本轮仍有效，下一轮开始前移除 |
| `/结束游戏` | 任一当前参与者 | 对局中 | 结束整局并输出实时统计 |
| `/国王游戏数据` | 群成员 | 对局中 | 查看当前局国王、受罚和回旋镖统计 |
| `/当前游戏` | 群成员 | 任意 | 查看当前状态、自己的身份及可用操作 |

`/公开` 支持以下分隔方式：

```text
/公开 2 5
/公开 2,5
/公开 2，5
```

约束：

- 至少提供一个编号。
- 编号必须是正整数。
- 编号不能重复。
- 编号不能超过本轮玩家人数。
- 国王可以选中自己的编号。

## 3. 标准对局流程

### 3.1 报名

1. 已入职员工发送 `/国王游戏`。
2. 系统创建一局 `signup` 状态的对局，发起者自动占据第一个名单顺序。
3. 其他员工发送 `/加入`。
4. 报名默认持续 10 分钟；到期仍未开始则自动取消。
5. 人数达到 3 人后，只有发起者可以发送 `/开始`。

报名期间发起者退出时，发起权按名单顺序转交给仍在报名的第一位玩家。

### 3.2 开始一轮

开始一轮时，服务端在同一事务内完成：

1. 读取当前 `active` 玩家。
2. 使用 `SystemRandom` 随机选出一名国王。
3. 使用 `SystemRandom.sample` 打乱玩家顺序。
4. 按打乱后的顺序分配 `1..N`。
5. 保存本轮国王、完整编号映射和截止时间。
6. 群内只公布轮数、国王和操作提示，不公布编号映射。

国王阶段默认 500 秒，后台允许配置为 1～3600 秒。配置变更从下一轮开始生效。

### 3.3 国王发布命令并公开

国王先发送普通群消息说明命令。普通消息不会被国王游戏解析或写入国王游戏数据表。

随后国王发送：

```text
/公开 2 5
```

系统验证发送者和编号后：

- 将本轮状态改为 `revealed`。
- 保存本轮被选中的编号列表。
- 公开本轮全部“编号：员工名称”映射。
- 根据被选中编号计算受罚次数。
- 若国王选中自己的编号，累计一次回旋镖。

### 3.4 下一轮

公开后，任一当前参与者可发送 `/继续`：

1. 将本轮登记退出的玩家改为 `withdrawn`。
2. 将对局中途 `/加入` 的候选玩家改为 `active`。
3. 若有效玩家少于 3 人，结束整局。
4. 否则重新随机国王和编号，进入下一轮。

公开后的等待阶段没有自动截止时间。

### 3.5 超时

- 报名超时：整局改为 `expired`，释放群内活跃对局占用，并发送自动取消公告。
- 国王超时：当前轮改为 `timed_out`，不公开映射、不记录被选编号，直接生成下一轮并通知群聊。

## 4. 状态机

### 4.1 对局状态

| 状态 | 含义 | 可进入的下一状态 |
| --- | --- | --- |
| `signup` | 报名中 | `awaiting_reveal`、`completed`、`expired`、`forced_ended` |
| `awaiting_reveal` | 等待国王公开 | `revealed`、下一轮 `awaiting_reveal`、`completed`、`forced_ended` |
| `revealed` | 已公开，等待继续 | 下一轮 `awaiting_reveal`、`completed`、`forced_ended` |
| `completed` | 正常结束 | 终态 |
| `cancelled` | 取消 | 终态 |
| `expired` | 报名超时 | 终态 |
| `forced_ended` | 后台强制结束 | 终态 |

活跃对局通过 `active_key = "global"` 标识。结束时必须将 `active_key` 置空，以释放该群的新对局创建资格。

### 4.2 玩家状态

| 状态 | 含义 |
| --- | --- |
| `signup` | 报名玩家；对局开始后也用于表示下一轮候选 |
| `active` | 当前轮有效玩家 |
| `withdrawn` | 已退出整局 |

对局中的退出不直接修改本轮编号映射，使用 `left_at` 登记，并在下一轮切换时统一转为 `withdrawn`。

### 4.3 轮次状态

| 状态 | 含义 |
| --- | --- |
| `awaiting_reveal` | 等待国王公开 |
| `revealed` | 已公开完整映射 |
| `timed_out` | 国王阶段超时，未公开 |

## 5. 实时统计

`/国王游戏数据` 只统计当前活跃对局，包含：

- 国王次数最多：每一轮被抽为国王的次数，包括最终超时的轮次。
- 受罚次数最多：已公开轮次中，号码被国王选中的次数。
- 回旋镖次数最多：已公开轮次中，国王选中自己号码的次数。

多人并列最高时全部显示；无有效记录时显示“暂无”。

整局由参与者 `/结束游戏` 时会先计算统计，再结束并在群里输出。当前没有“按历史局查询国王游戏统计”的管理接口。

## 6. 互斥、群聊与权限

### 6.1 群聊配置

创建新局前同时检查：

- 全局国王游戏开关为开启。
- 群聊存在且未删除。
- 群聊小游戏总开关 `games_enabled` 为开启。
- 群聊 `enabled_game_types` 包含 `king_game`。

### 6.2 对局互斥

国王游戏接入通用 gameplay gate。同一个群内已有互斥小游戏或随机事件时，创建返回 `multiplayer_active`。

数据库对 `king_games(group_chat_id)` 建立条件唯一索引，只允许每个群存在一条 `active_key IS NOT NULL` 的国王游戏，避免并发创建两局。

### 6.3 角色权限

- 创建、加入：必须存在员工用户记录。
- 开始：仅 `host_user_id`。
- 公开：仅 `current_king_user_id`。
- 继续、结束：仅本局 `active` 玩家。
- 后台：可使用通用强制结束能力，不受玩家角色限制。

## 7. 数据结构

迁移文件：`migrations/versions/20260903_68_king_game.py`

### 7.1 `king_game_settings`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | integer | 单例设置，固定为 1 |
| `enabled` | boolean | 是否允许创建新局 |
| `king_phase_timeout_seconds` | integer | 国王阶段秒数，默认 500 |
| `updated_at` | datetime | 最后更新时间 |

### 7.2 `king_games`

| 字段 | 说明 |
| --- | --- |
| `id` | 对局 UUID |
| `group_chat_id` | 所属群聊 |
| `host_user_id` | 发起者 |
| `active_key` | 活跃标识；结束后置空 |
| `state` | 对局状态 |
| `round_number` | 当前轮数 |
| `current_king_user_id` | 当前国王 |
| `signup_deadline` | 报名截止时间 |
| `king_phase_deadline` | 当前国王截止时间 |
| `end_after_round` | 兼容字段；当前流程不依赖该字段推进 |
| `created_at` / `started_at` / `finished_at` | 生命周期时间 |
| `finish_reason` | 结束原因 |

### 7.3 `king_game_players`

| 字段 | 说明 |
| --- | --- |
| `game_id` / `user_id` | 对局与员工 |
| `roster_order` | 稳定名单顺序 |
| `state` | `signup`、`active` 或 `withdrawn` |
| `joined_at` / `left_at` | 加入与登记退出时间 |

唯一约束：同一局同一员工仅一条记录；同一局名单顺序不可重复。

### 7.4 `king_game_rounds`

| 字段 | 说明 |
| --- | --- |
| `game_id` / `sequence` | 对局与轮数，组合唯一 |
| `king_user_id` | 本轮国王 |
| `number_map` | JSON，结构为 `{user_uuid: number}` |
| `revealed_numbers` | 国王选中的号码数组；未公开为 `NULL` |
| `state` | `awaiting_reveal`、`revealed` 或 `timed_out` |
| `started_at` / `revealed_at` | 开始与公开时间 |

## 8. 代码入口

| 层 | 文件 | 职责 |
| --- | --- | --- |
| 玩法注册 | `src/dzmm_bot/core/group_games.py` | `king_game` 类型、名称和专属指令映射 |
| 命令路由与文案 | `src/dzmm_bot/core/commands.py` | 群指令校验、调用仓储、渲染回复 |
| 状态机 | `src/dzmm_bot/core/repository.py` | 事务、锁、随机抽取、状态变更、超时、统计 |
| ORM | `src/dzmm_bot/core/schema.py` | 设置、对局、玩家、轮次表 |
| Core API | `src/dzmm_bot/core/app.py` | 内部设置读取与修改接口 |
| API 模型 | `src/dzmm_bot/core/api_models.py` | 设置请求与响应校验 |
| 管理端 API | `src/dzmm_bot/admin/app.py` | 后台鉴权、版本控制、转发 Core |
| 管理端客户端 | `src/dzmm_bot/admin/core_client.py` | Core HTTP 调用 |
| 管理页面 | `src/dzmm_bot/admin/templates/index.html`、`src/dzmm_bot/admin/static/admin.js` | 全局规则和群玩法开关 |
| 数据迁移 | `migrations/versions/20260903_68_king_game.py` | 建表、索引、知识卡和已有群启用 |

## 9. 仓储层接口

命令层调用以下方法；所有时间参数应为带时区的 `datetime`：

```python
get_king_game_settings() -> KingGameSettings
set_king_game_settings(*, enabled: bool, king_phase_timeout_seconds: int) -> KingGameSettings
king_game_statistics(group_chat_id) -> KingGameStatistics | None
start_king_game(platform_id, now, group_chat_id) -> KingGameResult
join_king_game(platform_id, now, group_chat_id) -> KingGameResult
begin_king_game(platform_id, now, group_chat_id) -> KingGameResult
reveal_king_game_numbers(platform_id, raw_numbers, now, group_chat_id) -> KingGameResult
continue_king_game(platform_id, now, group_chat_id) -> KingGameResult
leave_king_game(platform_id, now, group_chat_id) -> KingGameResult
end_king_game(platform_id, now, group_chat_id) -> KingGameResult
run_king_game_jobs(now) -> tuple[KingGameResult, ...]
```

`KingGameResult` 的主要字段：

```text
status
game_id
group_chat_id
round_number
king_name
king_platform_id
players
number_map
deadline
statistics
```

命令层必须根据 `status` 渲染用户可读消息，不应依赖异常表示普通业务拒绝。

## 10. 后台接口

### 10.1 管理端接口

```http
GET /api/game/king-game/settings
PATCH /api/game/king-game/settings
```

修改请求：

```json
{
  "enabled": true,
  "king_phase_timeout_seconds": 500
}
```

要求：

- 管理员鉴权。
- 请求字段必须且只能包含以上两个字段。
- `king_phase_timeout_seconds` 为 1～3600 的整数。
- 写操作使用后台通用的 `Idempotency-Key` 与 `If-Match` 配置版本控制。

### 10.2 Core 内部接口

```http
GET /internal/game/king-game/settings
PATCH /internal/game/king-game/settings
```

这些接口受 Core 内部鉴权保护，不是给普通玩家或第三方直接调用的公开 API。

## 11. 定时任务与重启恢复

超时依据数据库内的绝对截止时间，而不是进程内计时器：

- `signup_deadline` 控制报名超时。
- `king_phase_deadline` 控制国王阶段超时。

后台定时循环调用 `run_king_game_jobs(now)`，对到期记录加锁后推进状态，再将系统公告写入 outbound 队列。因此服务重启后仍可从数据库恢复并处理逾期对局。

多实例部署时必须共享同一数据库；事务锁和活跃局唯一索引用于避免重复推进与重复开局。

## 12. 安全与内容边界

- 国王的普通命令内容不进入国王游戏表，也不进入长期记忆或员工画像。
- 机器人不判断命令是否合理、安全或是否完成；群管理员仍需负责群规与内容治理。
- 群回复仅使用员工显示名，不公开数据库用户 UUID。
- 编号映射在 `king_game_rounds.number_map` 中属于未公开游戏状态，公开前不得由面向群聊的接口返回。
- `/公开` 只信任当前国王身份和服务端保存的本轮人数，不接受客户端提供映射。

## 13. 已知实现差异与待修项

以下项目是代码核对后确认的现状，二次开发时不能忽略：

1. **隐藏编号尚未私聊发给国王。** 当前服务端会生成并保存 `number_map`，群消息也写着“公开前仅国王可知”，但现有命令层没有把该映射通过私聊发送给国王。若产品规则要求国王先知道人物对应号码，需要增加可靠的私聊投递和失败提示；否则应把群文案改成“国王盲选编号”。
2. **报名阶段退出至不足 3 人的分支参数缺失。** `leave_king_game` 调用 `_finish_king_game_locked` 时漏传 `session`，该分支会抛出 `TypeError`。修复时应补回 `session` 并增加“一人创建后退出”“两人报名后退出”回归测试。
3. **旧设计稿中的退出规则已过时。** 当前实现统一把对局中退出延迟到下一轮，不会因国王当轮退出立即终止。
4. **没有国王游戏历史查询 API。** 数据会持久化，但后台目前只有设置接口；如需运营查询，应另做只读分页接口，不应复用活跃局统计接口。

## 14. 测试与验收

### 14.1 自动测试

聚焦测试：

```bash
.venv/bin/pytest -q \
  tests/core/test_group_games.py \
  tests/core/test_group_commands.py -k king_game \
  tests/core/test_repository.py -k king_game \
  tests/core/test_honors.py -k king_game \
  tests/deploy/test_king_game_migration.py
```

静态检查：

```bash
.venv/bin/python -m py_compile \
  src/dzmm_bot/core/group_games.py \
  src/dzmm_bot/core/commands.py \
  src/dzmm_bot/core/repository.py \
  src/dzmm_bot/core/schema.py
git diff --check
```

### 14.2 手工验收清单

- [ ] 未入职用户不能创建或加入。
- [ ] 少于 3 人不能开始。
- [ ] 非发起者不能开始。
- [ ] 非国王不能公开。
- [ ] 空编号、重复编号、负数、零、越界编号全部被拒绝。
- [ ] 中文逗号、英文逗号和空格都能分隔多个编号。
- [ ] 公开前群聊看不到编号映射。
- [ ] 公开后完整映射、受罚统计和回旋镖统计正确。
- [ ] 对局中加入者下一轮才生效。
- [ ] 对局中退出者本轮仍有效、下一轮移除。
- [ ] 下一轮不足 3 人时正常结束。
- [ ] 报名和国王阶段超时均能自动推进并发送公告。
- [ ] 服务重启后活跃局仍可继续。
- [ ] 同群并发创建最终只有一局成功。
- [ ] 不同群按各自群开关独立运行。
- [ ] 后台关闭玩法后不能创建新局，但不破坏已经开始的对局。

## 15. 部署步骤

```bash
alembic upgrade head
.venv/bin/pytest -q tests/deploy/test_king_game_migration.py
```

随后按项目现有方式重启 Core、Bot 与 Admin 服务，并完成以下健康检查：

1. 后台可以读取国王游戏设置。
2. 目标群已勾选“国王游戏”。
3. 测试群依次完成创建、三人加入、开始、公开、继续和结束。
4. 查看 outbound 消息队列与服务日志，确认无重复超时公告。

回滚前必须确认没有需要保留的国王游戏历史数据。迁移降级会删除 `king_game_rounds`、`king_game_players`、`king_games` 和 `king_game_settings` 表。

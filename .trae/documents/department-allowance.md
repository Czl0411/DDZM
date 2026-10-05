# 部门津贴系统实施计划（迁移 78）

## Context

部门功能完善（任务①）第一阶段：给部门接上实际增益。现状是部门只有组织架构（加入/切换/审批），没有任何功能。实现统一津贴结算器 + 钩子；抽象艺术部、风纪罚款暂不做；次元联合部拉新待平台侦察后另行实施。

**已确认规则**（用户拍板）：
- 封顶：每人每日合计 **+5 摸鱼币**（一人只属一个部门）
- **部门绑定走后台配置**：`departments` 表新增 `allowance_kind` 字段，管理员在后台为部门选择津贴类型；未绑定则不发（静默容错）
- 核心技术部（kind=checkin）：打卡 +5
- 色色事业部（kind=event）：**随机事件正常结算（ended）+5** 与 **公演正常完成（completed）+5** 两个钩子都挂
- 小游戏娱乐部（kind=game）：a) **对局真正开局时**（非创建报名时）发起者 +1；b) 每参与完成 5 局 +1（按日计数；**不含躲猫猫、记忆家族、红包完全不计**；德州流局 abort 不计；大话骰子按整局 finish 计）
- 学院（kind=submission）：随机事件投稿**审核通过** +5（与 approval_reward 同时机）
- 摸鱼吃瓜部（kind=chat）：普通水群消息 10% 概率掉 1 币，**同人 10 分钟冷却**（内存字典），静默入账不播报

## 已核实的代码锚点

| 机制 | 位置 |
|------|------|
| 发币唯一入口（原子自增+流水） | `repository.py:24162 _apply_balance_change`，须在 `self.transaction()` 活动会话内 |
| 每日计数表范式 | `TexasHoldemDailyStartRecord`（schema.py:1231）；幂等 upsert repository.py:24584-24630 |
| 打卡 | `repository.py:26308 check_in`（26337 发基础奖） |
| 随机事件结算 | `_settle_random_event_tipping`（repository.py:23609）→ `_finish_random_event("ended")` 23663；参与者 23619-23627 |
| 公演正常完成 | `_settle_performance_tipping`（repository.py:7772）→ `reservation.state = "completed"`（7823）；参与者 PerformanceParticipantRecord；expired(7911) 不算 |
| 投稿审核 | `approve_random_event_submission`（repository.py:3887，发奖先例 3951-3956） |
| **7 个真正开局点**（开局奖挂这里，发给发起者） | `begin_king_game` 12415 / `begin_liar_dice` 13199 / `_start_undercover_game` 17496（满员自动开局）/ `begin_never_have_i_ever` 14889 / `start_texas_holdem_hand` 10237（发牌）/ `start_number_bomb_round` 15168（首轮）/ `start_blame_game` 20803（创建即开局） |
| **对局完成计数点**（参与计数挂这里，发参与者） | `_finish_king_game_locked` 12722 / `_finish_liar_dice_locked` 12895 / `_settle_undercover_vote` 17875 与 `end_undercover` 17123 / `_settle_blame_game` 21303 / `_finish_number_bomb_game` 16323 / `_settle_texas_holdem` 10569（abort 10881 不计）/ `_finish_never_have_i_ever_locked` 14860。**红包、躲猫猫、记忆不挂** |
| 水群挂载 | `service.py` 365-374 eligible 判定之后 |
| RNG 注入范式 | repository.py:2517 `red_packet_random` |
| 部门后台 CRUD | `admin/app.py` 652-746（部门增删改查）；前端 `admin.js` 2054-2093 部门编辑弹窗 |
| 渲染 | /我 = commands.py:1903 `_me`；/部门 = commands.py:2175 `_departments` |

## 施工步骤（迁移 78）

### 1. `core/schema.py`
- `departments` 加列 `allowance_kind String(32) nullable`（枚举：checkin/event/game/submission/chat）
- 新表 `department_allowances`：id / user_id FK / allow_date Date / kind String(32) / amount Integer / created_at；Index(user_id, allow_date)
- 新表 `department_game_plays`：id / user_id FK / play_date Date / count；UniqueConstraint(user_id, play_date)

### 2. `migrations/versions/20261002_78_department_allowance.py`
down_revision=77；departments 加列 + 两张新表。不改 reply_templates 模板表。

### 3. `core/repository.py` 统一入口
- 构造器加 `chat_drop_random: RandomSource | None = None`（仿 2517）
- `_grant_department_allowance(session, user, kind, now)`：查 user.department → `dept.allowance_kind` 与 kind 的部门前缀匹配（checkin/event/game/submission/chat）→ 不匹配/未绑定/停用静默返回 → 当日 SUM≥5 返回 → `granted=min(面额, 5-SUM)` 写流水 + `_apply_balance_change`
- `_bump_department_game_plays(session, user_ids, now)`：方言分支 upsert count+1 returning count；`count % 5 == 0` 者发 `dept_game_play`
- `department_allowance_summary(platform_id, now) -> int`：当日 SUM
- `grant_chat_drop_allowance(platform_id, now)`：自开事务，校验 kind=chat → `_grant_department_allowance("dept_chat", 1)`
- 并发说明：发放均在用户自身消息/结算事务内，SUM 判定足够

### 4. 钩子挂载（全部在既有事务内追加）
| 钩子 | 插入点 |
|------|--------|
| 打卡 +5 | `check_in` 发基础奖后 |
| 随机事件 +5 | `_settle_random_event_tipping` 参与者循环内逐人（ended 分支）；dissolved/cancelled 不调 |
| 公演完成 +5 | `_settle_performance_tipping` completed 分支参与者逐人 |
| 开局 +1 | 7 个 begin 点（上表）创建/发牌成功后对发起者发 `dept_game_host` |
| 参与 5 局 +1 | 7 个完成计数点收集参与者 user_ids → `_bump_department_game_plays` |
| 投稿审核 +5 | `approve_random_event_submission` 发 approval_reward 后 |

### 5. `core/service.py` 水群掉落
- 内存冷却字典 `platform_id → 上次判定时间`，同人 10 分钟内不判定（连骰子都不掷）
- 冷却过后且 eligible：`random() < 0.1` 命中 → `grant_chat_drop_allowance`；静默不 enqueue

### 6. 后台管理（admin）
- `admin/app.py` 部门创建/更新接口接受 `allowance_kind`（校验枚举）；部门列表返回该字段
- `admin.js` 部门编辑弹窗加下拉框：无 / 打卡+5（checkin）/ 事件演出+5（event）/ 游戏开局与参与（game）/ 投稿+5（submission）/ 水群掉落（chat）
- `admin/templates/index.html` 弹窗对应控件

### 7. `core/commands.py` 渲染
- `_me`：渲染后追加一行 `今日部门津贴：X/5`（未绑定津贴的部门不加）
- `_departments`：按 `allowance_kind` 显示对应增益说明（静态 dict），未绑定不加

### 8. 测试
- `tests/core/test_repository.py` 补：封顶边界（4+5→实发 1）；未绑定/停用部门不发；`_bump_` 第 5 次发 1；texas abort 不计；开局奖在 begin 而非 signup（KingGame：signup 后不查余额变化，begin 后 +1）
- `tests/core/test_group_commands.py` 补：注入 Random 的水群命中/未命中与冷却（同发送者 10 分钟内第二条不判定）；打卡/事件/公演钩子经 `_service/_receive` 走通
- `tests/deploy/test_department_allowance_migration.py`：迁移 78（departments 新列 + 两表）

## 验证方案

1. 本地：`pytest tests/core tests/deploy -q`；alembic 单头
2. 部署到 43.153.194.94（备份 → 切分支 → deploy.sh）后，管理员在后台为四个部门绑定津贴类型，然后群内验证：
   - 核心技术部打卡 +5、二刷不发；色色部随机事件 ended +5、公演完成 +5、流局/过期不发
   - 游戏部：创建报名局不发、/开始 开局才 +1；参与满 5 局 +1；封顶后停发
   - 学院投稿过审 +5；吃瓜部水群命中 +1、同人 10 分钟内不重复判定
   - `/我` 显示今日津贴 X/5；`/部门` 显示绑定后的增益说明；后台改绑定立即生效

## 后续（不在本计划内）

- 次元联合部（选 A 邀请归因）：先侦察平台入群事件/邀请字段
- 风纪监察部罚款：等细则；抽象艺术部：搁置

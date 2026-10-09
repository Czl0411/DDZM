# 真心换真心：群轮流问答游戏

## 目标

群内轮流真心话问答游戏（据用户聊天记录定稿 + 4 点修订）：按编号轮流，轮到者提问、其余全员作答，答完换人，全员问过一轮后结算。没有大冒险，系统不判定内容对错。**本文档为实施定稿，待开工命令。**

## 一、玩法规则

1. `/真心换真心` 开报名局，`/加入` 报名（最少 2 人），发起者 `/开始` 开局；成员按加入顺序编号 1..N
2. 第 1 号发 `/问题 <问题>` 提问 → bot 广播"请其他人回答"
3. 其余参与者各发 `/真心 <回答>` 作答（每人一答，先到先得，可发 `/真心 跳过` 记为拒答）
4. 全员答完（或超时/跳过）→ bot 发本轮问答摘要 → 轮到下一位提问
5. 最后一位答完 → 自动结算（每人提问数/回答数统计）并进入轮次完毕态
6. `/继续`：以按下时在册活跃玩家开下一轮（人员变化规则见 §三），轮次 +1，从当前最小活跃序号轮起；`/结束游戏` 任意时刻结束
7. 中途加入：见 §二；中途退出：见 §三；剩余 <2 人自动结束

## 二、指令与状态机

| 指令 | 状态 | 行为 |
|---|---|---|
| `/真心换真心` | 无对局 | 开报名局（发起者=host），群需启用该游戏 |
| `/真心换真心数据` | 任意 | 本群历史统计 |
| `/问题 <内容>` | asking 且轮到自己 | 记为问题，进入 answering；`/问题 跳过` = 本题作废轮转下一位 |
| `/真心 <内容>` | answering 且未答参与者 | 记为回答（重复发→拒绝提示）；`/真心 跳过` = 记拒答 |
| `/加入` | asking/answering（中途加入） | 追加到轮转末尾（新序号），见 §三 |
| `/继续` | round_complete 且活跃 ≥2 人 | 下一轮，轮次 +1，回到 asking；任意当前参与者可按；**开轮文案带当前玩家名单与总人数** |
| `/当前游戏` | 任意活跃态 | 显示状态进度 + **当前玩家名单与总人数**（复用共享指令，加 truth_trade 分支） |

状态：`signup → asking ⇄ answering → round_complete →（/继续 回 asking）`；终态 `finished/cancelled`（CheckConstraint）。`/结束游戏` 从任何活跃态可结束（任意参与者）。

懒超时（无定时器，消息驱动）：进入 asking/answering 时记 `phase_deadline`；该群下一条消息到达时检查，提问超时（默认 300 秒）→ 跳过该提问者轮转下一位；回答超时（默认 600 秒）→ 未答者统一记"超时未答"，直接出摘要轮转。

## 三、中途加入 / 退出 / 津贴（修订定案）

**中途加入**（`/加入` 在 asking/answering 也放行）：
- 追加到轮转末尾，分配新序号（position = 当前最大 +1）
- **回答义务从下一个问题起算**：每条问题行存 `required_player_count`（提问时在册人数）；序号 > 该值的玩家免答当前题——即加入时正在收集回答的那题不用答
- 自己的提问轮：轮转到其序号时正常提问（追加在末尾 = 本轮最后一个提问位；若本轮已过其位置则下一轮）
- signup 阶段加入 = 普通报名；退出后重新 `/加入` 按中途加入处理（新序号）

**中途退出**（`/退出` 任意活跃态放行）：
- signup：直接移除
- asking（轮到 TA 提问）：跳过 TA 的问题，轮转下一位
- answering（当前题未答）：TA 免答（不计入 required），不阻塞当题收集
- 已产生的提问/回答记录与统计保留
- 剩余 <2 人 → 自动结束并结算

**`/继续` 的人员变化处理**：
- 参与资格以按下 `/继续` 时刻的在册活跃玩家（state=active）为准：本轮中途加入者自动进入下一轮，已退出者自然排除——**不冻结开局面名单**
- 序号沿用不重编（缺号不影响轮转顺序），每轮从当前最小活跃序号轮起（1 号退了就从 2 号起）
- round_complete 期间 `/加入`、`/退出` 照常适用：此时无开放问题，新加入者下一轮全勤（无免答），退出者直接移除
- 按下时活跃 <2 人 → 拒绝并提示（可 `/结束游戏` 收尾或重新 `/真心换真心` 报名）
- 任意当前参与者可按 `/继续`（host 已退出不影响）；下一轮全员重新获得提问与回答义务，`required_player_count` 按各题提问时在册数重新快照

**小游戏娱乐部津贴**（对齐其他 7 款游戏的挂钩模式）：
- **开局奖励**：`/开始`（真正开局点，非 signup）给发起人 `dept_game_host` +1
- **参与奖励**：每轮结算（全员问完出摘要）时 `_bump_department_game_plays` 给本轮参与者各计 1 局，每满 5 局 +1；中途 `/结束游戏` 当轮未结算时也计 1 局；轮次完毕后再 `/结束游戏` 不重复计——games 表加 `settled_rounds` 列做防重守卫
- 部门绑定走既有 `allowance_kind="game"`，后台零改动

## 四、数据模型（迁移 81，5 张表）

| 表 | 关键字段 | 约束 |
|---|---|---|
| `truth_trade_settings` | group_chat_id、question_timeout_seconds(300)、answer_timeout_seconds(600)、min_players(2) | 群唯一，repository 懒创建 |
| `truth_trade_games` | group_chat_id、host_user_id、state、round_number、settled_rounds、current_position、phase_deadline、signup_at、finished_at | 群内唯一活跃（部分唯一索引）、state Check |
| `truth_trade_players` | game_id、user_id、position、state(active/withdrawn) | unique(game_id, user_id)、unique(game_id, position) |
| `truth_trade_questions` | game_id、asker_player_id、content、round_number、required_player_count、state(open/collected/skipped)、asked_at | unique(game_id, round_number, position) |
| `truth_trade_answers` | question_id、user_id、content、state(answered/declined/timed_out/left)、answered_at | unique(question_id, user_id) |

命名对齐现有游戏（never_have_i_ever 系列同款风格），时间列用北京时间列类型。

## 五、代码接入点

- **group_games.py**（4 处）：`truth_trade` 加入 TypeAlias/GROUP_GAME_TYPES/GROUP_GAME_LABELS（真心换真心）/GROUP_GAME_COMMANDS（`/真心换真心`、`/真心换真心数据`、`/问题`、`/真心`）
- **schema.py**：5 张表 + Base 注册
- **迁移 81**：`20261002_81_truth_trade.py` 建表（settings 全群默认行由 repository 懒创建，不在迁移插数据）
- **repository.py**：`_COMMAND_DEFINITIONS` 种子 4 指令；settings 懒取；start/join（含中途加入）/begin/ask/answer/leave/end/continue/statistics + 懒超时 + 津贴两挂钩点；`active_gameplay_summary` 加 truth_trade 分支；`truth_trade_view`（状态/进度/名单/总人数）供 `/当前游戏` 与 `/继续` 文案共用
- **commands.py**：`_COMMANDS` 加 4 指令；`/真心换真心`、`/真心换真心数据`、`/问题`、`/真心` 分支；共享指令 5 处 `summary.game_type == "truth_trade"` 路由（begin/join/leave/end + `/当前游戏`）；帮助分区"真心换真心"条目
- **后台**：群管理游戏复选框自动出现（admin.js 从 GROUP_GAME_TYPES 渲染），零改动

## 六、文案

- 开局：【真心换真心】报名开启，发送 /加入 报名；至少 2 人后发起者 /开始
- 提问轮：【真心换真心】第 R 轮 · 轮到 N号 名字 提问，发送 /问题 你的问题（超时 X 秒自动跳过）
- 回答轮：【真心换真心】N号 的问题：{问题}\n其他人发送 /真心 你的回答（/真心 跳过 可拒答）
- 摘要：【真心换真心】N号 的问题收集完毕：逐条"名字：回答/拒答/超时未答/中途退出"
- 结算：【真心换真心】第 R 轮结束 + 提问/回答排行 + "/继续 开下一轮，/结束游戏 结束"
- 继续开轮：【真心换真心】第 R+1 轮开始（共 M 人）：1号 A、2号 B…\n轮到 N号 名字 提问，发送 /问题 你的问题
- 当前游戏：【真心换真心】第 R 轮 · <轮到 N号 X 提问 / 收集 N号 的问题回答（已答 k/M）> \n当前玩家（共 M 人）：1号 A、2号 B…

## 七、测试

- 报名：开局/重复加入/人数不足开始被拒/群未启用被拒/与他人对局冲突
- 轮转：提问→全员回答→自动轮转→全员问完自动结算；`/问题 跳过` 与 `/真心 跳过` 双语义
- 中途加入：asking/answering 加入免答当前题、本轮末位提问、重新加入新序号
- 退出：各态退出边界/剩余 1 人自动结束/记录与统计保留
- 超时：提问超时跳过/回答超时记未答（可注入时钟）
- `/继续`：按按下时活跃名单开下一轮（含中途加入者、排除退出者）/序号沿用/round_complete 期间进出/活跃 <2 拒绝/仅轮次完毕态可继续/任意参与者可按
- 名单显示：`/当前游戏` 各态含玩家名单与总人数；`/继续` 开轮文案含名单与总人数（人数随中途加入/退出正确变化）
- 津贴：开局 host +1（绑定 game 部门）/每轮结算计 1 局/每满 5 局 +1/中途结束防重
- 统计：/真心换真心数据 跨局累计
- 迁移 81：建表 + downgrade

## 八、交付

迁移 81 + 代码 + 测试，本地全绿后提交推送，随下次部署上线。无后台新 UI。

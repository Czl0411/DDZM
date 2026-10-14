# 群聊你画我猜 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 已入职群友通过独立游戏卡完成 3～8 人轮流作画、猜词计分、观战及断线重连。

**Architecture:** 新建独立纯规则、事务仓储、HTTP/SSE 和 H5 模块，使用现有员工数据库和 Bot 出站。服务端权威判题及计时，画布批量追加事件并按游标同步，不复制斗地主的全量快照轮询实现。

**Tech Stack:** Python、FastAPI、SQLAlchemy、Alembic、PostgreSQL；原生 JavaScript/CSS/Canvas、Gamefy SDK；pytest、Node test、Playwright。

**Spec:** `docs/superpowers/specs/2026-10-14-dzmm-drawguess-design.md`，已获用户确认，提交 b29c436。

## Global Constraints

- 在当前分支逐项实施；保留现有斗地主未提交修改、`.env` 和平台目录；不全量暂存，不提交密钥。
- 3～8 人，每人画两次；三选一、15 秒选词、90 秒作画、5 秒揭晓。候场入座码四位数字，10 分钟有效。
- 猜中得 `50 + floor(50 × 剩余毫秒 / 90000)`，范围 50～100；画手每人次 20 分；一次结算；并列名次 1、1、3。
- 继续信任 SDK UID，并明确可冒名风险；不接摸鱼币、津贴或管理权限；不增加 token 依赖。
- 画手及已猜中者本题不可发自由文字；观众全程只读；正确答案在揭晓前不得出现在其余玩家的任何响应或日志中。
- 画布 4:3，100ms 批量发送，单批最多 256 点、16 KiB，每题最多 30,000 点。文字最多 100 字、每人每秒一次。
- Gamefy 沙箱不用 localStorage、sessionStorage 或 URL hash；网络 8 秒超时、重试有界；触控目标至少 44px。
- 新 Gamefy 卡 ID 未提供：本地开发不受阻，但禁止覆盖 3761638/3763357，发布和开放正式群另行执行授权步骤。
- 每任务先记录失败测试，再最小实现，通过测试后只提交本任务文件；本计划审阅前不实施。

## Review Focus

- 超时与正确猜测同时到达：截止时间为边界，截止时拒绝计分（任务 1、3）。
- 断线恢复期间清空/换题：快照游标和题 ID 阻止旧笔触复活（任务 3、6）。
- 改请求 ID 以外的载荷或重复重发：不重复加分/绘画，冲突载荷明确拒绝（任务 3）。
- SDK 延迟、切换账号及 KV 失败：大厅可用、不泄漏前一个 UID 的私有词语（任务 6）。
- 中文输入法、触摸取消及键盘遮挡：不误发送、不连接意外笔触、输入仍可见（任务 6）。

## 文件、数据和接口约定

新增 `src/dzmm_bot/core/drawguess_words.py`（词库及规范化）、`drawguess_state.py`（纯状态）、`drawguess_repository.py`（事务/投影）、`drawguess_api.py`（协议）。模型追加到 `core/schema.py`，Mixin 接入 `core/repository.py`，不重构现有游戏。

State 为可 JSON 序列化 dict：`phase, seats, ready, host, scores, match_id, turn_id, turn_index, candidates, word_id, guessed, deadline_ms, version`。seats 使用内部员工 ID 字符串；候场八席，开局压缩成固定参赛顺序。阶段为 `waiting/selecting/drawing/revealing/finished/closed`。服务端时间统一 epoch 毫秒；API 时间字段同名同单位，前端以 server_time_ms 校准。

纯状态接口：`new_state(host: str, now_ms: int) -> dict`；`apply_action(state: dict, actor: str, action: str, payload: dict, now_ms: int, candidates: list[str]) -> dict`；`advance(state: dict, now_ms: int, candidates: list[str]) -> dict`；均返回新状态不改输入，非法抛 ValueError。候选随机抽取在仓储层，纯函数不调用网络或随机数。

仓储接口：`create_drawguess_room(platform_id, group_chat_id, inbound_id, now) -> dict`；`list_drawguess_rooms(platform_id, now) -> list[dict]`；`drawguess_view(room_id, platform_id, now) -> dict`；`drawguess_action(room_id, platform_id, turn_id, version, request_id, action, payload, now) -> dict`；`drawguess_strokes(room_id, platform_id, turn_id, request_id, operations, now) -> dict`；`drawguess_chat(room_id, platform_id, turn_id, request_id, text, now) -> dict`；`drawguess_events(room_id, platform_id, after, now) -> dict`；`advance_drawguess_deadlines(now) -> int`。ID 类型 UUID、platform_id 为 str、now 为带时区 datetime，操作 payload 为 dict，operations 为 list[dict]。API 只调用这些接口，不直接写表。

快照含公开 state 投影、`room_id, cursor, server_time_ms, canvas, messages, self_seat`。`candidates` 只在选词时给画手，`answer` 在作画时仅画手有、揭晓后全员有。画布事件 `{seq, turn_id, op, stroke_id, points, color, width}`；op 为 `begin/append/end/undo/clear`，非相关字段禁止提交。坐标和笔宽为归一化有限数值；三个宽度为 0.003、0.008、0.016，橡皮为显式工具字段，不接受任意混合模式。

## Task 1：词库、轮转及计分纯规则

**Files:** 新增 `src/dzmm_bot/core/drawguess_words.py`、`drawguess_state.py`；测试 `tests/core/test_drawguess_state.py`、`test_drawguess_words.py`。

**Interfaces:** 产出上述纯状态接口；另 `normalize_guess(text: str) -> str`、`guess_score(remaining_ms: int) -> int`；词库 WORDS 为含 id、answer、aliases 的元组，至少 100 个易画日常词，唯一 id/规范化答案。

- [ ] 写 `test_score_boundaries`：断言 guess_score(90000)==100、guess_score(45000)==75、guess_score(0)==50；仓储截止拒绝另测，评分函数夹紧范围。
- [ ] 写 `test_three_and_eight_players_draw_twice`：2 人/未全准备不能开始；3/8 人各完成 6/16 题；每人两次，顺序固定；全部猜中提前揭晓、5 秒切题、最后排名同分为 1、1、3。
- [ ] 写 `test_timeout_and_secrecy_rules`：15 秒自动选词、90 秒揭晓、不暂停断线玩家；重复正确猜测不计分，画手/观众猜词拒绝。
- [ ] 写 `test_words_and_normalization`：词库无重名，NFKC、首尾空白和大小写通过；同义词仅显式别名，包含答案长句拒绝；16 题抽词不重复已用答案。
- [ ] 运行 `.venv/bin/python -m pytest tests/core/test_drawguess_state.py tests/core/test_drawguess_words.py -q`，确认缺实现失败，再实现规则及词库，重跑全部通过。
- [ ] `git diff --check`；仅提交上述四文件：`feat: add drawguess rules and word bank`。

## Task 2：独立持久化模型及迁移

**Files:** 修改 `src/dzmm_bot/core/schema.py`；新增 `migrations/versions/20261014_110_drawguess.py`、`tests/deploy/test_drawguess_migration.py`。

**Interfaces:** 新模型 DrawguessRoomRecord（群、唯一入站消息、短号、可空唯一 active_code、state JSON、cursor、deadline、phase）；DrawguessEventRecord（room_id+seq 唯一、turn_id、operation JSON）；DrawguessRequestRecord（room_id+user_id+request_id 唯一、digest、turn_id）；DrawguessMessageRecord（room_id、turn_id、user_id、内容、时间）。事件表仅存公开画布操作，不存答案；聊天正确反馈存“已猜中”。

- [ ] 写 `test_upgrade_downgrade_and_constraints`：迁移升级后四表、外键、唯一入站、唯一 active_code、事件序号和请求去重成立；降级不影响现有游戏表。
- [ ] 运行 `.venv/bin/python -m pytest tests/deploy/test_drawguess_migration.py -q` 记录失败。实施前读取 Alembic heads；当前头为 20261013_109，若改变则同步新文件 revision/down_revision，禁止分叉迁移头。
- [ ] 最小追加四模型及迁移。候场关闭/开局清空 active_code，分配码使用唯一约束及有界冲突重试；用独立测试 PostgreSQL 验证，不接生产库。
- [ ] 重跑迁移测试通过，检查 downgrade；提交限定三文件：`feat: persist independent drawguess rooms`。

## Task 3：事务、幂等、答案投影与画布增量

**Files:** 新增 `src/dzmm_bot/core/drawguess_repository.py`、`tests/core/test_drawguess_repository.py`、`test_drawguess_concurrency.py`；修改 `core/repository.py` 接入 Mixin。

**Interfaces:** 实现文件约定中全部仓储接口；消费任务 1 状态和任务 2 模型。事件结果 `{cursor, reset, events, snapshot}`；过旧游标/换题返回 reset=true 和原子快照，普通增量含公开画布 events，状态版本改变时附接收者专属 snapshot。

- [ ] 写 `test_claim_ready_start_and_rematch`：只允许员工，八席上限，重复入站只一房，过期码拒绝，房主转移，全员准备才开局，中途仅观众；再开清零、取消准备并换码。
- [ ] 写 `test_deadline_guess_race_and_idempotency`：同请求重发不重复计分，载荷改变拒绝；now==deadline 不计分；重启跨期限按原 deadline 推进，有限批次，不出现无限循环。
- [ ] 写 `test_recipient_projection_never_leaks_words`：画手/猜手/猜中者/观众，列表、快照、事件投影均检查；答对原文不入公共消息，错误猜测纯文本；按设计阶段拒绝违规聊天。
- [ ] 写 `test_stroke_order_limits_and_reset`：当前画手才能绘制，旧 turn_id 拒绝；256 点/16 KiB/30,000 点边界、NaN/Infinity/越界拒绝；撤销清空、重复批次、切题快照及断点游标正确；清空后回收点配额，不删已确认序号造成客户端漏同步。
- [ ] 写 PostgreSQL `test_concurrent_last_seat_and_strokes`：争最后一席仅一人成功，画布序号唯一递增，快照到订阅之间写入不丢；八客户端每 100ms 批量绘画只产生批量写入、无逐点提交。
- [ ] 运行 `.venv/bin/python -m pytest tests/core/test_drawguess_repository.py tests/core/test_drawguess_concurrency.py -q` 记录失败；实现每房行锁、先推进截止再动作、请求摘要去重、100 字/1 秒限流。画布与游戏状态版本分开，笔触不使猜词因版本过期失败。
- [ ] 重跑通过；SQLite 不能替代 PostgreSQL 并发测试。记录真实数据库测试结果；仅提交本任务文件：`feat: add transactional drawguess gameplay and canvas sync`。

## Task 4：HTTP、SSE、Bot 与开关接入

**Files:** 新增 `core/drawguess_api.py`、`tests/core/test_drawguess_api.py`、`test_drawguess_commands.py`、`tests/deploy/test_drawguess_proxy.py`；修改 `core/app.py`、`core/commands.py`、`runtime/settings.py`、`deploy/caddy/dzmm-chess-ip.Caddyfile`，路径均在现有 src/dzmm_bot 下（deploy/tests 除外）。

**Interfaces:** `drawguess_router(repository, clock) -> APIRouter`，前缀 `/api/drawguess`，GET rooms、rooms/{id}、rooms/{id}/events?after=N，POST rooms/{id}/actions、/strokes、/chat。Authorization 为 `DrawguessUid <uid>`；新增 drawguess_game_id/game_url/public_api_url/chatroom_id 配置，缺配置时入口关闭。

- [ ] 写 `test_auth_validation_and_projection`：空 UID 401、非员工 403、坏参数 422、非法阶段 409、限流 429；严格 UUID/整数、不接受额外字段；非画手所有响应无答案；Cache-Control no-store。
- [ ] 写 `test_event_cursor_disconnect_and_backpressure`：订阅时先鉴权，约 200ms 检查增量，无变更仅定期心跳；断开取消查询；最多一次读取 200 事件，落后返回快照，不建无界队列。同步 SQL 在工作线程执行，不阻塞事件循环。
- [ ] 写 `test_command_two_message_types_and_scope`：开放监听群+员工可开；返回第一条 character 卡、第二条 text 入座说明；非开放群不创建；与象棋/斗地主同时开房不互斥；重复出站沿用既有去重路径。
- [ ] 写 `test_proxy_exposes_only_drawguess_routes`：Caddy 允许该 API 和 SSE，保留现有规则，不开放后台或内部维护接口。
- [ ] 运行 `.venv/bin/python -m pytest tests/core/test_drawguess_api.py tests/core/test_drawguess_commands.py tests/deploy/test_drawguess_proxy.py -q`，记录失败后实现上述接口、配置传递、定时推进及代理；重跑通过。
- [ ] 回归现有 `test_doudizhu_commands.py` 与 `test_doudizhu_proxy.py`；仅提交任务文件：`feat: connect drawguess API and group command`。

## Task 5：可测试 Canvas 与传输客户端

**Files:** 新增 `gamefy/drawguess/publish/canvas.js`、`client.js`、`config.js`；新增 `gamefy/drawguess/tests/canvas.test.mjs`、`client.test.mjs`。

**Interfaces:** `createCanvas(element, {onBatch}) -> {setEditable, applyEvents, restore, setTool, undo, clear, destroy}`；`createClient(config) -> {identity, rooms, snapshot, action, strokes, chat, follow, dispose}`。follow(roomId,cursor,onUpdate,onError) 返回取消函数；所有写请求生成并保留 request_id，重试不得换 ID。

- [ ] 写 `canvas.test.mjs`：比例坐标/三个笔宽、批次 100ms、序号去重、题目切换丢弃旧事件、撤销清空、pointercancel 不连下一笔。
- [ ] 写 `client.test.mjs`：8 秒超时、初始失败可手动重试；画布同批最多三次指数退避，仍失败停止新绘画并显示重连；恢复快照后重新核对未确认批次，不无界累积；取消旧 follow 不再回调。
- [ ] 运行 `node --test gamefy/drawguess/tests/*.test.mjs` 记录失败，实现上述接口，SDK 获取 UID、KV 定位但不依赖 KV 成功，使用平台兼容的 UUID 生成路径。
- [ ] 重跑通过；只提交新增文件：`feat: add drawguess canvas and realtime client`。

## Task 6：完整原创移动 UI 与沙箱流程

**Files:** 新增 `gamefy/drawguess/publish/index.html`、`style.css`、`game.js`、`gamefy/drawguess/tests/test_drawguess_sandbox.py`。

**Interfaces:** game.js 消费任务 5 客户端与 Canvas、任务 3 快照；单一页面状态保存当前房间和导航代次，所有异步结果检查代次及 UID。SDK KV key 为 `drawguess:last-room:<uid>`，不存答案或积分。

- [ ] 写沙箱测试 `test_full_game_mobile_and_desktop`：320/390px、1280px，无横向溢出；候场八席、准备原因、房主开始、选词/倒计时、画手工具、猜手输入、揭晓积分、全员排名及再开流程；没有裸 UUID 主标题。
- [ ] 写 `test_keyboard_touch_and_permissions`：IME composition 时回车不发送，键盘出现输入可见；画布阻止滚动但页面其余可滚；三类禁输入原因明确，按钮至少 44px；清空取消后画布不变。
- [ ] 写 `test_boot_restore_and_identity_change`：SDK 延迟超时后可重试，KV 失败仍可进大厅，重开恢复本人房间、返回大厅清定位；切账号清旧私有词语；URL hash 始终不变；旧房间慢响应不能覆盖新房间。
- [ ] 写 `test_reconnect_during_clear_and_next_turn`：绘画中断线、清空/换题后恢复，画布一致，无重复得分，无永远 loading；只有可交互页面出现才 loading.ready。
- [ ] 运行 `.venv/bin/python -m pytest gamefy/drawguess/tests/test_drawguess_sandbox.py -q` 记录失败，然后实现暖白/珊瑚橙/蓝色原创界面，桌面画布+侧栏、手机上方头像画布下方消息。用 fake SDK/后端测试，不向平台发送模拟聊天。
- [ ] 重跑通过并逐张查看关键阶段截图，修正布局；不把 Chromium 模拟标为 iPhone Safari 实测。只提交任务新增文件：`feat: build mobile drawguess game interface`。

## Task 7：完整联调、回归与发布交接

**Files:** 新增 `tests/core/test_drawguess_end_to_end.py`、`docs/drawguess-deployment.md`、`gamefy/drawguess/README.md`；仅在用户提供新卡后生成本游戏 dzmm.json，不预填旧卡 ID。

**Interfaces:** 使用已完成的公开 API 与配置，交付可本地运行的 H5、后端及真实测试记录；外部发布为条件步骤，不因无卡 ID 阻止本地交付。

- [ ] 写 `test_three_players_six_turns_and_restart`：通过 API 开局、各画两次、含答错/答对/断线/超时，重建 repository 后继续；最终积分精确匹配，不涉及任何余额变动，观众不能操作。
- [ ] 运行 `.venv/bin/python -m pytest tests/core/test_drawguess_*.py tests/deploy/test_drawguess_*.py gamefy/drawguess/tests/test_drawguess_sandbox.py -q` 及 Node 测试，先核实集成测试失败原因，再修复本功能问题并重跑。
- [ ] 运行象棋/斗地主针对性回归（通过 `rg --files tests gamefy` 取实际测试文件），最后尝试完整 pytest；既有环境或基线失败单独记录，不宣称全绿。检查 `git diff --check` 和新增文件无密钥。
- [ ] 在本地八客户端绘画基准记录事件延迟、写入批次数和重连行为；验收目标为无积压、无丢笔，给出测量结果而非声称覆盖生产负载。
- [ ] 请求独立代码审查，重点答案泄漏、事务竞态及事件顺序；修复重要发现再回归，不连带修改无关功能。
- [ ] 编写启动配置、迁移/备份/回滚和测试记录；真实 Safari/Android 及三人联调若无设备/参与者标为尚待验证，不能自动勾选。只提交交接文件及必要修复。
- [ ] 发布前取得新游戏 ID 与测试群发布授权，先读该项目生成的平台说明，CLI 校验、部署、预览，用户验收后再上架/开放正式群。不在此计划批准时自动推送或部署生产。

## 执行交接

建议沿用当前会话由主助手逐项实施，最后独立审查；接口依赖紧密，首版无需并行改同一仓储/状态层。待用户审阅本计划后，执行 executing-plans；已确认当前分支开发，不自行切换工作区。每任务记录红/绿测试和 scoped commit，完成时区分“本地实现”“测试验证”“已部署”。

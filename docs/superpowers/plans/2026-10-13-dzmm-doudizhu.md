# 群聊斗地主 Implementation Plan

执行状态（2026-10-13）：已按用户确认在当前分支实现任务 1～7，并完成独立审查的重要问题修复。下列步骤保留为原始实施计划；真实验证结果、暂缓问题和未完成的发布闸门见 `docs/doudizhu-deployment.md`。尚未推送或部署。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 已入职群友可通过独立 Gamefy 卡完成三人经典斗地主、重连、观战聊天及中文群结算，不涉及摸鱼币。

**Architecture:** 现有 Python 后端保存权威状态，新建独立规则、持久化和 API 模块；H5 只负责展示与提交操作。按用户明确选择信任 SDK UID，按请求 UID 分发手牌，不承诺防 UID 冒充。通过既有 bot 入站、出站和定时维护接入，不重构象棋。

**Tech Stack:** Python、FastAPI、SQLAlchemy、Alembic、PostgreSQL；原生 JavaScript/CSS、Gamefy SDK、SSE；pytest、Node test、Playwright。

**Spec:** `docs/superpowers/specs/2026-10-13-dzmm-doudizhu-design.md`（b067c82 修订）。

## Global Constraints

- 当前分支开发，保留现存未跟踪文件，不提交 `.env`、开发凭证、平台本地状态或数据库。
- 独立 Gamefy 游戏卡，不覆盖象棋卡 3761638；正式群 `4fc4a2fd-465a-4436-9884-dbb5e60c6af2`。
- 54 张牌、17/17/17 加 3 底牌；叫 1/2/3 分，叫分 15 秒、出牌 25 秒，无总时钟。
- 四位入座码 10 分钟有效，三人准备才发牌；连续三副全不叫取消。
- 不做付费 AI、摸鱼币、积分、自动匹配、癞子、抢地主或付费素材。
- 不要求 JWT、私聊验证码或登录令牌；伪造有效 UID 可冒充玩家，这属于明确接受的限制。
- 聊天 1～300 字、每人至少间隔 2 秒；终局停止写入，新局独立。
- 平台沙箱不支持表单提交；按钮显式绑定点击与键盘事件。
- 所有新增任务遵循先失败测试、最小实现、验证、仅提交该任务文件；不自行推送或部署正式环境。

## Review Focus

- 发牌后调用公开列表、错误响应、SSE 重连：不得误带其他席位手牌或未公开底牌（任务 4）。
- 请求 ID 重用但载荷不同：拒绝，不能把旧成功结果视为新出牌成功（任务 3）。
- 服务重启期间跨越多个截止时间：有限批次推进并保留原期限，不拖慢 bot 队列（任务 3）。
- Gamefy SDK UID 读取失败后恢复、切换账号：不得沿用前一 UID 的私有快照（任务 6）。
- 手机滑选触发滚动或重复 pointer 事件：每张牌只切换一次，松手取消仍不自动出牌（任务 6）。

## 文件与接口约定

新增规则模块 `src/dzmm_bot/core/doudizhu_rules.py`，牌 ID 为整数 0～53，0～51 按 3～2 每四张一组，52 小王、53 大王。`rank(card: int) -> int` 返回 3～17。

新增纯状态模块 `doudizhu_state.py`，新建局次状态与行动归约；新增 `doudizhu_repository.py` 管事务、幂等和投影；新增 `doudizhu_api.py` 管 HTTP/SSE。共享类型各在定义模块导出，不复制定义。

数据库模型只追加到 `schema.py`，Mixin 加到现有 `CoreRepository`。接入文件限于 `core/commands.py`、`core/service.py`、`core/repository.py`、`core/app.py`、`runtime/settings.py`。新前端全部放 `gamefy/doudizhu/`。

## Task 1：牌型与合法提示

**Files:** 新增 `src/dzmm_bot/core/doudizhu_rules.py`、`tests/core/test_doudizhu_rules.py`。

**Interfaces:** `Pattern(kind: str, high: int, length: int, cards: tuple[int, ...])`；`patterns(cards: tuple[int, ...]) -> tuple[Pattern, ...]`；`choose_pattern(cards: tuple[int, ...], previous: Pattern | None) -> Pattern`（非法抛 `ValueError`）；`legal_plays(hand: tuple[int, ...], previous: Pattern | None) -> tuple[Pattern, ...]`。提示按主体点数、牌数、牌 ID 稳定排序，炸弹和王炸排普通应手之后。

- [ ] 写参数测试 `test_all_patterns_and_boundaries`：所有设计牌型；3～A 连续有效、含 2/王无效；顺子 4 张失败、5 张通过；连对 2 对失败、3 对通过。
- [ ] 增加 `test_wings_and_ambiguous_airplanes`：设计中的成对单翅膀通过，主体点数翅膀、双王翅膀、四同点数翅膀拒绝；多解释采用设计指定主体。
- [ ] 增加 `test_illegal_card_ids_and_duplicates` 与 `test_suggestions_are_legal_subsets`：-1、54、重复牌拒绝；提示均是手牌子集且可压前牌，20 张手牌提示不枚举全部排列。
- [ ] 运行 `.venv/bin/python -m pytest tests/core/test_doudizhu_rules.py -q`，先记录因缺少规则实现失败。
- [ ] 实现上述函数；按点数计数组合生成牌型和提示，不穷举 20 张牌的所有子集。依次通过测试。
- [ ] `git diff --check` 后仅提交规则与测试，提交消息 `feat: add classic doudizhu card rules`。

## Task 2：纯局次状态、叫分、计时与胜负

**Files:** 新增 `src/dzmm_bot/core/doudizhu_state.py`、`tests/core/test_doudizhu_state.py`。

**Interfaces:** `new_round(deck: tuple[int, ...], first: int, now: datetime) -> dict`；`apply_action(state: dict, seat: int, action: str, payload: dict, now: datetime) -> dict`；`apply_timeout(state: dict, now: datetime) -> dict`。状态为 JSON 可序列化值，UTC 截止时间字符串；包含 hands、bottom、phase、turn、landlord、bid、passes、previous、play_counts、multiplier、deadline、trustees、result、events。归约返回新状态不原地改输入；重发由仓库提供新牌，不在归约函数调用随机源。

- [ ] 写 `test_deal_and_bidding`：发牌 17/17/17/3、54 张守恒；3 分立即结束，低于当前叫分拒绝；全不叫产生 `redeal` 状态。
- [ ] 写 `test_turns_passes_and_victory`：领出不能过，两次过牌归最后出牌者；农民任一出完共享胜利；炸弹、王炸、春天、反春倍数符合设计。
- [ ] 写 `test_timeout_and_takeover`：叫分截止正好 15 秒触发不叫、出牌 25 秒触发托管；领先最小单张，跟牌过；取消托管不撤销已处理行动。
- [ ] 写 `test_illegal_actions_leave_input_unchanged`：越席、重复牌、不属于手牌、终局行动均拒绝且不改原状态。
- [ ] 运行 `.venv/bin/python -m pytest tests/core/test_doudizhu_state.py -q` 确认失败，再实现并连同规则测试运行通过。
- [ ] 仅提交本任务文件，消息 `feat: add authoritative doudizhu round transitions`。

## Task 3：持久化、入座、准备与恢复

**Files:** 新增 `src/dzmm_bot/core/doudizhu_repository.py`、`tests/core/test_doudizhu_repository.py`、`tests/deploy/test_doudizhu_migration.py`；修改 `core/schema.py`、`core/repository.py`；新增 `migrations/versions/20261013_109_doudizhu.py`（执行前确认 HEAD 仍为 108，如已变化按真实迁移链分配编号）。

**Interfaces:** `DoudizhuRepositoryMixin.create_doudizhu_room(platform_id: str, group_chat_id: UUID, inbound_id: UUID, now: datetime) -> dict` 返回开局内部信息；`doudizhu_action(room_id: UUID, platform_id: str, round_id: UUID | None, version: int, request_id: UUID, action: str, payload: dict, now: datetime) -> dict` 返回请求者视图；`advance_doudizhu_deadlines(now: datetime) -> int`；`doudizhu_view(room_id: UUID, platform_id: str, now: datetime) -> dict`；`list_doudizhu_rooms(platform_id: str, now: datetime) -> list[dict]`。

模型：`DoudizhuRoomRecord` 保存创建者、原群、唯一入站 ID、短编号、码、席位/准备、等待截止、当前局次和版本；`DoudizhuRoundRecord` 保存局次号、私有状态与结果；`DoudizhuRequestRecord` 对房间/用户/请求 ID 唯一，保存载荷摘要和处理结果标记，不保存对外手牌响应；`DoudizhuMessageRecord` 保存房间/局次/用户/纯文本/时间。终局出站业务键对局次唯一。

- [ ] 写 `test_create_dedup_and_two_claims`：同入站只建一房；码 4 位；文字未送达不能加入；两个不同员工先到先得，重复本人不重复占位，10 分钟截止拒绝。
- [ ] 写 `test_ready_leave_and_rematch`：第三人准备只发一次；房主等待期离开取消，其他人释放席位；新局次拒绝旧请求；首发后席位不释放。
- [ ] 写 `test_concurrent_claim_and_timeout`：真实 PostgreSQL 隔离测试数据库并发争最后席位、准备/超时/出牌竞态只推进一次。没有测试数据库时明确标记未验证，不以 SQLite 锁语义代替。
- [ ] 写 `test_request_id_payload_conflict`、`test_redeal_limit_and_restart`：同 ID 同载荷重试不重复操作，不同载荷拒绝；第三次全不叫取消；时钟重启不重置，每次维护最多推进每房间一次、最多 100 房间，下一轮继续。
- [ ] 写迁移测试：升级保留既有员工/象棋数据、降级仅移除本次新增表；运行相关测试确认失败。
- [ ] 实现行锁事务、条件版本更新、唯一键幂等；使用 `secrets.SystemRandom().shuffle` 洗牌。等待阶段 `round_id=None`，首发后每局新 UUID；再来一局设置新的 10 分钟准备期限。托管行动仍按截止触发，防同事务无限自动推进。
- [ ] 运行 `.venv/bin/python -m pytest tests/core/test_doudizhu_repository.py tests/deploy/test_doudizhu_migration.py -q`，另运行 PostgreSQL 并发用例；检查并提交精确文件，消息 `feat: persist doudizhu rooms and atomic actions`。

## Task 4：UID API、私有视图、SSE 与聊天

**Files:** 新增 `src/dzmm_bot/core/doudizhu_api.py`、`tests/core/test_doudizhu_api.py`；修改仓库模块及 `core/app.py`。

**Interfaces:** `doudizhu_router(repository: CoreRepository, clock: Callable[[], datetime]) -> APIRouter`；`Authorization: DoudizhuUid <uid>`。GET `/api/doudizhu/rooms`、GET `/rooms/{id}`、GET `/rooms/{id}/events`；POST `/rooms/{id}/actions` 使用任务 3 行动信封；POST `/rooms/{id}/chat` 使用 `round_id, request_id, text`。行动为 claim/ready/unready/leave/bid/play/pass/takeover/resume/rematch，payload 分别只允许需要的字段。聊天另有 `doudizhu_chat(room_id, platform_id, round_id, request_id, text, now) -> dict` 仓库方法。

- [ ] 写 `test_uid_and_public_private_views`：缺失/非法/未入职拒绝；四个 UID 分别获取自己的视图，隐藏手牌不出现在列表、观众、错误响应或未叫分底牌中；明确有效 UID 冒充不在防御范围。
- [ ] 写 `test_sse_reconnect_is_recipient_scoped`：每连接按 UID 投影，不复用别人的缓存；重连先快照；失效/移除员工后终止连接；取消连接释放循环。
- [ ] 写 `test_chat_limits_idempotency_and_round_scope`：0/301 字拒绝、1/300 字通过、两秒边界、重试只发一次、HTML 作为文本，终局只读、旧局消息不混入新局。
- [ ] 运行 `.venv/bin/python -m pytest tests/core/test_doudizhu_api.py -q` 确认失败，再实现；所有响应 `Cache-Control: no-store`，不记录隐藏手牌；聊天版本与牌局行动版本分开避免发言使出牌失效。
- [ ] UID 有效性每次请求查询员工；异常只返回明确中文错误。SSE 沿用现有可用传输方式，不新加消息中间件。运行任务 1～4 全部测试，通过后提交 `feat: expose UID-scoped doudizhu API and chat`。

## Task 5：群聊入口与中文结算

**Files:** 修改 `core/commands.py`、`core/service.py`、`core/repository.py`、`core/app.py`、`runtime/settings.py`、斗地主仓库；新增 `tests/core/test_doudizhu_commands.py`；补充 `tests/runtime/test_settings.py`。

**Interfaces:** 设置 `DZMM_DOUDIZHU_GAME_ID`、`DZMM_DOUDIZHU_GAME_URL`、`DZMM_DOUDIZHU_PUBLIC_API_URL`、`DZMM_DOUDIZHU_CHATROOM_ID`，缺省不启用。`/斗地主` 不占已有游戏互斥锁。已有维护入口调用 `advance_doudizhu_deadlines`。

- [ ] 写 `test_command_requires_config_employee_and_allowed_group`：未配置给未开放提示，不创建房间；员工/群检查符合设计。
- [ ] 写 `test_command_shares_card_then_text`：两条 `CommandReply`，首条 character 分享真实新卡 ID，次条文字含 4 位码/10 分钟/两空位说明，无拼接长 URL。
- [ ] 写 `test_finish_notice_once_without_currency`：含地主/两农民姓名、胜负、倍数和中文原因，无 UUID/英文结果码；重试维护不重复结算，余额与流水不变。
- [ ] 先跑新增测试失败，再最小接入指令注册、帮助、设置传递、文字送达门槛和终局出站；不修改其他群指令。
- [ ] 运行 `.venv/bin/python -m pytest tests/core/test_doudizhu_commands.py tests/core/test_chess_commands.py tests/runtime/test_settings.py -q`；通过后提交 `feat: integrate group doudizhu invitations and results`。

## Task 6：Gamefy 牌桌、选牌、聊天与重连

**Files:** 新增 `gamefy/doudizhu/publish/index.html`、`style.css`、`game.js`、`client.js`、`cards.js`、`config.js`；新增 `gamefy/doudizhu/tests/client.test.mjs`、`cards.test.mjs`、`test_sandbox.py`；新增 `gamefy/doudizhu/README.md`。平台配置 `dzmm.json` 仅在取得真实独立卡 ID 后创建，不填象棋 ID。

**Interfaces:** `DoudizhuClient` 提供 `identity(), rooms(), snapshot(id), action(id, envelope), chat(id, payload), follow(id, onSnapshot)`，`follow` 返回停止函数；`cards.js` 导出 `cardLabel(id)` 与 `toggleSelection(selected, cardId)`；客户端提示通过 GET `/rooms/{id}/suggestions` 按该 UID 自身手牌调用规则层获取，不下发其他手牌。提示只选牌不提交。

- [ ] 先写 Node 测试：SDK 请求合并、UID 获取失败可重试、账号变化清空快照/订阅、行动 UUID 重试复用、牌标签/排序/重复触碰不翻转。
- [ ] 先写沙箱 Playwright 测试：mock SDK/API，在仅 allow-scripts/allow-modals iframe 下，三人准备、叫分、选牌、提示、不出、聊天、重新打开自动回房、主动回列表均可操作。
- [ ] Node 用 `node --test gamefy/doudizhu/tests/*.test.mjs`；浏览器用 `.venv/bin/python -m pytest gamefy/doudizhu/tests/test_sandbox.py -q`，先确认缺失实现失败。
- [ ] 实现绿绒牌桌与代码绘制牌面，自己下方、对手左上/右上；17～20 张窄屏最多两排；指针滑选使用当次手势 visited 集合，pointercancel 只结束手势不提交。按钮与 Enter 显式绑定，不使用表单提交。
- [ ] 实现身份/入座/准备/叫分/出牌/托管/结果状态，中文牌型提示、1/2 张提醒、炸弹王炸春天短动效；结果显示两位农民共同胜负，观众没有选牌控件。
- [ ] 最近房间只存平台 KV，重开用当前 SDK UID 拉新快照；后台断线不冻结服务端时钟。聊天折叠但等待/对局均能发送，终局只读。
- [ ] 为提示 endpoint 补 API 测试；截图检查 320px、390px、1280px，20 张可见、无遮挡无溢出；测试通过提交 `feat: add mobile Gamefy doudizhu table`。

## Task 7：整体验证与发布准备

**Files:** 新增 `tests/core/test_doudizhu_end_to_end.py`、`docs/doudizhu-deployment.md`；修改 `deploy/caddy/dzmm-chess-ip.Caddyfile` 仅增加 `/api/doudizhu/*` 的同后端代理，不扩大兜底路径；新增路由配置静态检查测试 `tests/deploy/test_doudizhu_proxy.py`。

- [ ] 端到端测试串起群入口、两席位、准备、完整对局、中文结算一次、再来一局及观众；每阶段检查 54 张牌守恒、正确手牌投影、无币流水。
- [ ] 新增代理配置测试：斗地主和象棋路径均保留流式代理，其他路径仍 404。测试失败后补部署模板与操作文档。
- [ ] 运行 `.venv/bin/python -m pytest tests/core/test_doudizhu*.py tests/core/test_chess*.py tests/deploy/test_doudizhu*.py tests/deploy/test_chess_migration.py tests/runtime/test_settings.py -q`，再跑 Node 和沙箱测试；记录 PostgreSQL 并发结果。
- [ ] 运行全套测试并如实区分既有收集失败（缺 DZMM_DATABASE_URL、tests 导入问题）与本次回归，不为通过无关测试修改业务。
- [ ] 自检所有变更对应设计、无秘密/隐藏牌日志、无象棋产品行为变动；执行 `git diff --check`，提交发布准备文件。汇报完成项与真实账号验证/发布未完成项。

## 发布闸门（本地完成不等于已上线）

- [ ] 用户批准上线后才备份线上数据库/代码，创建独立 Gamefy 草稿并记录真实卡 ID；开发密钥不写入仓库或文档。
- [ ] 校验迁移链及回滚步骤，迁移并安装代码，设置测试群及真实卡 ID/API URL，校验 Caddy 配置后重载；只重启受影响服务。
- [ ] Gamefy CLI 校验并部署新卡，不覆盖象棋；需要公开审核时明确交用户确认，不能把预览通过当普通用户可访问。
- [ ] 三个真实账号在测试群完整对局，第四账号观战，包含关闭重开、聊天、托管与群结算；未完成时报告阻塞，不虚报上线成功。
- [ ] 用户批准后开放小游戏群，检查服务健康与 bot 时延，提供提交号、部署版本及回滚备份路径。

## 执行方式

建议在当前会话由主代理按任务顺序实施，沿用当前分支；此计划尚待用户审阅确认。任务间接口相互依赖，先把规则、事务和私有视图验证清楚再接 UI；不在批准前创建新卡或修改线上服务。

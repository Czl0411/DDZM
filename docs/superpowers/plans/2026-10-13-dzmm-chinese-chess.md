# DZMM 群聊象棋 H5 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 群聊 `/象棋` 创建可并行的双人 H5 象棋局，支持先到先得入座、观战、文字聊天、权威计时与断线恢复。

**Architecture:** Gamefy `publish/` 提供棋盘页面和 DZMM 登录 token；现有 DDZM Python 服务持久化棋局、裁判、时钟和聊天，通过带认证的 HTTP/SSE 给页面同步。Bot 只创建入口并在原群发布开局与终局消息，不借用现有群级小游戏互斥槽。

**Tech Stack:** Python 3.12、FastAPI、SQLAlchemy 2、Alembic、PostgreSQL、PyJWT/JWKS、原生 HTML/CSS/JavaScript、DZMM Gamefy SDK、pytest、Node 测试。

**Spec:** `docs/superpowers/specs/2026-10-13-dzmm-chinese-chess-design.md`

## Global Constraints

- 每盘两个不同的已入职账号；发起者占首位，第二位凭创建后 10 分钟内有效的四位码抢座；已入职观众免码。
- 同群多盘、同一人多盘、与现有小游戏并行；不使用 `active_gameplay_summary`、通用 `/加入` 或 `/结束游戏`。
- 红黑随机、红先；每方总时 15 分钟、每步硬上限 60 秒、无加秒；断线不暂停。
- 规则按《中国象棋竞赛规则（2020 版）》，包括长将／长捉，不把三次重复直接判和。
- 悔棋和求和需对方同意；悔一步且不返还耗时；本人确认认输；仅原群有一次终局通告。
- 游戏内棋手与观众均可发纯文字；聊天只属本局、不进入长期史册；首版无摸鱼币、AI、匹配、段位或排行。
- 发布目录文件名仅用 ASCII 字母、数字、`_`、`-`、`.`；浏览器不存 token 到 URL、KV 或日志。

## Review Focus

- 同一玩家打开多盘／多个标签后刷新旧标签，仍恢复旧棋局而非最近打开的一盘：Task 7 测试。
- 群消息未成功发出、入座码过期或被抢时，不产生可入座的隐形／双人第二席棋局：Task 1、Task 6 测试。
- 网络重复提交、SSE 断线重连和 token 过期时，落子与终局只发生一次且页面恢复权威快照：Task 4、Task 5 测试。
- 临界落子与超时、悔棋后继续走钟时，服务端时间裁决唯一：Task 4 测试。
- 非法启动参数、错误 token 受众及未入职账号不能访问棋局或聊天：Task 5、Task 7 测试。

---

### Task 1: 独立棋局持久化和原子抢座

**Files:** Create `migrations/versions/20261013_102_chess.py`, `src/dzmm_bot/core/chess_repository.py`, `tests/core/test_chess_repository.py`; modify `src/dzmm_bot/core/schema.py`, `src/dzmm_bot/core/repository.py`; test `tests/deploy/test_chess_migration.py`.

**Interfaces:** 在 `chess_repository.py` 定义只读 `ChessGameView`（棋局快照）和 `ChessClaimResult`（状态 + 快照）；`CoreRepository.create_chess_game(creator_platform_id: str, group_chat_id: UUID, inbound_id: UUID, now: datetime) -> ChessGameView`; `claim_chess_seat(game_id: UUID, platform_id: str, code: str, now: datetime) -> ChessClaimResult`; `get_chess_game(game_id: UUID) -> ChessGameView`。棋局表保存原群、发起入站／出站 ID、四位码、创建／截止时间、状态、双方用户 ID、红黑、局面、时钟、版本与结果；着法和本局聊天单独存储。不加群或用户的活动局唯一约束。

- [ ] 写失败测试：同群／同人可建多盘、仅已入职发起／入座、创建者不能抢第二席、码过期／错误／已使用失败、两人并发只有一人入座；迁移可升级空库。
- [ ] 运行 `python3 -m pytest tests/core/test_chess_repository.py tests/deploy/test_chess_migration.py -q`，确认预期失败。
- [ ] 加最小模型、迁移和事务锁；第二席只在关联开局 OutboundRecord 已 `sent` 且尚未过期时开放，入座成功同事务决定红黑并进入 `playing`。
- [ ] 重跑上述测试并确认全过；提交此任务文件。

### Task 2: 标准走法与基础终局裁判

**Files:** Create `src/dzmm_bot/core/chess_rules.py`, `tests/core/test_chess_rules.py`.

**Interfaces:** 在 `chess_rules.py` 定义不可变 `ChessPosition`（棋盘 + 行棋方）、`ChessMove`（起终点）、`ChessOutcome`（胜负／和及原因）和 `IllegalChessMove`；`initial_position() -> ChessPosition`; `play_move(position: ChessPosition, move: ChessMove) -> ChessPosition`; `legal_moves(position: ChessPosition) -> tuple[ChessMove, ...]`; `basic_outcome(position: ChessPosition) -> ChessOutcome | None`。坐标固定 `x=0..8, y=0..9`，红方在 `y=9` 侧；非法着不修改输入局面。

- [ ] 写失败测试：车马炮兵仕相帅与黑方对应棋子、蹩马腿、塞象眼、过河兵、炮架、将帅照面、被将时只能解将、将死和困毙。
- [ ] 运行 `python3 -m pytest tests/core/test_chess_rules.py -q`，确认预期失败。
- [ ] 实现纯规则函数；不得把棋规判断放在浏览器端作为最终裁决。
- [ ] 重跑测试并确认全过；提交此任务文件。

### Task 3: 重复局面与 2020 规则裁判

**Files:** Modify `src/dzmm_bot/core/chess_rules.py`, `tests/core/test_chess_rules.py`.

**Interfaces:** 在 `chess_rules.py` 定义 `ChessViolation`（违规方 + 原因）；`adjudicate_repetition(history: tuple[ChessPosition, ...], moves: tuple[ChessMove, ...]) -> ChessOutcome | ChessViolation | None`；Task 4 在每步后调用，结果区分允许重复、应变着方与可判和局面。

- [ ] 写失败测试：三次重复不自动和、双方允许重复、单方长将、单方长捉及必须变着却再次走回的案例，按 2020 规则给出期望结果。
- [ ] 运行目标测试并确认失败；实现最小历史分析和禁着／终局裁决。
- [ ] 运行 `python3 -m pytest tests/core/test_chess_rules.py -q` 并确认全过；提交此任务文件。

### Task 4: 权威行棋、计时、协商和终局

**Files:** Modify `src/dzmm_bot/core/chess_repository.py`; create `tests/core/test_chess_gameplay.py`.

**Interfaces:** `play_chess(game_id: UUID, platform_id: str, from_xy: tuple[int,int], to_xy: tuple[int,int], expected_version: int, now: datetime) -> ChessGameView`; `chess_action(game_id: UUID, platform_id: str, action: Literal['offer_undo','accept_undo','decline_undo','offer_draw','accept_draw','decline_draw','resign'], now: datetime) -> ChessGameView`; `advance_chess_deadlines(now: datetime) -> int`。所有状态变更锁定同一棋局行并以服务端时钟结算，版本只增不减；终局删除本局聊天正文，只保留棋谱和结果。

- [ ] 写失败测试：红先、错人／错轮／非法着／旧版本不变状态；总时和步时先到者判负；断线／进程重启不重置截止；临界落子与超时只判一次；悔棋／和棋需对方同意、悔棋不返钱钟；认输终局。
- [ ] 运行 `python3 -m pytest tests/core/test_chess_gameplay.py -q`，确认预期失败。
- [ ] 用 Task 2–3 裁判完成事务状态转移、时钟更新和期限扫描；结果持久化并为原群终局出站创建幂等键。
- [ ] 重跑目标测试并确认全过；提交此任务文件。

### Task 5: Gamefy 身份验证与棋局 API

**Files:** Create `src/dzmm_bot/core/chess_api.py`, `src/dzmm_bot/core/chess_auth.py`, `tests/core/test_chess_api.py`; modify `src/dzmm_bot/core/app.py`, `src/dzmm_bot/runtime/settings.py`, `pyproject.toml`, `deploy/env/dzmm.example.env`.

**Interfaces:** `verify_gamefy_token(token: str, expected_game_id: str) -> str` 返回经 JWKS 验签后的 `sub`；公开路由 `GET /api/chess/{id}`、`POST /api/chess/{id}/claim|moves|actions|chat`、`GET /api/chess/{id}/events`。事件路由用带 Bearer 头的 `fetch` SSE，先发快照，后按版本推增量；不把 token 放 URL。增加 `DZMM_CHESS_GAME_ID`、`DZMM_CHESS_GAME_URL`、`DZMM_CHESS_PUBLIC_API_URL`；仅配置齐全时启用创建入口。

- [ ] 写失败测试：RS256 签名、`iss`、`aud`、有效期、JWKS 轮换与未入职检查；观众只能聊天／观战；过期 token 重新认证；SSE 重连先得最新快照；无效 ID、非法 JSON、无效操作不变更状态。
- [ ] 运行 `python3 -m pytest tests/core/test_chess_api.py -q`，确认预期失败。
- [ ] 实现 JWT 校验、CORS 预检、公开 API、聊天正文上限 300 字／每账号每局至少间隔 2 秒、SSE 版本同步；API 仅在公开 HTTPS 反向代理下暴露，不开放内部管理接口。
- [ ] 重跑目标测试并确认全过；提交此任务文件。

### Task 6: Bot 发起指令、消息和期限任务

**Files:** Modify `src/dzmm_bot/core/commands.py`, `src/dzmm_bot/core/repository.py`, `src/dzmm_bot/core/service.py`, `src/dzmm_bot/core/app.py`; create `tests/core/test_chess_commands.py`.

**Interfaces:** `/象棋` 只调用 Task 1 的 `create_chess_game`，构造 Gamefy 入口 URL 的 `gp={"roomId":"<uuid>"}`；使用现有 outbox 回原群。周期任务调用 `advance_chess_deadlines(now)`，发送等席过期／终局通告且每种通告每盘最多一条。

- [ ] 写失败测试：未监听群／私聊／未入职／未配置入口不能创建；成功回复含链接与四位码；同群多盘、同人多盘和现有小游戏并行；未送达链接不能抢座；过期取消、重试只通告一次；随机事件进行时该指令仍可独立触发。
- [ ] 运行 `python3 -m pytest tests/core/test_chess_commands.py -q`，确认预期失败。
- [ ] 注册命令与帮助文案、接入原群 outbox 和现有周期任务；不把象棋加入 `GROUP_GAME_TYPES` 或现有互斥查询。
- [ ] 重跑目标测试并确认全过；提交此任务文件。

### Task 7: Gamefy H5 棋盘与聊天

**Files:** Create `gamefy/chess/publish/index.html`, `gamefy/chess/publish/style.css`, `gamefy/chess/publish/game.js`, `gamefy/chess/publish/config.js`, `gamefy/chess/tests/game.test.mjs`.

**Interfaces:** 启动时通过 `dzmm.getLaunchParams()` 读取、校验 `roomId`，用当前 iframe 的 `#room=<uuid>` 保留本标签上下文；通过 `dzmm.user.info()` 取 token，调用 Task 5 API。重连先取快照，再恢复 SSE；所有动作以服务端回执为准。

- [ ] 写失败测试：无效／缺失 `gp`、双标签分别刷新、过期 token 刷新、棋手／观众权限、落子后旧版本冲突回拉、SSE 断线重连与终局聊天禁用。
- [ ] 运行 `node --test gamefy/chess/tests/game.test.mjs`，确认预期失败。
- [ ] 完成横竖屏可用的棋盘、点击走棋、红黑方向、双时钟、着法、入座框、观战、协商／认输和文字聊天；资源使用相对路径并遵守 Gamefy 文件名规则。
- [ ] 重跑 Node 测试并确认全过；提交此任务文件。

### Task 8: 回归、真实 Gamefy 验收和发布准备

**Files:** Create `tests/core/test_chess_end_to_end.py`, `deploy/nginx/dzmm-chess.conf.example`; modify `docs/DZMM_ACCOUNT_AND_MESSAGE_INTEGRATION_GUIDE.md` 追加象棋入口和环境配置说明。Nginx 示例仅代理 `/api/chess/` 到本机 core，不暴露 `/internal/`。

**Interfaces:** 无新运行接口；真实发布前必须取得已发布 Gamefy 游戏 ID／卡片 URL 和指向 DDZM 公共棋局 API 的 HTTPS 域名，且验证平台 token `sub` 与已入职用户 `platform_id` 一致。

- [ ] 写端到端测试：Bot 指令→出站送达→第二人入座→行棋／聊天／观战→重连→终局；同群多盘与同人多盘不串局。
- [ ] 运行 `python3 -m pytest tests/core/test_chess_*.py tests/deploy/test_chess_migration.py -q` 和 `node --test gamefy/chess/tests/game.test.mjs`，确认全过。
- [ ] 运行 `python3 -m pytest tests/core tests/deploy -q`，确认回归全过；检查 `git diff --check` 与迁移单一 head。
- [ ] 在真实 DZMM 玩家页面验证 Bot 链接携带 `gp`、平台登录、HTTPS/CORS、两位入座和第三人观战；缺少公开 HTTPS 入口或 Gamefy 发布权限时止于本地验收，不宣称已上线。
- [ ] 记录实际验收证据并提交文档；部署须另做生产环境备份、迁移、健康检查和回滚准备。

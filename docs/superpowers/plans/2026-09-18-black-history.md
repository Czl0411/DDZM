# 黑历史册 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 支持群内记录、随机翻出和私聊删除员工黑历史。

**Architecture:** 仓储层原子完成扣币、保存、抽取与删除；命令层只校验消息位置和文案。文字抽取创建图片卡任务，由浏览器 worker 渲染、上传并回写为图片出站；图片抽取直接复用现有图片出站。

**Tech Stack:** Python 3.12、SQLAlchemy/Alembic、FastAPI、Playwright、DZMM Socket、pytest。

**Spec:** `docs/superpowers/specs/2026-09-18-black-history-design.md`

## Global Constraints

- `/q` 仅限群内回复文字或图片；记录者扣 1 摸鱼币，记录归被回复作者。
- `/黑历史` 仅限群内回复目标消息；免费且只能随机抽取。
- `/删除黑历史` 仅限本人私聊；单条删除扣 5 摸鱼币。
- 同一来源消息仅保存一次；不记录私聊、Bot、系统通告、空文字。
- 图片原样使用保存的 URL；文字卡仅复用既有图片上传通道。

---

### Task 1: 持久化模型、迁移与原子仓储操作

**Files:**

- Create: `migrations/versions/20260918_81_black_history.py`
- Modify: `src/dzmm_bot/core/schema.py`
- Modify: `src/dzmm_bot/core/repository.py`
- Test: `tests/core/test_black_history_repository.py`

**Interfaces:** 新增 `BlackHistoryEntryRecord`、`BlackHistoryDeleteDraftRecord`；新增 `record_black_history`、`draw_black_history`、`black_history_delete_page`、`delete_black_history` 四个 `CoreRepository` 方法及各自 frozen result。

- [ ] **Step 1: 写失败测试。** 覆盖首次 `/q` 扣记录者 1 币、同源重复不扣、图片快照、余额不足、随机仅抽归属者、每页 5 条、本人删除扣 5、越权删除无效。
- [ ] **Step 2: 验证失败。** Run `.venv/bin/python -m pytest tests/core/test_black_history_repository.py -q`；Expected: FAIL，因为模型和接口尚不存在。
- [ ] **Step 3: 加模型与迁移。** Entry 使用 `Integer` 自增编号，保存归属/记录用户、群、来源平台消息 ID、`text|image` 快照和时间；唯一约束 `(group_chat_id, source_platform_message_id)`，列表索引 `(subject_user_id, id)`。Delete draft 用 `user_id` 主键、页码、更新时间。迁移 `20260918_81` 以 `20260917_80` 为基线，升级建表、降级删表。
- [ ] **Step 4: 实现仓储事务。** 用 `with_for_update()` 锁记录者；重复来源先返回；余额确认后调用 `_apply_balance_change(user, -1, "black_history_record", now)` 并写 entry。随机查询 `order_by(func.random()).limit(1)`；删除同时限制 entry 编号和归属者，确认余额后扣 5 并删除。
- [ ] **Step 5: 验证并提交。** Run `.venv/bin/python -m pytest tests/core/test_black_history_repository.py -q`，Expected: PASS；提交 `feat: store black history entries`。

### Task 2: 群内记录/抽取与私聊删除命令

**Files:**

- Modify: `src/dzmm_bot/core/commands.py`
- Modify: `src/dzmm_bot/core/service.py`
- Modify: `src/dzmm_bot/core/reply_templates.py`
- Test: `tests/core/test_black_history_commands.py`

**Interfaces:** 添加 `/q`、`/黑历史`、`/删除黑历史` 到命令表；添加私聊删除草稿的 `/下一页`。图片抽取产生文字说明和 `CommandReply(content_type="image")`，文字抽取交给 Task 3。

- [ ] **Step 1: 写失败测试。** 用带 `MessageReference` 的群入站覆盖对他人与自己记录、无回复、私聊 `/q`、Bot/空引用、重复、无记录；覆盖图片抽取的文本加图片、私聊列表/下一页/删除、群内删除提示。
- [ ] **Step 2: 验证失败。** Run `.venv/bin/python -m pytest tests/core/test_black_history_commands.py -q`；Expected: FAIL，因为命令未注册。
- [ ] **Step 3: 最小路由实现。** `/q` 和 `/黑历史` 必须校验 `source_type == "group"`、启用群上下文与有效引用。`/删除黑历史` 只能 direct；`/下一页` 只在存在删除草稿时翻页，不能影响现有私聊向导。固定说明与帮助条目写入 `reply_templates.py`。
- [ ] **Step 4: 验证并提交。** Run `.venv/bin/python -m pytest tests/core/test_black_history_commands.py tests/core/test_group_commands.py tests/core/test_service.py -q`，Expected: PASS；提交 `feat: add black history commands`。

### Task 3: 文字卡异步渲染、上传与图片出站

**Files:**

- Modify: `src/dzmm_bot/core/schema.py`
- Modify: `migrations/versions/20260918_81_black_history.py`
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `src/dzmm_bot/core/api_models.py`
- Modify: `src/dzmm_bot/core/app.py`
- Modify: `src/dzmm_bot/browser/core_client.py`
- Modify: `src/dzmm_bot/browser/worker.py`
- Create: `src/dzmm_bot/browser/black_history_card.py`
- Test: `tests/browser/test_black_history_card.py`
- Test: `tests/browser/test_worker.py`
- Test: `tests/core/test_app.py`

**Interfaces:** 添加 `BlackHistoryCardJobRecord`（entry、触发入站、目标群/聊天室、状态、租约、图片 URL、临时路径、失败摘要）以及 claim/complete/fail 内部 API；添加 `render_black_history_card(display_name, rank_name, text, path) -> None`。

- [ ] **Step 1: 写失败测试。** renderer 测试断言 PNG 文件头并输入 `<script>`；job 测试断言完成上传会 enqueue 一条 `content_type == "image"` 的 outbound；worker 测试断言 claim、上传、complete 和临时文件清理。
- [ ] **Step 2: 验证失败。** Run `.venv/bin/python -m pytest tests/browser/test_black_history_card.py tests/browser/test_worker.py -k black_history -q`；Expected: FAIL，因为 renderer 和任务 API 不存在。
- [ ] **Step 3: 实现任务与 renderer。** 抽中文字时在同一 transaction 建立 `pending` job。renderer 用 `html.escape` 处理姓名、职位、原文，并以固定本地 HTML/CSS 在 Playwright `page.set_content()` 后 `page.screenshot(type="png")`；不加载远程资源。worker 复用 profile image upload 的租约模式，上传 `image/png`，成功回写图片 outbound，失败以原 inbound 关联发送失败提示并清理临时文件。
- [ ] **Step 4: 端到端验证并提交。** Run `.venv/bin/python -m pytest tests/browser/test_black_history_card.py tests/browser/test_worker.py -k black_history tests/core/test_black_history_repository.py tests/core/test_black_history_commands.py tests/core/test_app.py -k black_history -q`，Expected: PASS；提交 `feat: render black history cards`。

### Task 4: 玩家说明与回归验证

**Files:**

- Modify: `docs/command-basics-design.md`
- Test: `tests/core/test_black_history_repository.py`
- Test: `tests/core/test_black_history_commands.py`
- Test: `tests/browser/test_black_history_card.py`

- [ ] **Step 1: 补齐玩家说明。** 写入回复消息 `/q`、回复目标 `/黑历史`、私聊 `/删除黑历史` 与 `/删除黑历史 编号` 的示例，并标明 1/0/5 币、图片原样转发及记录者不公开。
- [ ] **Step 2: 全量相关验证。** Run `.venv/bin/python -m pytest tests/core/test_black_history_repository.py tests/core/test_black_history_commands.py tests/browser/test_black_history_card.py tests/browser/test_worker.py tests/core/test_group_commands.py tests/core/test_service.py tests/core/test_app.py -q && .venv/bin/python -m compileall -q src/dzmm_bot && git diff --check`；Expected: PASS，无格式错误。
- [ ] **Step 3: 提交说明。** 提交 `docs: explain black history commands`。

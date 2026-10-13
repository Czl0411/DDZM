# 自定义固定回复指令 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 管理员在指令库配置群聊专用自定义指令，Bot 按配置发送一条文本、图片、群聊邀请卡或小说卡。

**Architecture:** 扩展现有 `command_definitions`，用独立图片上传任务取得平台 URL；Core 校验并持久化配置，现有群消息路由在内置指令未命中时读取自定义回复。继续使用现有出站队列和 Browser Worker；后台只做鉴权、上传文件校验和表单展示。

**Tech Stack:** Python 3.12、SQLAlchemy/Alembic、FastAPI、pytest、原生 JavaScript。

**Spec:** `docs/superpowers/specs/2026-10-12-custom-fixed-reply-commands-design.md`

## Global Constraints

- 仅已监听群聊生效，任意群成员可用；私聊不触发，活动和游戏的现有指令限制不变。
- 指令名以 `/` 开头、无空白、最长 32 字符；整条消息去首尾空白后精确匹配，不接受参数；不得占用内置名称、别名或特殊格式。
- 每条指令只发一条固定回复；文本最多 2000 字符；图片仅 JPEG/PNG/WebP 且最多 10 MB。
- 分享群聊仅接受当前站点 `/invite/<邀请码>`，小说仅接受当前站点 `/novel/<UUID>`；出站分别为 `group_invite`、`novel` 分享卡。
- 图片上传或表单取消失败时，当前生效配置不能被替换；部署、生产数据变更、按群配置和私聊均不在范围内。

## Review Focus

- `/暗网`、`/me`、`/第3场` 等别名/特殊格式：保存同名自定义指令必须拒绝（Task 2）。
- 错误域名、`/chat?c=...`、空邀请码、非法小说 UUID：应返回 422 而不写入配置（Task 1、2）。
- 图片任务完成前、失败后，或编辑器取消：旧图片回复仍可发送，未保存的新图不生效（Task 1、3、5）。
- 相同指令在两个已监听群、私聊及未监听群：只在前两者各回复一条（Task 4）。
- 公演/随机事件正在限制指令：自定义指令不能绕过现有拦截（Task 4）。

---

### Task 1: 数据表与仓储

**Files:** Modify `src/dzmm_bot/core/schema.py`, `src/dzmm_bot/core/repository.py`; create `migrations/versions/20261012_104_custom_commands.py`; test `tests/core/test_repository.py`, `tests/deploy/test_custom_commands_migration.py`.

**Interfaces:** `CoreRepository.create_custom_command(command: str, description: str, reply_type: str, content: str | None, upload_task_id: UUID | None, enabled: bool) -> CommandDefinitionRecord`; `update_custom_command(old_command: str, command: str, description: str, reply_type: str, content: str | None, upload_task_id: UUID | None, enabled: bool) -> CommandDefinitionRecord`; `delete_custom_command(command: str) -> bool`; `get_enabled_custom_command(command: str) -> CommandDefinitionRecord | None`. 图片任务仓储提供 `create_custom_command_image_upload(temp_path: str, original_filename: str, mime_type: str, now: datetime) -> CustomCommandImageUploadRecord`、`claim_custom_command_image_upload(worker_id: str, now: datetime, lease_seconds: int) -> CustomCommandImageUploadRecord | None`、`complete_custom_command_image_upload(task_id: UUID, worker_id: str, lease_token: UUID, result_url: str, now: datetime) -> bool`、`fail_custom_command_image_upload(task_id: UUID, worker_id: str, lease_token: UUID, failure_summary: str, now: datetime) -> bool`、`get_custom_command_image_upload(task_id: UUID) -> CustomCommandImageUploadRecord | None`；租约和临时文件清理遵循现有档案图片任务。

- [ ] **Step 1: 写失败测试。** 新增、改名、启停、删除仅影响 `is_custom` 行；内置行不可删除/改写；文本长度、邀请链接、小说 UUID 无效被拒；图片保存只接受已完成任务，上传失败不替换旧回复；迁移升级后内置行保持可用。
- [ ] **Step 2: 验证失败。** `pytest -q tests/core/test_repository.py -k custom_command tests/deploy/test_custom_commands_migration.py`；预期因新表/方法缺失失败。
- [ ] **Step 3: 最小实现。** 为 `command_definitions` 加 `is_custom`、`reply_type`、`reply_value`；新增独立上传任务表。复用现有 `company_story_novel_resource_id` 验证小说链接；邀请链接用 `urlsplit` 校验当前站点及 `/invite/<code>`。仓储事务内校验并写入，内置行保持原义；名称保留校验由 Task 2 的 Core API 传入已知内置名/别名集合。
- [ ] **Step 4: 验证通过并提交。** 运行 Step 2 命令及 `git diff --check`；提交 schema、migration、repository 与测试。

### Task 2: Core 与 Admin 的配置接口

**Files:** Modify `src/dzmm_bot/core/api_models.py`, `src/dzmm_bot/core/app.py`, `src/dzmm_bot/core/commands.py`, `src/dzmm_bot/admin/core_client.py`, `src/dzmm_bot/admin/app.py`; test `tests/core/test_app.py`, `tests/admin/test_app.py`.

**Interfaces:** Core `POST /internal/game/custom-commands`, `PUT /internal/game/custom-commands/{command}`, `DELETE /internal/game/custom-commands/{command}`；复用 `GET/PATCH /internal/game/commands` 列表和启停。Admin 对应 `/api/game/custom-commands` 路由，配置写操作调用现有 `versioned_configuration_response`。请求字段为 `command, description, enabled, reply_type, content, upload_task_id`；响应含 `is_custom, reply_type, reply_value`。

- [ ] **Step 1: 写失败测试。** Core 鉴权、CRUD、422（`/暗网`、`/me`、`/第3场` 及错误 URL）、404（未知/内置删除）；Admin 配置版本、幂等、编辑后重读和内置模板不变。
- [ ] **Step 2: 验证失败。** `pytest -q tests/core/test_app.py tests/admin/test_app.py -k custom_command`；预期新接口不存在。
- [ ] **Step 3: 最小实现。** `commands.py` 暴露 `is_reserved_command_name(name: str) -> bool`，覆盖 `_COMMANDS`、别名及正则特殊格式；Core API 调用仓储；Admin 仅转发并使用既有版本/幂等包装。列表序列化区分内置与自定义，不给自定义行生成模板。
- [ ] **Step 4: 验证通过并提交。** 运行 Step 2 命令及 `git diff --check`；提交接口与测试。

### Task 3: 独立图片上传链路

**Files:** Modify `src/dzmm_bot/core/api_models.py`, `src/dzmm_bot/core/app.py`, `src/dzmm_bot/admin/core_client.py`, `src/dzmm_bot/admin/app.py`, `src/dzmm_bot/browser/core_client.py`, `src/dzmm_bot/browser/worker.py`; test `tests/core/test_app.py`, `tests/admin/test_app.py`, `tests/browser/test_core_client.py`, `tests/browser/test_worker.py`.

**Interfaces:** Admin `POST /api/game/custom-command-images` 接文件、`GET /api/game/custom-command-images/{task_id}` 查状态；Core 内部创建/查询/领取/完成/失败/清理任务接口沿用档案图片的鉴权和租约字段；Worker 的 `_process_custom_command_image_upload(gateway: ChatGateway) -> None` 调用 `gateway.upload_image(path, mime_type)`。

- [ ] **Step 1: 写失败测试。** 合法 PNG/JPEG/WebP 返回任务并可取得 URL；>10 MB、MIME 与文件头不符返回 422 且删除临时文件；上传失败保留旧命令；完成/失败回报采用 lease token 防止旧 worker 覆盖；完成任务文件清理。
- [ ] **Step 2: 验证失败。** `pytest -q tests/core/test_app.py tests/admin/test_app.py tests/browser/test_core_client.py tests/browser/test_worker.py -k custom_command_image`；预期新上传接口缺失。
- [ ] **Step 3: 最小实现。** 复制现有档案图片上传的鉴权、文件验证、异步领取/回报/清理约定，但存入 Task 1 的独立表；不创建员工档案记录，也不在上传完成时直接修改指令。
- [ ] **Step 4: 验证通过并提交。** 运行 Step 2 命令及 `git diff --check`；提交链路与测试。

### Task 4: 群消息匹配与四种出站

**Files:** Modify `src/dzmm_bot/core/commands.py`, `src/dzmm_bot/core/service.py`, `src/dzmm_bot/core/api_models.py`, `src/dzmm_bot/browser/worker.py`; test `tests/core/test_group_commands.py`, `tests/core/test_service.py`, `tests/browser/test_worker.py`.

**Interfaces:** `GroupCommandHandler.handle` 内置分支之后读取 `get_enabled_custom_command(content)`；返回 `CommandReply` 的 `content_type` 为 `text|image|group_invite|novel`。`OutboundClaimResponse.content_type` 加 `group_invite`；Worker 将 `group_invite` 传给 `gateway.send_share` / `send_share_to`。

- [ ] **Step 1: 写失败测试。** 四种回复各入队一条、群邀请只发送邀请码；已监听两群可用，私聊/未监听/停用/删除/附加参数无回复；活动期间仍被拦截；Worker 不把分享卡当文本。
- [ ] **Step 2: 验证失败。** `pytest -q tests/core/test_group_commands.py tests/core/test_service.py tests/browser/test_worker.py -k custom_command`；预期未产生自定义回复。
- [ ] **Step 3: 最小实现。** 在现有活动闸门之后匹配自定义指令，沿用 `_enqueue_replies`；复用现有图片与小说处理，仅给 Worker 分享分支增加 `group_invite`，不改限速/重试逻辑。
- [ ] **Step 4: 验证通过并提交。** 运行 Step 2 命令及 `git diff --check`；提交路由与测试。

### Task 5: 指令库编辑界面及回归

**Files:** Modify `src/dzmm_bot/admin/templates/index.html`, `src/dzmm_bot/admin/static/admin.js`, `src/dzmm_bot/admin/static/admin.css`（仅确有布局需求时）； test `tests/admin/test_app.py`.

**Interfaces:** “新增自定义指令”按钮和编辑弹窗调用 Task 2 的 CRUD；图片选择调用 Task 3 的上传/状态接口；现有内置行继续只显示模板配置/启停。

- [ ] **Step 1: 写失败测试。** 页面含新增入口、四种类型选项和文件输入；JS 使用自定义 CRUD/上传状态接口；内置行无删除入口，自定义行有编辑/删除；保存后列表能重读并显示类型/摘要。
- [ ] **Step 2: 验证失败。** `pytest -q tests/admin/test_app.py -k custom_command_ui`；预期新 UI 元素缺失。
- [ ] **Step 3: 最小实现。** 表单按类型切换字段，上传完成前禁用图片保存；失败/取消不发送保存请求；列表搜索、分页沿用现有实现，字符串经 `escapeHtml` 渲染。
- [ ] **Step 4: 验证通过。** 运行 Step 2 命令、`node --check src/dzmm_bot/admin/static/admin.js`、`git diff --check`，再运行 `pytest -q tests/core tests/admin tests/browser` 和迁移专项测试；记录既有失败与新增失败区别。
- [ ] **Step 5: 提交。** 仅提交 UI、相关测试与本任务直接产生的样式改动。

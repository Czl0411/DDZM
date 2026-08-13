# 档案形象实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 增加回复图片设置档案形象、`/我的档案` 顺序发送文字和图片，以及后台本地上传、替换、清除档案形象的完整可靠链路。

**Architecture:** 在现有入站、出站、个人档案和 Worker 租约模型上做兼容扩展。引用图片作为结构化入站元数据进入核心；图片作为新出站内容类型复用现有顺序、租约和重试；后台文件通过独立持久化上传任务交给 Browser Worker 上传，再用档案版本防止旧任务覆盖新状态。

**Tech Stack:** Python 3.12、FastAPI、SQLAlchemy 2、Alembic、PostgreSQL/SQLite 测试、python-socketio、Playwright、原生 HTML/CSS/JavaScript、pytest。

## Global Constraints

- 玩家必须回复图片并发送完整指令 `/编辑档案形象`。
- 玩家必须已入职且已填写文字个人档案。
- 成功设置形象共用现有编辑费用并消耗 1 点公共人力，所有写入原子完成。
- `/我的档案` 先发文字，存在形象时再单独发图片；没有形象时不发第二条。
- 后台允许 JPEG、PNG、WebP，最大 10 MB；管理员操作不扣玩家资源。
- 后台清空文字档案必须同步清除形象。
- 图片不进入 AI 记忆或 AI 对话上下文。
- 不自动部署；完成后等待用户确认。

---

### Task 1: 入站图片引用契约

**Files:**
- Modify: `src/dzmm_bot/runtime/contracts.py`
- Modify: `src/dzmm_bot/browser/aikda_socket.py`
- Modify: `src/dzmm_bot/browser/core_client.py`
- Modify: `src/dzmm_bot/core/api_models.py`
- Modify: `src/dzmm_bot/core/app.py`
- Test: `tests/runtime/test_contracts.py`
- Test: `tests/browser/test_aikda_socket.py`
- Test: `tests/browser/test_core_client.py`
- Test: `tests/core/test_app.py`

**Interfaces:**
- Produces: `MessageReference(message_id, sender_platform_id, content_type, image_url, alt, width, height, blurhash)`.
- Produces: `InboundMessage.reference: MessageReference | None` with a backward-compatible default.
- Consumes: platform `content.reference` with `id`, `sentBy`, and nested `content`.

- [ ] Write tests proving a referenced image survives Socket parsing and the internal HTTP boundary while ordinary text remains unchanged.
- [ ] Run the focused tests and verify failure is caused by the absent reference contract.
- [ ] Add the minimal immutable reference dataclass, strict parser, request model fields, and serialization.
- [ ] Run the focused tests until green and commit only Task 1 files.

### Task 2: 档案形象数据与玩家事务

**Files:**
- Create: `migrations/versions/20260813_41_profile_images.py`
- Modify: `src/dzmm_bot/core/schema.py`
- Modify: `src/dzmm_bot/core/repository.py`
- Test: `tests/deploy/test_profile_image_migration.py`
- Test: `tests/core/test_repository.py`

**Interfaces:**
- Produces: `UserRecord.profile_image_url: str | None` and `UserRecord.profile_version: int`.
- Produces: `ProfileImageEditResult(status: str, image_url: str | None = None, cost: int = 0)`.
- Produces: `CoreRepository.edit_own_profile_image(platform_id: str, image_url: str) -> ProfileImageEditResult`.
- Produces: `CoreRepository.get_personal_profile_details(platform_id: str) -> tuple[str, str | None] | None`.
- Produces: administrator profile writes that clear image when text is cleared and increment `profile_version` on image-affecting changes.

- [ ] Write migration and repository tests for historical defaults, prerequisite text, atomic fee/labor deduction, unchanged image, insufficient resources, and admin clear semantics.
- [ ] Run focused tests and verify expected failures.
- [ ] Add the migration, columns, result type, transactional player method, detailed getter, and versioned admin writes.
- [ ] Run migration upgrade/downgrade and repository tests until green; commit Task 2 files.

### Task 3: 玩家命令与回复模板

**Files:**
- Modify: `src/dzmm_bot/core/commands.py`
- Modify: `src/dzmm_bot/core/reply_templates.py`
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `src/dzmm_bot/core/service.py`
- Test: `tests/core/test_group_commands.py`
- Test: `tests/core/test_repository.py`
- Test: `tests/core/test_service.py`

**Interfaces:**
- Consumes: `InboundMessage.reference` and `CoreRepository.edit_own_profile_image`.
- Produces: command `/编辑档案形象` with scenarios `usage`, `not_joined`, `profile_required`, `unchanged`, `insufficient_balance`, `insufficient_labor`, `updated`.
- Produces: a typed command result allowing `/我的档案` to enqueue one text reply plus an optional image reply without parsing template text.

- [ ] Write command tests for every scenario and for `/我的档案` with and without an image.
- [ ] Run the tests and verify failures show the missing command and secondary outbound.
- [ ] Add command registration, help metadata, templates, reference validation, repository call, and secondary image enqueue hook.
- [ ] Verify focused command/service tests and commit Task 3 files.

### Task 4: 图片出站队列与平台发送

**Files:**
- Modify: `migrations/versions/20260813_41_profile_images.py`
- Modify: `src/dzmm_bot/runtime/contracts.py`
- Modify: `src/dzmm_bot/core/schema.py`
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `src/dzmm_bot/core/api_models.py`
- Modify: `src/dzmm_bot/core/app.py`
- Modify: `src/dzmm_bot/browser/core_client.py`
- Modify: `src/dzmm_bot/browser/session.py`
- Modify: `src/dzmm_bot/browser/aikda_socket.py`
- Modify: `src/dzmm_bot/browser/worker.py`
- Test: `tests/core/test_repository.py`
- Test: `tests/core/test_app.py`
- Test: `tests/browser/test_core_client.py`
- Test: `tests/browser/test_aikda_socket.py`
- Test: `tests/browser/test_worker.py`

**Interfaces:**
- Produces: outbound fields `content_type: Literal["text", "image"]`, `image_url: str | None`, `image_alt: str | None`.
- Produces: `CoreRepository.enqueue_image_outbound(inbound_message_id, image_url, reply_index, image_alt="image")`.
- Produces: `ChatGateway.send_image(...)` and `send_image_to(...)`.
- Extends: `OutboundClaim` with content type and image attributes.

- [ ] Write tests for queue ordering, claim serialization, Socket image payload, Worker routing, confirmation, retry, and existing text compatibility.
- [ ] Run focused tests and verify expected failures.
- [ ] Add the minimal database/API/client/gateway/Worker extensions and make `/我的档案` use the image queue method.
- [ ] Run all focused tests and commit Task 4 files.

### Task 5: 持久化后台图片上传任务

**Files:**
- Modify: `migrations/versions/20260813_41_profile_images.py`
- Modify: `src/dzmm_bot/core/schema.py`
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `src/dzmm_bot/core/api_models.py`
- Modify: `src/dzmm_bot/core/app.py`
- Modify: `src/dzmm_bot/browser/core_client.py`
- Modify: `src/dzmm_bot/browser/session.py`
- Modify: `src/dzmm_bot/browser/worker.py`
- Test: `tests/core/test_repository.py`
- Test: `tests/core/test_app.py`
- Test: `tests/browser/test_core_client.py`
- Test: `tests/browser/test_worker.py`

**Interfaces:**
- Produces: `ProfileImageUploadRecord` with employee, file metadata, expected profile version, status, lease, result URL, failure summary, timestamps.
- Produces: repository create/claim/complete/fail methods using existing lease conventions.
- Produces: internal create/status/claim/complete/fail endpoints and `ProfileImageUploadClaim` client type.
- Produces: `ChatGateway.upload_image(path: Path, mime_type: str) -> dict` backed by `chatroom.uploadImage`.

- [ ] Write repository/API tests for task creation, leasing, expired lease recovery, completion, failure, superseded version, and temporary-file cleanup eligibility.
- [ ] Write Worker tests for successful upload, upload failure, and completion reporting.
- [ ] Run focused tests and verify expected failures.
- [ ] Add schema, migration, repository, endpoints, client contract, gateway upload call, and Worker polling.
- [ ] Run focused tests and commit Task 5 files.

### Task 6: 后台上传、预览、替换与清除界面

**Files:**
- Modify: `src/dzmm_bot/admin/core_client.py`
- Modify: `src/dzmm_bot/admin/app.py`
- Modify: `src/dzmm_bot/admin/templates/index.html`
- Modify: `src/dzmm_bot/admin/static/admin.js`
- Modify: `src/dzmm_bot/admin/static/admin.css`
- Test: `tests/admin/test_app.py`
- Test: `tests/core/test_app.py`

**Interfaces:**
- Produces: employee profile response fields `profile_image_url`, `profile_version`, and latest upload status.
- Produces: multipart upload endpoint, clear-image endpoint, and polling status endpoint.
- Consumes: JPEG/PNG/WebP files up to 10 MB and the Task 5 core upload API.

- [ ] Write admin tests for rendering controls, valid multipart upload, invalid MIME, oversized file, clear action, clearing text plus image, and status response.
- [ ] Run focused tests and verify expected failures.
- [ ] Add core client methods, server-side validation and controlled temp-file storage, modal preview/file/status controls, JavaScript submission/polling, and minimal matching styles.
- [ ] Run focused admin/core tests and commit Task 6 files.

### Task 7: 回归、迁移和规格验收

**Files:**
- Modify only files required to fix failures introduced by Tasks 1–6.
- Verify: `docs/superpowers/specs/2026-08-13-profile-image-design.md`

**Interfaces:**
- Consumes all preceding task interfaces.
- Produces no new behavior.

- [ ] Run formatting/static checks configured by the repository and `git diff --check`.
- [ ] Run the complete pytest suite and record pass/skip counts.
- [ ] Run a fresh migration upgrade to head and downgrade/upgrade coverage for revision 41.
- [ ] Compare every design acceptance item against tests and inspect `git diff --stat` plus `git status --short`.
- [ ] Fix only feature-related regressions with a failing test first, rerun full verification, and commit final integration fixes if needed.
- [ ] Report implementation and verification results without deploying.

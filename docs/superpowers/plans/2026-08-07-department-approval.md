# 部门申请审批 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增部门查询与独立的部门申请审批流程，使部门加入和切换仅在合资格目标部门成员同意后生效。

**Architecture:** 核心仓储新增部门申请与审批记录，在一个事务内校验目标部门、职级和状态。群指令使用独立编号；管理端仅展示分页审批记录；现有随机事件门禁仍是这些命令的默认拦截层。

**Tech Stack:** Python 3、SQLAlchemy、Alembic、FastAPI、原生 HTML/JavaScript、pytest。

## Global Constraints

- 所有申请有效期与时间展示使用 `Asia/Shanghai`；有效期固定 24 小时。
- 同一员工仅一条待审部门申请；编号独立于晋升申请、递增且不复用。
- 仅目标部门中职级严格高于申请人的员工可以审批；申请人不能审批自己。
- 同意才实际变更部门；拒绝、失效、无权限或单项批量失败均不变更部门。
- 新命令默认受随机事件门禁限制，但可在既有放行配置中勾选。
- 迁移只插入缺失的命令/模板，绝不覆盖管理员已保存的回复。

---

### Task 1: 部门申请持久化

**Files:** `src/dzmm_bot/core/schema.py`, `src/dzmm_bot/core/repository.py`, `migrations/versions/20260807_24_department_approvals.py`, `tests/core/test_repository.py`

**Interfaces:** 新增 `DepartmentRequestRecord`、`DepartmentApprovalRecord`，以及 `request_department_change`、`list_approvable_department_requests`、`decide_department_requests`、`list_department_requests_page`。

- [ ] 写一个失败测试：未分配员工申请“核心技术部”，该部门内 LV2 员工同意后，申请人才变更部门。
- [ ] 运行 `.venv/bin/pytest -q tests/core/test_repository.py -k department_application`，确认因为接口不存在而失败。
- [ ] 创建带独立数字编号的申请表（申请人、来源/目标部门、状态、申请/失效/处理时间）和每申请一条的审批表；为申请人创建 pending 部分唯一索引。
- [ ] 在事务中锁定申请、申请人和审批人；同意前检查待审状态、24 小时、审批人处于目标部门、审批人职级更高且非本人。只有同意才写 `department_id`。
- [ ] 新增 `20260807_24` 迁移，仅创建新表/索引，不改现有部门归属。
- [ ] 运行 `.venv/bin/pytest -q tests/core/test_repository.py`，覆盖非目标部门、同级、本人、过期、拒绝和批量独立性。
- [ ] 提交：`feat: persist department approval requests`。

### Task 2: 群内命令与可编辑回复

**Files:** `src/dzmm_bot/core/commands.py`, `src/dzmm_bot/core/repository.py`, `src/dzmm_bot/core/reply_templates.py`, `tests/core/test_group_commands.py`

**Interfaces:** 新增 `/部门`、`/部门申请列表`、`/同意部门`、`/全部同意部门`、`/拒绝部门`、`/全部拒绝部门`；`/加入部门` 与 `/切换部门` 改为创建申请。

- [ ] 写失败测试：`/加入部门 核心技术部` 只回复已提交，`/同意部门 1` 后才变更部门；`/部门` 只展示启用部门与说明。
- [ ] 运行 `.venv/bin/pytest -q tests/core/test_group_commands.py -k department_commands_apply`，确认在旧即时变更行为下失败。
- [ ] 注册全部指令、默认定义和模板。模板覆盖申请已提交、已有待审、参数错误、无可审批申请、同意、拒绝和不可处理申请。
- [ ] 保留原有约束：`/加入部门` 仅默认部门员工可申请；`/切换部门` 仅非默认部门员工可申请。
- [ ] 将全部新部门指令加入随机事件可配置命令集合，不修改默认放行清单。
- [ ] 运行 `.venv/bin/pytest -q tests/core/test_group_commands.py`。
- [ ] 提交：`feat: add department approval commands`。

### Task 3: 核心/管理端审批记录

**Files:** `src/dzmm_bot/core/api_models.py`, `src/dzmm_bot/core/app.py`, `src/dzmm_bot/admin/core_client.py`, `src/dzmm_bot/admin/app.py`, `src/dzmm_bot/admin/templates/index.html`, `src/dzmm_bot/admin/static/admin.js`, `tests/core/test_app.py`, `tests/admin/test_app.py`

**Interfaces:** `GET /internal/game/department-requests` 与管理端代理 `GET /api/game/department-requests`，支持 state/page/page_size。组织页面新增独立分页的只读申请记录列表。

- [ ] 写失败 API/UI 测试：端点返回目标部门为“核心技术部”的分页记录，HTML 包含 `department-request-list`。
- [ ] 运行 `.venv/bin/pytest -q tests/core/test_app.py tests/admin/test_app.py -k department_request`，确认端点和页面元素不存在。
- [ ] 返回并展示编号、申请人、来源/目标部门、状态、申请/失效/处理时间、审批人和处理决定；复用现有 `renderPagination`。审批仍只由群指令执行。
- [ ] 运行 `.venv/bin/pytest -q tests/core/test_app.py tests/admin/test_app.py`。
- [ ] 提交：`feat: show department approval records in admin`。

### Task 4: 全局规则、回归与部署

**Files:** `rule.md`, `tests/deploy/test_artifacts.py`

- [ ] 将规则第 10 节的即时部门变更替换为申请、目标部门高级别成员审批和独立命令规则。
- [ ] 添加迁移构件测试，确认 `20260807_24` 的 revision 链和新申请/审批表定义。
- [ ] 执行 `node --check src/dzmm_bot/admin/static/admin.js && .venv/bin/pytest -q && .venv/bin/alembic heads && git diff --check`。
- [ ] 提交规则与构件测试，部署已提交归档；验证新的 Alembic head、三项 active 服务、健康检查和认证后的部门申请 API。

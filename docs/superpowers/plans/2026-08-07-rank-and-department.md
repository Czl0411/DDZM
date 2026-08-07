# 职级、部门与晋升审批 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为员工增加可配置的职位与部门资料，并实现 24 小时有效、可批量同意或拒绝的付费晋升审批流程。

**Architecture:** 核心服务持有职位、部门与申请的唯一状态，并在数据库事务内结算晋升。核心 API 只暴露受核心令牌保护的游戏数据；管理端代理普通配置操作，并仅让超级管理员调用核心董事会授予/撤销接口。群内命令通过既有 `GroupCommandHandler` 与可编辑回复模板进入仓储层。

**Tech Stack:** Python 3、FastAPI、SQLAlchemy、Alembic、PostgreSQL/SQLite、原生 HTML/CSS/JavaScript、pytest。

## Global Constraints

- 全部时间、有效期和展示都使用 `Asia/Shanghai`。
- 职级和部门独立存储；新员工默认 LV1“实习生”和“未分配部门”。
- 晋升申请只允许下一档普通职位；创建时不扣币，同意时重新校验余额后扣币。
- 审批人当前职位必须严格高于申请人的当前职位，且不能审批自己。
- 核心董事会不可通过群命令申请；仅超级管理员可以授予/撤销，撤销后回落 LV10，不退款、不改部门。
- 后台管理员账号与员工职级无关；LV8+ 的“群内管理资格”只展示，不新增群管理能力。
- 新增群命令默认受随机事件门禁限制；它们必须被加入可配置放行命令集合，但默认不放行。
- 写操作保持既有幂等键、配置版本、加载态、防重复提交、局部刷新和标准消息提示约定。

---

## File Structure

- `src/dzmm_bot/core/schema.py`：新增职位、部门、晋升申请、审批审计 ORM 表，并给 `UserRecord` 增加外键。
- `migrations/versions/20260807_22_rank_and_department.py`：创建/回填数据库结构及默认职位、部门。
- `src/dzmm_bot/core/repository.py`：职位/部门查询与配置、部门切换、申请创建/审批/核心董事会变更的事务逻辑。
- `src/dzmm_bot/core/reply_templates.py`：新增职位、部门和审批命令的默认回复及变量白名单。
- `src/dzmm_bot/core/commands.py`：解析并调用新群命令。
- `src/dzmm_bot/core/api_models.py`、`src/dzmm_bot/core/app.py`：核心管理 API 与分页响应。
- `src/dzmm_bot/admin/core_client.py`、`src/dzmm_bot/admin/app.py`：管理端到核心的代理、版本化配置和超级管理员边界。
- `src/dzmm_bot/admin/templates/index.html`、`src/dzmm_bot/admin/static/admin.js`、`src/dzmm_bot/admin/static/admin.css`：职位与部门管理视图、分页、编辑弹窗及员工资料展示。
- `tests/core/test_group_commands.py`、`tests/core/test_repository.py`、`tests/core/test_app.py`、`tests/admin/test_app.py`：行为、事务、API、权限和页面结构测试。

### Task 1: 持久化职位、部门和晋升申请

**Files:**
- Modify: `src/dzmm_bot/core/schema.py`
- Create: `migrations/versions/20260807_22_rank_and_department.py`
- Modify: `src/dzmm_bot/core/repository.py`
- Test: `tests/core/test_repository.py`

**Interfaces:**
- Produces `RankRecord`、`DepartmentRecord`、`PromotionRequestRecord`、`PromotionApprovalRecord` 与扩展后的 `UserRecord.rank_id` / `department_id`。
- Produces仓储方法 `get_user_profile(platform_id)`, `list_ranks()`, `list_departments()`, `join_department(...)`, `switch_department(...)`, `request_promotion(...)`, `list_approvable_promotions(...)`, `decide_promotions(...)`, `set_board_membership(...)`。
- Consumes现有 `_apply_balance_change(employee, amount, reason, occurred_at)` 记账机制。

- [ ] **Step 1: 写出仓储层失败测试**

```python
def test_new_employee_has_default_rank_and_department():
    employee, _ = repository.create_user("u1", "小明", now, 0)
    profile = repository.get_user_profile("u1")
    assert profile.rank.name == "实习生"
    assert profile.department.name == "未分配部门"


def test_promotion_approval_charges_once_and_records_audit():
    applicant = _create_employee("u1", "小明", balance=80)
    approver = _create_employee("u2", "小红", rank_order=2)
    request = repository.request_promotion(applicant.platform_id, now)
    result = repository.decide_promotions(approver.platform_id, [request.number], "approved", now)
    assert result[0].status == "approved"
    assert repository.find_user("u1").balance == 0
    assert repository.get_user_profile("u1").rank.order == 2
    assert repository.list_promotion_audits(request.id)[0].decision == "approved"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/core/test_repository.py -k 'default_rank or promotion_approval' -v`

Expected: FAIL，因为新增仓储接口和模型尚不存在。

- [ ] **Step 3: 以最小模型与事务实现通过测试**

```python
class PromotionRequestRecord(Base):
    __tablename__ = "promotion_requests"
    number: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    applicant_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    source_rank_id: Mapped[UUID] = mapped_column(ForeignKey("ranks.id"), nullable=False)
    target_rank_id: Mapped[UUID] = mapped_column(ForeignKey("ranks.id"), nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    expires_at: Mapped[datetime] = mapped_column(BeijingDateTime, nullable=False)
```

在一个 `repository.transaction()` 内锁定申请和员工记录，校验状态、24 小时有效期、审批人职级与余额；同意时依次扣币、更新职位、关闭申请并插入审计记录。拒绝只关闭申请并写审计。`/全部` 使用相同逐项方法，单项失败不回滚其他项。

- [ ] **Step 4: 编写 Alembic 迁移与回填**

迁移创建四张表/关系：`ranks`、`departments`、`promotion_requests`、`promotion_approvals`；为 `users` 新增可空外键后回填默认“实习生”和“未分配部门”，最后设为非空。插入规格中 11 个职位和 9 个部门；为待审申请建立“每员工一条 pending”部分唯一索引，按 PostgreSQL 与 SQLite 分别定义条件索引。

- [ ] **Step 5: 运行仓储测试**

Run: `pytest tests/core/test_repository.py -v`

Expected: PASS，覆盖默认回填、部门删除保护、24 小时过期、同意扣费、余额不足保持待审、拒绝无扣费、重复审批和核心董事会回落。

- [ ] **Step 6: 提交**

```bash
git add src/dzmm_bot/core/schema.py src/dzmm_bot/core/repository.py migrations/versions/20260807_22_rank_and_department.py tests/core/test_repository.py
git commit -m "feat: persist employee ranks and promotion requests"
```

### Task 2: 群内职位、部门与审批命令

**Files:**
- Modify: `src/dzmm_bot/core/commands.py`
- Modify: `src/dzmm_bot/core/reply_templates.py`
- Modify: `src/dzmm_bot/core/repository.py`
- Test: `tests/core/test_group_commands.py`

**Interfaces:**
- Consumes Task 1 的 `get_user_profile`, `join_department`, `switch_department`, `request_promotion`, `list_approvable_promotions`, `decide_promotions`。
- Produces命令 `/职位`、`/加入部门`、`/切换部门`、`/晋升`、`/晋升申请列表`、`/同意`、`/全部同意`、`/拒绝`、`/全部拒绝`。
- Produces与每个命令/场景对应的可编辑 `TemplateDefinition`，并将命令加到 `_COMMANDS` 和仓储默认指令定义。

- [ ] **Step 1: 写出命令层失败测试**

```python
def test_promotion_commands_show_only_eligible_requests_and_support_bulk_decisions():
    _receive(service, "join-1", "u1", "/入职 小明", now)
    _receive(service, "join-2", "u2", "/入职 小红", now)
    repository.promote_for_test("u2", rank_order=2)
    _receive(service, "apply", "u1", "/晋升", now)
    _receive(service, "list", "u2", "/晋升申请列表", now)
    assert "1" in _latest_reply(factory)
    _receive(service, "approve", "u2", "/同意 1", now)
    assert "晋升成功" in _latest_reply(factory)


def test_department_join_and_switch_and_me_reply_show_profile():
    _receive(service, "join", "u1", "/入职 小明", now)
    _receive(service, "department", "u1", "/加入部门 核心技术部", now)
    _receive(service, "me", "u1", "/我", now)
    assert "实习生" in _latest_reply(factory)
    assert "核心技术部" in _latest_reply(factory)
```

- [ ] **Step 2: 运行命令测试确认失败**

Run: `pytest tests/core/test_group_commands.py -k 'promotion or department or profile' -v`

Expected: FAIL，因为命令尚未注册。

- [ ] **Step 3: 实现解析、业务结果映射和模板**

```python
if command == "/晋升申请列表":
    return self._promotion_list(message.sender_platform_id, received_at)
if command in {"/同意", "/拒绝"}:
    return self._promotion_decision(message.sender_platform_id, command, content, received_at)
if command in {"/全部同意", "/全部拒绝"}:
    return self._promotion_decision(message.sender_platform_id, command, command, received_at)
```

为 `/我` 默认模板加入 `{职位}`、`{部门}`；为 `/职位`、部门和审批命令分别定义成功、未入职、参数错误、无权限、余额不足、无可处理申请等场景。模板变量只提供业务实际可填的值，例如 `{申请列表}`、`{职位列表}`、`{部门}`、`{目标职位}`、`{晋升价格}`、`{剩余有效时间}`。

- [ ] **Step 4: 将新命令纳入随机事件可配置门禁**

在 `_RANDOM_EVENT_CONFIGURABLE_COMMANDS` 和 `CoreService._allows_random_event_command()` 的规范化映射中加入新命令。默认报名中/进行中允许清单保持不变，确保新命令默认被“当前有随机事件发生，监事不会处理。”拦截，而管理员可明确勾选放行。

- [ ] **Step 5: 运行命令测试**

Run: `pytest tests/core/test_group_commands.py -v`

Expected: PASS，覆盖职位展示、默认部门、加入/切换、申请、24 小时显示、编号批量同意/拒绝、余额不足与随机事件门禁。

- [ ] **Step 6: 提交**

```bash
git add src/dzmm_bot/core/commands.py src/dzmm_bot/core/reply_templates.py src/dzmm_bot/core/repository.py src/dzmm_bot/core/service.py tests/core/test_group_commands.py
git commit -m "feat: add rank department and promotion commands"
```

### Task 3: 核心管理 API 与分页响应

**Files:**
- Modify: `src/dzmm_bot/core/api_models.py`
- Modify: `src/dzmm_bot/core/app.py`
- Modify: `src/dzmm_bot/core/repository.py`
- Test: `tests/core/test_app.py`

**Interfaces:**
- Produces `RankResponse`, `DepartmentResponse`, `PromotionRequestResponse` 与通用分页响应。
- Produces核心端点：`GET/PATCH /internal/game/ranks`、`GET/POST/PATCH/DELETE /internal/game/departments`、`GET /internal/game/promotions`、`POST /internal/game/users/{platform_id}/board-membership`。
- Consumes Task 1 仓储接口；核心董事会操作由上游管理端认证后调用。

- [ ] **Step 1: 写出 API 失败测试**

```python
def test_game_rank_and_department_endpoints_return_paginated_config(client, headers):
    ranks = client.get("/internal/game/ranks", headers=headers)
    departments = client.get("/internal/game/departments?page=1&page_size=20", headers=headers)
    assert ranks.status_code == 200
    assert ranks.json()[0]["name"] == "实习生"
    assert departments.json()["items"][0]["name"] == "未分配部门"
```

- [ ] **Step 2: 运行 API 测试确认失败**

Run: `pytest tests/core/test_app.py -k 'rank or department or promotion' -v`

Expected: FAIL，端点和响应模型尚不存在。

- [ ] **Step 3: 实现最小请求/响应模型和端点**

```python
@app.get("/internal/game/promotions", response_model=PaginatedPromotionRequestsResponse)
def game_promotions(..., state: PromotionState | None = None, page: int = Query(1, ge=1)):
    records, total = repository.list_promotion_requests(state, page, page_size)
    return _paginated_promotion_response(records, total, page, page_size)
```

所有名称、说明、数值边界在 Pydantic 中验证；职级编辑按固定顺序保存，核心董事会不能改为普通可申请职位。部门删除遇到仍在职人数时返回 409，重复部门名返回 422。员工列表响应加入职位、部门字段。

- [ ] **Step 4: 运行 API 测试**

Run: `pytest tests/core/test_app.py -v`

Expected: PASS，覆盖认证、分页、验证、冲突和核心董事会变更的核心端响应。

- [ ] **Step 5: 提交**

```bash
git add src/dzmm_bot/core/api_models.py src/dzmm_bot/core/app.py src/dzmm_bot/core/repository.py tests/core/test_app.py
git commit -m "feat: expose rank and department management APIs"
```

### Task 4: 管理端服务代理与权限边界

**Files:**
- Modify: `src/dzmm_bot/admin/core_client.py`
- Modify: `src/dzmm_bot/admin/app.py`
- Test: `tests/admin/test_app.py`

**Interfaces:**
- Extends `AdminCorePort` / `CoreClient` with职级、部门、审批记录和核心董事会调用。
- Produces管理端 API：`/api/game/ranks`、`/api/game/departments`、`/api/game/promotions`、`/api/game/users/{platform_id}/board-membership`。
- Consumes Task 3 内部核心 API；普通管理员可维护职位/部门并查看记录，董事会变更只经 `require_super_admin`。

- [ ] **Step 1: 写出管理端 API 失败测试**

```python
def test_regular_admin_cannot_change_board_membership_but_can_read_rank_pages(client, admin_headers, core):
    assert client.get("/api/game/ranks", headers=admin_headers).status_code == 200
    response = client.post("/api/game/users/user-1/board-membership", headers=admin_headers, json={"member": True})
    assert response.status_code == 403
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/admin/test_app.py -k 'rank or department or board' -v`

Expected: FAIL，因为代理接口尚不存在。

- [ ] **Step 3: 实现代理与并发保护**

```python
@app.patch("/api/game/ranks")
def set_ranks(request: dict, identity: Annotated[AdminIdentity, Depends(authorize)], ...):
    return versioned_configuration_response(
        identity, idempotency_key, if_match,
        lambda: _relay_core(lambda: core.set_game_ranks(request["ranks"])),
        scope="game-ranks",
    )
```

对职级和部门写操作使用现有 `versioned_configuration_response`；创建部门使用 `idempotent_response`；董事会授予/撤销仅 `require_super_admin` 且使用独立幂等 scope。错误经 `_relay_core` 保留 409/422 语义。

- [ ] **Step 4: 运行管理端 API 测试**

Run: `pytest tests/admin/test_app.py -v`

Expected: PASS，覆盖角色授权、版本冲突、幂等重放、创建后刷新所需响应以及董事会超级管理员限制。

- [ ] **Step 5: 提交**

```bash
git add src/dzmm_bot/admin/core_client.py src/dzmm_bot/admin/app.py tests/admin/test_app.py
git commit -m "feat: add rank and department admin APIs"
```

### Task 5: 管理端职位与部门界面

**Files:**
- Modify: `src/dzmm_bot/admin/templates/index.html`
- Modify: `src/dzmm_bot/admin/static/admin.js`
- Modify: `src/dzmm_bot/admin/static/admin.css`
- Test: `tests/admin/test_app.py`

**Interfaces:**
- Consumes Task 4 的管理端 API。
- Produces左侧“职位与部门”导航、职级配置表、部门列表/编辑弹窗、审批记录分页和员工职位部门展示。
- Produces与既有 `runButtonAction`、`requestGame`、`renderPagination` 和标准 toast 一致的写操作交互。

- [ ] **Step 1: 写出页面结构失败测试**

```python
def test_admin_page_has_rank_department_view_and_pagination(client, headers):
    page = client.get("/", headers=headers).text
    assert 'id="nav-ranks"' in page
    assert 'id="ranks-view"' in page
    assert 'id="department-pagination"' in page
    assert 'id="promotion-pagination"' in page
```

- [ ] **Step 2: 运行页面测试确认失败**

Run: `pytest tests/admin/test_app.py -k 'rank_department_view' -v`

Expected: FAIL，因为导航和容器尚不存在。

- [ ] **Step 3: 实现最小可运营界面**

```javascript
async function loadRanksAndDepartments(page = departmentPage) {
  const [ranks, departments, promotions] = await Promise.all([
    requestGame("/api/game/ranks"),
    requestGame(`/api/game/departments?page=${page}&page_size=${pageSize}`),
    requestGame(`/api/game/promotions?page=${promotionPage}&page_size=${pageSize}`),
  ]);
  renderRanks(ranks);
  renderDepartments(departments);
  renderPromotions(promotions);
}
```

职级采用可编辑表单并显示只读“预计所需天数”；部门新增/编辑使用弹窗，删除前显示服务器返回的在职人数冲突；晋升记录提供状态筛选和服务端分页。按钮点击后禁用并显示加载文本，成功后只刷新对应列表并显示一次标准成功 toast；轮询状态不显示成功 toast。员工列表新增职位、部门行。

- [ ] **Step 4: 添加样式与可访问性约束**

为长列表和弹窗内容使用 `max-height: calc(100vh - 40px)` 与 `overflow-y: auto`；保留已有小屏布局、焦点状态、禁用状态和危险删除按钮颜色。所有弹窗均可关闭，关闭后清除草稿和 busy 状态。

- [ ] **Step 5: 运行管理端页面测试**

Run: `pytest tests/admin/test_app.py -v`

Expected: PASS，覆盖模板结构、管理员权限、分页与接口代理；人工浏览确认新增视图的加载态、错误 toast 和滚动行为。

- [ ] **Step 6: 提交**

```bash
git add src/dzmm_bot/admin/templates/index.html src/dzmm_bot/admin/static/admin.js src/dzmm_bot/admin/static/admin.css tests/admin/test_app.py
git commit -m "feat: add rank and department admin console"
```

### Task 6: 回归验证、规则同步和部署

**Files:**
- Modify: `rule.md`（只在实现与已确认规格不一致时同步；当前规则已经包含本功能）
- Test: `tests/core/test_group_commands.py`, `tests/core/test_repository.py`, `tests/core/test_app.py`, `tests/admin/test_app.py`, `tests/deploy/test_artifacts.py`

**Interfaces:**
- Consumes Tasks 1–5。
- Produces一次可部署的、经全量测试验证的实现。

- [ ] **Step 1: 运行重点回归**

Run:

```bash
pytest tests/core/test_group_commands.py tests/core/test_repository.py tests/core/test_app.py tests/admin/test_app.py tests/deploy/test_artifacts.py -q
```

Expected: PASS，无新增失败；特别验证随机事件默认继续拦截新指令、`/我` 模板变量完整、审批并发不重复扣费。

- [ ] **Step 2: 运行完整测试套件**

Run: `pytest -q`

Expected: PASS；若失败，只修复本功能导致的失败并重新运行。

- [ ] **Step 3: 检查迁移和部署产物**

Run:

```bash
alembic upgrade head
pytest tests/deploy/test_artifacts.py -q
git diff --check
```

Expected: 迁移可在空库执行，部署产物测试和空白检查通过。

- [ ] **Step 4: 提交验证性修改（仅当有修改）**

```bash
git add rule.md tests
git commit -m "test: verify rank and department workflow"
```

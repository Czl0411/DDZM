# 管理端运营基础体验 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为管理端增长型列表提供服务端分页，并为所有写操作提供可见加载态、防重复提交和可读错误。

**Architecture:** 核心服务负责以稳定排序返回分页的员工与商品数据，管理端 API 原样代理分页元数据。前端按视图保存页码并使用单一的写操作包装器控制按钮状态和错误解析，写入成功后只重新加载受影响的数据。

**Tech Stack:** FastAPI、SQLAlchemy、PostgreSQL/SQLite、原生浏览器 JavaScript、pytest。

## Global Constraints

- 员工与物品默认每页固定为 20 条，客户端不得一次拉取全量数据。
- 指令库是固定配置集合，不分页。
- 所有写操作都必须禁用触发控件，完成后恢复；失败必须保留表单输入。
- 分页和写操作必须保留现有管理员 Token 授权边界。
- 不增加商品搜索、筛选、编辑或删除功能。

---

### Task 1: 核心分页查询与 API 契约

**Files:**
- Modify: `src/dzmm_bot/core/repository.py:815-845`
- Modify: `src/dzmm_bot/core/api_models.py:105-132`
- Modify: `src/dzmm_bot/core/app.py:228-255`
- Test: `tests/core/test_repository.py`
- Test: `tests/core/test_app.py`

**Interfaces:**
- Produces `CoreRepository.list_users_page(page: int, page_size: int) -> tuple[list[UserRecord], int]`.
- Produces `CoreRepository.list_active_items_page(page: int, page_size: int) -> tuple[list[ItemRecord], int]`.
- Produces `GET /internal/game/users?page=1&page_size=20` and `GET /internal/game/items?page=1&page_size=20` returning `{"items": [...], "page": 1, "page_size": 20, "total": 0, "pages": 0}`.

- [ ] **Step 1: Write failing repository pagination tests**

```python
def test_user_page_returns_newest_twenty_and_total(repository, now):
    for index in range(21):
        repository.create_user(f"u-{index}", f"员工{index}", now + timedelta(minutes=index), 0)

    users, total = repository.list_users_page(1, 20)

    assert total == 21
    assert [user.display_name for user in users] == [
        *(f"员工{index}" for index in range(20, 0, -1))
    ]


def test_item_page_returns_newest_records(repository):
    for index in range(21):
        repository.add_item(f"物品{index}", "说明", index, 1)

    items, total = repository.list_active_items_page(2, 20)

    assert total == 21
    assert [item.name for item in items] == ["物品0"]
```

- [ ] **Step 2: Run repository tests to verify they fail**

Run: `.venv/bin/pytest tests/core/test_repository.py -k 'user_page_returns_newest_twenty or item_page_returns_newest_records' -v`

Expected: FAIL because the pagination methods do not exist.

- [ ] **Step 3: Implement the two repository methods with `count`, descending order, `offset`, and `limit`**

```python
def list_users_page(self, page: int, page_size: int) -> tuple[list[UserRecord], int]:
    with self._session() as session:
        total = int(session.scalar(select(func.count()).select_from(UserRecord)) or 0)
        users = list(session.scalars(
            select(UserRecord)
            .order_by(UserRecord.joined_at.desc(), UserRecord.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ))
        return users, total
```

Use the same query shape for active items ordered by `ItemRecord.created_at.desc(), ItemRecord.id.desc()`.

- [ ] **Step 4: Write failing core API pagination test**

```python
def test_game_users_return_page_metadata(client, headers, repository, now):
    for index in range(21):
        repository.create_user(f"u-{index}", f"员工{index}", now, 0)

    response = client.get("/internal/game/users?page=2&page_size=20", headers=headers)

    assert response.json()["page"] == 2
    assert response.json()["total"] == 21
    assert len(response.json()["items"]) == 1
```

- [ ] **Step 5: Add typed response models and page-validated API routes**

```python
class PaginatedUsersResponse(ApiModel):
    items: list[UserResponse]
    page: int
    page_size: int
    total: int
    pages: int

@app.get("/internal/game/users", response_model=PaginatedUsersResponse)
def game_users(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    users, total = repository.list_users_page(page, page_size)
    return _page_response(users, page, page_size, total)
```

Implement the item route with `PaginatedItemsResponse`; `pages` is `(total + page_size - 1) // page_size`.

- [ ] **Step 6: Run focused core pagination tests**

Run: `.venv/bin/pytest tests/core/test_repository.py tests/core/test_app.py -k 'page_returns_newest or page_metadata' -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/dzmm_bot/core/repository.py src/dzmm_bot/core/api_models.py src/dzmm_bot/core/app.py tests/core/test_repository.py tests/core/test_app.py
git commit -m "feat: paginate game management data"
```

### Task 2: 管理端分页代理

**Files:**
- Modify: `src/dzmm_bot/admin/core_client.py:15-110`
- Modify: `src/dzmm_bot/admin/app.py:125-135`
- Test: `tests/admin/test_app.py`

**Interfaces:**
- Consumes the paginated core responses from Task 1.
- Produces `GET /api/game/users?page=1&page_size=20` and `GET /api/game/items?page=1&page_size=20` with the unchanged page envelope.

- [ ] **Step 1: Write failing management proxy test**

```python
def test_admin_proxies_employee_page_metadata(client, headers, core):
    core.employees = [{"platform_id": "u1", "display_name": "小明", "balance": 5, "joined_at": "2026-08-05T09:00:00+08:00"}]

    response = client.get("/api/game/users?page=2&page_size=20", headers=headers)

    assert response.json()["page"] == 2
    assert response.json()["items"][0]["display_name"] == "小明"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/pytest tests/admin/test_app.py -k admin_proxies_employee_page_metadata -v`

Expected: FAIL because the fake core and management route still return a raw list.

- [ ] **Step 3: Update the protocol, HTTP client, routes, and fake core**

```python
def list_game_users(self, page: int, page_size: int) -> dict:
    return self._get("/internal/game/users", params={"page": page, "page_size": page_size})

@app.get("/api/game/users")
def game_users(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), ...):
    return core.list_game_users(page, page_size)
```

Apply the same signature and behavior to item methods and routes.

- [ ] **Step 4: Run all management API tests**

Run: `.venv/bin/pytest tests/admin/test_app.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dzmm_bot/admin/core_client.py src/dzmm_bot/admin/app.py tests/admin/test_app.py
git commit -m "feat: proxy paginated management data"
```

### Task 3: 前端分页、写入状态和可读错误

**Files:**
- Modify: `src/dzmm_bot/admin/templates/index.html:140-165`
- Modify: `src/dzmm_bot/admin/static/admin.js:145-460`
- Modify: `src/dzmm_bot/admin/static/admin.css:55-110`
- Test: `tests/admin/test_app.py`

**Interfaces:**
- Consumes paginated API envelopes from Task 2.
- Produces `renderPagination(container, page, pages, total, onChange)` and `runMutation(button, busyLabel, operation)` in `admin.js`.

- [ ] **Step 1: Write failing dashboard asset test for the pagination and mutation UI entry points**

```python
def test_admin_dashboard_exposes_pagination_and_mutation_controls(client):
    page = client.get("/").text
    script = client.get("/static/admin.js").text

    assert 'id="employee-pagination"' in page
    assert 'id="shop-pagination"' in page
    assert "runMutation" in script
    assert "renderPagination" in script
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/pytest tests/admin/test_app.py -k pagination_and_mutation_controls -v`

Expected: FAIL because the controls and shared helpers do not exist.

- [ ] **Step 3: Add the list footer containers and responsive styles**

```html
<div id="employee-list" class="data-list"></div>
<nav id="employee-pagination" class="pagination" aria-label="员工分页"></nav>
```

```css
.pagination { display: flex; gap: 10px; align-items: center; justify-content: flex-end; margin-top: 16px; }
.pagination small { margin-right: auto; color: var(--muted); }
```

Add matching markup for the shop list.

- [ ] **Step 4: Implement shared request, pagination, and mutation helpers**

```javascript
async function requestGame(path, options = {}) {
  const response = await fetch(path, {...options, headers: {...headers(), ...(options.headers || {})}});
  if (response.ok) return response.json();
  const body = await response.text();
  try { throw new Error(JSON.parse(body).detail || response.status); }
  catch (error) { if (error instanceof SyntaxError) throw new Error(body || response.status); throw error; }
}

async function runMutation(button, busyLabel, operation) {
  if (button.disabled) return;
  const label = button.textContent;
  button.disabled = true;
  button.textContent = busyLabel;
  try { return await operation(); }
  finally { button.disabled = false; button.textContent = label; }
}
```

Maintain `employeePage` and `shopPage`; load their respective envelopes with `?page=${page}&page_size=20`, render rows, then render previous/next controls. Wrap every POST/PATCH action in `runMutation`; keep form values on exceptions and reload only after successful mutations.

- [ ] **Step 5: Run focused dashboard asset test**

Run: `.venv/bin/pytest tests/admin/test_app.py -k pagination_and_mutation_controls -v`

Expected: PASS.

- [ ] **Step 6: Run the full test suite and compile check**

Run: `.venv/bin/pytest -q && .venv/bin/python -m compileall -q src && git diff --check`

Expected: all tests pass; compile and diff checks exit 0.

- [ ] **Step 7: Commit**

```bash
git add src/dzmm_bot/admin/templates/index.html src/dzmm_bot/admin/static/admin.js src/dzmm_bot/admin/static/admin.css tests/admin/test_app.py
git commit -m "feat: improve admin operation feedback"
```

### Task 4: 部署与线上验证

**Files:**
- No source changes.

**Interfaces:**
- Consumes the committed implementation from Tasks 1-3.
- Produces an active core, admin web, and browser worker deployment.

- [ ] **Step 1: Deploy the release with `deploy/scripts/deploy.sh` and restart all three services**

Run the established release upload, deployment, and systemd restart sequence for the committed revision.

- [ ] **Step 2: Verify online health and pagination contract**

Run authenticated local-host requests on the server for `/internal/game/users?page=1&page_size=20` and `/api/game/items?page=1&page_size=20`; verify both return `items`, `page`, `page_size`, `total`, and `pages`. Confirm `dzmm-core`, `dzmm-admin-web`, and `dzmm-browser-worker` are active.

- [ ] **Step 3: Verify the admin UI manually**

Open the admin console, navigate both paginated lists, submit one permitted mutation, and confirm its button shows a busy label until the request completes.

## Plan Self-Review

- Spec coverage: Task 1 and 2 implement server-side pagination; Task 3 implements busy state, duplicate prevention, readable errors, scoped refresh, and pagination controls; Task 4 verifies deployment.
- Placeholder scan: no unresolved tasks or undefined interfaces remain.
- Type consistency: every paginated route returns the `items/page/page_size/total/pages` envelope consumed by the proxy and frontend.

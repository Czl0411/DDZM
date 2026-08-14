# 员工摸鱼币流水后台 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在管理后台员工列表中提供单员工摸鱼币流水分页弹窗，显示当前余额、中文来源、变动金额和变动后余额。

**Architecture:** 复用现有 `balance_transactions` 表，由核心仓库以窗口累计值计算任意分页的 `balance_after`，核心内部接口输出稳定分页结构，管理服务只做认证代理，原生管理端页面负责只读展示与翻页。功能不增加迁移、不改变任何余额写入路径。

**Tech Stack:** Python 3.12、FastAPI、SQLAlchemy 2、PostgreSQL/SQLite、原生 HTML/CSS/JavaScript、pytest。

## Global Constraints

- 入口只在管理后台员工列表中开放，普通管理员和超级管理员都可查看。
- 默认每页 20 条，允许页大小 1 至 100，按 `occurred_at DESC, id DESC` 稳定排序。
- 展示当前余额、流水总数、时间、中文来源、正负金额和变动后余额。
- 未知来源必须保留并显示原始 `source`。
- 只读取 2026-08-05 起已有流水，不补造更早历史。
- 不新增数据库迁移、不修改余额、不新增玩家指令、筛选或导出。

---

### Task 1: 核心仓库分页与余额计算

**Files:**
- Modify: `src/dzmm_bot/core/repository.py`
- Test: `tests/core/test_repository.py`

**Interfaces:**
- Produces: `BalanceTransactionSummary(id: UUID, amount: int, source: str, source_label: str, occurred_at: datetime, balance_after: int)`.
- Produces: `EmployeeBalanceLedger(platform_id: str, display_name: str, current_balance: int, items: tuple[BalanceTransactionSummary, ...], total: int)`.
- Produces: `balance_source_label(source: str) -> str` with known Chinese labels and raw-source fallback.
- Produces: `CoreRepository.list_balance_transactions_page(platform_id: str, page: int, page_size: int) -> EmployeeBalanceLedger | None`.

- [ ] **Step 1: Write failing repository tests**

Add tests that create one employee, record ordered positive and negative transactions including an unknown source, then assert page 1 and page 2 return stable descending order, correct Chinese labels, raw fallback, total count, current balance, and `balance_after` values. Add a separate employee with no transactions and assert an empty ledger with its current balance. Add a missing employee assertion returning `None`.

```python
page_one = repository.list_balance_transactions_page("ledger-user", 1, 2)
assert [item.amount for item in page_one.items] == [7, -3]
assert [item.balance_after for item in page_one.items] == [24, 17]
assert page_one.items[0].source_label == "每日打卡"
assert repository.list_balance_transactions_page("missing", 1, 20) is None
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `.venv/bin/pytest -q tests/core/test_repository.py -k balance_transactions_page`

Expected: FAIL because `list_balance_transactions_page` and the summary types do not exist.

- [ ] **Step 3: Add source labels and repository query**

Add immutable summary/page dataclasses near the existing admin summary types. Add a module-level `_BALANCE_SOURCE_LABELS` mapping containing every label from the approved spec and:

```python
def balance_source_label(source: str) -> str:
    return _BALANCE_SOURCE_LABELS.get(source, source)
```

Implement the repository method by locking nothing and changing nothing. Filter by user, count rows, and select records with this window expression before applying offset/limit:

```python
newer_total = func.coalesce(
    func.sum(BalanceTransactionRecord.amount).over(
        order_by=(
            BalanceTransactionRecord.occurred_at.desc(),
            BalanceTransactionRecord.id.desc(),
        ),
        rows=(None, -1),
    ),
    0,
)
balance_after = (user.balance - newer_total).label("balance_after")
```

Return `EmployeeBalanceLedger` with tuple items; do not call `_apply_balance_change`.

- [ ] **Step 4: Run repository tests and verify GREEN**

Run: `.venv/bin/pytest -q tests/core/test_repository.py -k 'balance_transactions_page or balance_change'`

Expected: PASS, including existing balance-write regression tests.

- [ ] **Step 5: Commit Task 1**

```bash
git add src/dzmm_bot/core/repository.py tests/core/test_repository.py
git commit -m "feat: query employee balance ledger"
```

### Task 2: 核心与管理服务只读接口

**Files:**
- Modify: `src/dzmm_bot/core/api_models.py`
- Modify: `src/dzmm_bot/core/app.py`
- Modify: `src/dzmm_bot/admin/core_client.py`
- Modify: `src/dzmm_bot/admin/app.py`
- Test: `tests/core/test_app.py`
- Test: `tests/admin/test_app.py`

**Interfaces:**
- Consumes: `CoreRepository.list_balance_transactions_page(...)` from Task 1.
- Produces: `BalanceTransactionResponse` and `PaginatedBalanceTransactionsResponse`.
- Produces: internal GET `/internal/game/users/{platform_id}/balance-transactions`.
- Produces: `AdminCorePort.list_balance_transactions(platform_id: str, page: int, page_size: int) -> dict`.
- Produces: admin GET `/api/game/users/{platform_id}/balance-transactions`.

- [ ] **Step 1: Write failing core API tests**

Create an employee and transactions, call the internal endpoint with `page=1&page_size=2`, and assert:

```python
assert response.json() == {
    "platform_id": "ledger-user",
    "display_name": "流水员工",
    "current_balance": 24,
    "items": [
        {
            "id": str(latest_transaction.id),
            "amount": 7,
            "source": "checkin",
            "source_label": "每日打卡",
            "occurred_at": latest_time.isoformat(),
            "balance_after": 24,
        },
        {
            "id": str(second_transaction.id),
            "amount": -3,
            "source": "shop",
            "source_label": "商店购买",
            "occurred_at": second_time.isoformat(),
            "balance_after": 17,
        },
    ],
    "page": 1,
    "page_size": 2,
    "total": 3,
    "pages": 2,
}
```

Also assert missing employee returns 404, invalid pagination returns 422, and an unauthenticated request returns 401.

- [ ] **Step 2: Run core API tests and verify RED**

Run: `.venv/bin/pytest -q tests/core/test_app.py -k balance_transactions`

Expected: FAIL with 404 because the route does not exist.

- [ ] **Step 3: Add typed response models and core route**

Add models:

```python
class BalanceTransactionResponse(ApiModel):
    id: UUID
    amount: int
    source: str
    source_label: str
    occurred_at: datetime
    balance_after: int

class PaginatedBalanceTransactionsResponse(ApiModel):
    platform_id: str
    display_name: str
    current_balance: int
    items: list[BalanceTransactionResponse]
    page: int
    page_size: int
    total: int
    pages: int
```

Add the authenticated route with `Query(1, ge=1)` and `Query(20, ge=1, le=100)`. Return 404 when the repository returns `None`; otherwise calculate `pages` with `(total + page_size - 1) // page_size`.

- [ ] **Step 4: Run core API tests and verify GREEN**

Run: `.venv/bin/pytest -q tests/core/test_app.py -k balance_transactions`

Expected: PASS.

- [ ] **Step 5: Write failing admin proxy tests**

Extend the admin `FakeCore` with captured call state. Test the authenticated route forwards `platform_id`, page, and page size, returns the core payload unchanged, rejects missing admin credentials, and returns 422 for invalid pagination.

- [ ] **Step 6: Run admin tests and verify RED**

Run: `.venv/bin/pytest -q tests/admin/test_app.py -k balance_transactions`

Expected: FAIL because the admin client method and route do not exist.

- [ ] **Step 7: Add admin client method and route**

Add to protocol and client:

```python
def list_balance_transactions(
    self, platform_id: str, page: int, page_size: int
) -> dict:
    return self._get(
        f"/internal/game/users/{platform_id}/balance-transactions",
        params={"page": page, "page_size": page_size},
    )
```

The existing `_get(path, params)` accepts query parameters, so use it directly. Add the authenticated admin route and relay core HTTP errors using the existing `_relay_core` convention.

- [ ] **Step 8: Run API test files and verify GREEN**

Run: `.venv/bin/pytest -q tests/core/test_app.py tests/admin/test_app.py -k 'balance_transactions or admin_routes_require_admin_token'`

Expected: PASS.

- [ ] **Step 9: Commit Task 2**

```bash
git add src/dzmm_bot/core/api_models.py src/dzmm_bot/core/app.py src/dzmm_bot/admin/core_client.py src/dzmm_bot/admin/app.py tests/core/test_app.py tests/admin/test_app.py
git commit -m "feat: expose employee balance ledger"
```

### Task 3: 员工流水弹窗

**Files:**
- Modify: `src/dzmm_bot/admin/templates/index.html`
- Modify: `src/dzmm_bot/admin/static/admin.js`
- Modify: `src/dzmm_bot/admin/static/admin.css`
- Test: `tests/admin/test_app.py`

**Interfaces:**
- Consumes: admin balance-transactions endpoint from Task 2.
- Produces: employee-row `data-balance-ledger` button, `#employee-balance-ledger-modal`, and paginated rendering functions.

- [ ] **Step 1: Write failing management-surface test**

Extend the existing admin HTML/JavaScript surface test to require:

```python
assert 'id="employee-balance-ledger-modal"' in page
assert 'id="employee-balance-ledger-list"' in page
assert 'data-balance-ledger=' in script
assert 'balance-transactions?page=${page}&page_size=20' in script
```

Also require visible copy for “当前余额”, “暂无摸鱼币流水记录”, “上一页” and “下一页”.

- [ ] **Step 2: Run the surface test and verify RED**

Run: `.venv/bin/pytest -q tests/admin/test_app.py -k 'balance_ledger_surface'`

Expected: FAIL because the modal and button are absent.

- [ ] **Step 3: Add modal markup and minimal styles**

Add a modal after the employee profile modal containing title, current-balance summary, total count, list container, pagination container and close controls. Reuse existing modal/list/button classes; add only small ledger-specific classes for positive and negative amount colors and a scrollable list.

- [ ] **Step 4: Add employee button and JavaScript behavior**

Add a “摸鱼币流水” button to each employee row with platform ID and current display name. Implement:

```javascript
async function openEmployeeBalanceLedger(platformId, displayName) {
  employeeBalanceLedgerModal.dataset.platformId = platformId;
  employeeBalanceLedgerModal.dataset.displayName = displayName;
  await loadEmployeeBalanceLedger(1);
  employeeBalanceLedgerModal.hidden = false;
}

async function loadEmployeeBalanceLedger(page) {
  const platformId = employeeBalanceLedgerModal.dataset.platformId;
  const ledger = await requestGame(`/api/game/users/${platformId}/balance-transactions?page=${page}&page_size=20`);
  const rows = ledger.items.map((item) => ({
    source: escapeHtml(item.source_label),
    amount: item.amount > 0 ? `+${item.amount}` : String(item.amount),
    balanceAfter: item.balance_after,
    occurredAt: formatHeartbeat(item.occurred_at),
  }));
}
```

Use `escapeHtml` for employee/source text and `formatHeartbeat` for time. Render `+N` for positive amounts and the original negative number for expenses. Reuse `renderPagination` for previous/next navigation. On close, hide the modal and delete its dataset values. Errors use the existing `setResult` toast and leave existing data visible.

- [ ] **Step 5: Run admin tests and JavaScript syntax check**

Run: `.venv/bin/pytest -q tests/admin/test_app.py -k 'balance_transactions or balance_ledger_surface'`

Run: `node --check src/dzmm_bot/admin/static/admin.js`

Expected: PASS and exit 0.

- [ ] **Step 6: Commit Task 3**

```bash
git add src/dzmm_bot/admin/templates/index.html src/dzmm_bot/admin/static/admin.js src/dzmm_bot/admin/static/admin.css tests/admin/test_app.py
git commit -m "feat: show employee balance ledger"
```

### Task 4: 全量回归与交付

**Files:**
- Modify only files required to fix regressions introduced by Tasks 1–3.

**Interfaces:**
- Consumes all preceding interfaces.
- Produces no new behavior.

- [ ] **Step 1: Run static checks**

Run: `git diff --check`

Run: `node --check src/dzmm_bot/admin/static/admin.js`

Run: `.venv/bin/python -m compileall -q src`

Expected: all exit 0.

- [ ] **Step 2: Run full test suite**

Run: `.venv/bin/pytest -q`

Expected: zero failures; record passed and skipped counts.

- [ ] **Step 3: Inspect scope and repository state**

Run: `git diff --stat main...HEAD`

Run: `git status --short --branch`

Verify only the approved repository/API/admin files changed and `.env`, `.DS_Store`, and `docs/BOT_MESSAGE_TRANSPORT_HANDOFF.md` were not added.

- [ ] **Step 4: Request code review and fix only verified findings**

Use `superpowers:requesting-code-review` with the spec, this plan, base SHA, and head SHA. Fix Critical and Important findings with a failing regression test first; rerun full verification.

- [ ] **Step 5: Report without automatic deployment**

Report the branch, commits, changed surface and fresh verification results. Do not deploy until the user explicitly requests deployment.

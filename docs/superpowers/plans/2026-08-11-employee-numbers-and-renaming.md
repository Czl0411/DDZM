# Employee Numbers and Renaming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every employee a permanent sequential work number, expose it only in identity-management surfaces, support exact bonus targeting by work number, and add `/修改名称 新名称`.

**Architecture:** Persist a unique integer on `users` and allocate future numbers through a locked single-row counter. Keep work numbers separate from display names, format them only at presentation boundaries, and add repository operations for renaming and resolving bonus targets without changing game-facing name flows.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL production, SQLite tests, vanilla JavaScript admin UI, pytest.

## Global Constraints

- Historical employees receive numbers in `joined_at ASC, id ASC` order.
- Numbers start at `1`, are permanent, are never reused, and display with a minimum width of four digits.
- Work numbers are visible only on `/入职`, `/我`, the admin employee list, and ambiguous-target guidance.
- Existing game, event, red-packet, balance, inventory, promotion, and department messages keep plain display names.
- `/修改名称` is free, unlimited, self-service, accepts duplicate names, and preserves all non-name employee state.
- Existing untracked files `.DS_Store`, `.env`, and `docs/BOT_MESSAGE_TRANSPORT_HANDOFF.md` must remain untouched.

---

### Task 1: Persist and backfill employee numbers

**Files:**
- Create: `migrations/versions/20260811_37_employee_numbers.py`
- Create: `tests/deploy/test_employee_number_migration.py`
- Modify: `src/dzmm_bot/core/schema.py`
- Modify: `tests/deploy/test_artifacts.py`

**Interfaces:**
- Produces: `UserRecord.employee_number: int`
- Produces: `EmployeeNumberCounterRecord(id=1, next_number: int)`
- Produces: Alembic revision `20260811_37` after `20260811_36`

- [ ] **Step 1: Write the failing migration and schema tests**

```python
def test_employee_number_migration_backfills_by_joined_at_then_uuid(tmp_path, monkeypatch):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'employees.db'}"
    monkeypatch.setenv("DZMM_DATABASE_URL", database_url)
    config = Config(str(ROOT / "alembic.ini"))
    engine = create_engine(database_url)
    metadata = MetaData()
    users = Table(
        "users",
        metadata,
        Column("id", Uuid, primary_key=True),
        Column("platform_id", String(255), nullable=False),
        Column("display_name", String(64), nullable=False),
        Column("balance", Integer, nullable=False),
        Column("joined_at", DateTime(timezone=True), nullable=False),
    )
    metadata.create_all(engine)
    early = datetime(2026, 8, 1, tzinfo=UTC)
    late = datetime(2026, 8, 2, tzinfo=UTC)
    ids = [UUID(int=3), UUID(int=1), UUID(int=2)]
    with engine.begin() as connection:
        connection.execute(users.insert(), [
            {"id": ids[0], "platform_id": "late", "display_name": "晚", "balance": 0, "joined_at": late},
            {"id": ids[1], "platform_id": "early-1", "display_name": "早甲", "balance": 0, "joined_at": early},
            {"id": ids[2], "platform_id": "early-2", "display_name": "早乙", "balance": 0, "joined_at": early},
        ])
    command.stamp(config, "20260811_36")
    command.upgrade(config, "head")
    with engine.connect() as connection:
        rows = connection.execute(text("SELECT platform_id, employee_number FROM users ORDER BY employee_number")).all()
        assert rows == [("early-1", 1), ("early-2", 2), ("late", 3)]
        assert connection.execute(text("SELECT next_number FROM employee_number_counters WHERE id = 1")).scalar_one() == 4
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `pytest -q tests/deploy/test_employee_number_migration.py tests/deploy/test_artifacts.py`

Expected: FAIL because revision `20260811_37`, the new column, and the counter table do not exist.

- [ ] **Step 3: Implement the migration and ORM records**

```python
class EmployeeNumberCounterRecord(Base):
    __tablename__ = "employee_number_counters"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    next_number: Mapped[int] = mapped_column(Integer, nullable=False)

employee_number: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
```

The migration must add the column as nullable, select historical IDs with `ORDER BY joined_at ASC, id ASC`, write sequential values, change the column to non-null, add a unique constraint, create the counter table, and insert `(1, max_number + 1)`.

- [ ] **Step 4: Run migration tests and verify GREEN**

Run: `pytest -q tests/deploy/test_employee_number_migration.py tests/deploy/test_artifacts.py`

Expected: PASS with Alembic head `20260811_37`.

- [ ] **Step 5: Commit**

```bash
git add migrations/versions/20260811_37_employee_numbers.py src/dzmm_bot/core/schema.py tests/deploy/test_employee_number_migration.py tests/deploy/test_artifacts.py
git commit -m "feat: persist employee numbers"
```

### Task 2: Allocate numbers and rename employees in the repository

**Files:**
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `tests/core/test_repository.py`

**Interfaces:**
- Produces: `format_employee_number(number: int) -> str`
- Produces: `RenameEmployeeResult(status: str, old_name: str | None, new_name: str | None)`
- Produces: `CoreRepository.rename_user(platform_id: str, new_name: str) -> RenameEmployeeResult`
- Changes: `CoreRepository.create_user(platform_id: str, display_name: str, joined_at: datetime, initial_balance: int) -> tuple[UserRecord, bool]` assigns the next persistent number.

- [ ] **Step 1: Write failing repository tests**

```python
def test_create_user_allocates_permanent_employee_numbers(repository, now):
    first, _ = repository.create_user("u1", "甲", now, 0)
    second, _ = repository.create_user("u2", "乙", now, 0)
    existing, created = repository.create_user("u1", "新甲", now, 0)
    assert (first.employee_number, second.employee_number) == (1, 2)
    assert created is False
    assert existing.employee_number == 1

def test_rename_user_changes_only_name_and_allows_duplicates(repository, now):
    first, _ = repository.create_user("u1", "甲", now, 10)
    repository.create_user("u2", "乙", now, 20)
    result = repository.rename_user("u1", "乙")
    renamed = repository.find_user("u1")
    assert result.status == "renamed"
    assert renamed.display_name == "乙"
    assert renamed.employee_number == first.employee_number
    assert renamed.balance == 10
```

Also cover `not_joined`, `invalid_name`, and `unchanged` without database writes.

- [ ] **Step 2: Run repository tests and verify RED**

Run: `pytest -q tests/core/test_repository.py -k 'employee_number or rename_user'`

Expected: FAIL because allocation and renaming APIs do not exist.

- [ ] **Step 3: Implement minimal repository behavior**

```python
def format_employee_number(number: int) -> str:
    return f"#{number:04d}"

def _take_employee_number(self, session: Session) -> int:
    counter = session.scalar(
        select(EmployeeNumberCounterRecord).where(
            EmployeeNumberCounterRecord.id == 1
        ).with_for_update()
    )
    if counter is None:
        next_number = int(session.scalar(select(func.coalesce(func.max(UserRecord.employee_number), 0))) or 0) + 1
        counter = EmployeeNumberCounterRecord(id=1, next_number=next_number)
        session.add(counter)
        session.flush()
    number = counter.next_number
    counter.next_number += 1
    return number
```

Normalize rename input with `.strip()`, reject lengths outside `1..64`, and update only `UserRecord.display_name`.

- [ ] **Step 4: Run repository tests and verify GREEN**

Run: `pytest -q tests/core/test_repository.py -k 'employee_number or rename_user'`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dzmm_bot/core/repository.py tests/core/test_repository.py
git commit -m "feat: allocate employee numbers and rename users"
```

### Task 3: Add `/修改名称` and identity-only work-number output

**Files:**
- Modify: `src/dzmm_bot/core/commands.py`
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `src/dzmm_bot/core/reply_templates.py`
- Modify: `tests/core/test_group_commands.py`
- Modify: `tests/core/test_repository.py`

**Interfaces:**
- Adds command syntax: `/修改名称 新名称`
- Adds reply scenarios: `usage`, `not_joined`, `invalid_name`, `unchanged`, `renamed`
- Adds template variable `{工号}` only to `/入职` and `/我` identity responses.

- [ ] **Step 1: Write failing command and template tests**

```python
def test_join_and_me_show_employee_number_but_balance_does_not():
    joined = _receive(service, "join", "u1", "/入职 小明", now)
    assert "你的工号：#0001" in _reply(joined)
    assert "工号：#0001" in _reply(_receive(service, "me", "u1", "/我", now))
    assert "#0001" not in _reply(_receive(service, "balance", "u1", "/余额", now))

def test_rename_command_allows_duplicate_name_and_preserves_number():
    service, repository, factory = _service()
    now = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)
    repository.create_user("u1", "甲", now, 0)
    repository.create_user("u2", "乙", now, 0)
    rename = _receive(service, "rename", "u1", "/修改名称 乙", now)
    assert _replies_for(factory, rename.message_id) == ["名称已修改：甲 → 乙。"]
    assert repository.find_user("u1").employee_number == 1
```

Test missing name, over-64 name, not joined, and unchanged name. Assert `/帮助 基础` lists `/修改名称 新名称`.

- [ ] **Step 2: Run command tests and verify RED**

Run: `pytest -q tests/core/test_group_commands.py tests/core/test_repository.py -k 'employee_number or rename'`

Expected: FAIL because the command, templates, and `{工号}` values are absent.

- [ ] **Step 3: Register and implement the command**

Add `/修改名称` to `_COMMANDS`, `_COMMAND_DEFINITIONS`, help output, and reply templates. Dispatch it before the generic help fallback.

```python
def _rename(self, platform_id: str, content: str, received_at) -> str:
    new_name = content[len("/修改名称"):].strip()
    if not new_name:
        return self._reply("/修改名称", "usage", received_at)
    result = self._repository.rename_user(platform_id, new_name)
    values = {"{旧名称}": result.old_name, "{新名称}": result.new_name}
    return self._reply("/修改名称", result.status, received_at, values)
```

Update default `/入职` and `/我` templates to show `{工号}` while leaving all other templates unchanged.

- [ ] **Step 4: Run command tests and verify GREEN**

Run: `pytest -q tests/core/test_group_commands.py tests/core/test_repository.py -k 'employee_number or rename'`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dzmm_bot/core/commands.py src/dzmm_bot/core/repository.py src/dzmm_bot/core/reply_templates.py tests/core/test_group_commands.py tests/core/test_repository.py
git commit -m "feat: add employee rename command"
```

### Task 4: Resolve bonus recipients by work number

**Files:**
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `src/dzmm_bot/core/commands.py`
- Modify: `src/dzmm_bot/core/reply_templates.py`
- Modify: `tests/core/test_repository.py`
- Modify: `tests/core/test_group_commands.py`

**Interfaces:**
- Extends: `BoardBonusResult.candidate_labels: tuple[str, ...] = ()`
- Accepts: `#1` and `#0001` as the same exact employee reference.
- Adds template variable: `{候选员工}` for `/发奖金` `ambiguous_target`.

- [ ] **Step 1: Write failing target-resolution tests**

```python
def test_board_bonus_resolves_exact_employee_number(repository, now):
    # Create a board issuer and two employees with the same display name.
    result = repository.grant_board_bonus("board", "#0002", 5, now)
    assert result.status == "granted"
    assert result.recipient_display_name == "小明"

def test_board_bonus_lists_numbered_candidates_for_duplicate_name(repository, now):
    result = repository.grant_board_bonus("board", "小明", 5, now)
    assert result.status == "ambiguous_target"
    assert result.candidate_labels == ("小明 #0002", "小明 #0003")
```

Also test `#2`, nonexistent `#9999`, unique names, and `全部`.

- [ ] **Step 2: Run focused bonus tests and verify RED**

Run: `pytest -q tests/core/test_repository.py tests/core/test_group_commands.py -k 'board_bonus or 发奖金'`

Expected: FAIL because work-number resolution and candidate labels are absent.

- [ ] **Step 3: Implement exact-number resolution and ambiguity output**

Use `re.fullmatch(r"#([0-9]+)", normalized_target)`; if matched, query only `UserRecord.employee_number`. Otherwise preserve `全部` and exact-name behavior. Sort duplicate candidates by employee number before formatting.

- [ ] **Step 4: Run focused bonus tests and verify GREEN**

Run: `pytest -q tests/core/test_repository.py tests/core/test_group_commands.py -k 'board_bonus or 发奖金'`

Expected: PASS, with successful notifications still containing plain names only.

- [ ] **Step 5: Commit**

```bash
git add src/dzmm_bot/core/repository.py src/dzmm_bot/core/commands.py src/dzmm_bot/core/reply_templates.py tests/core/test_repository.py tests/core/test_group_commands.py
git commit -m "feat: target bonuses by employee number"
```

### Task 5: Expose and display work numbers in the admin employee list

**Files:**
- Modify: `src/dzmm_bot/core/api_models.py`
- Modify: `src/dzmm_bot/core/app.py`
- Modify: `src/dzmm_bot/admin/static/admin.js`
- Modify: `tests/core/test_app.py`
- Modify: `tests/admin/test_app.py`

**Interfaces:**
- Changes: `UserResponse.employee_number: int`
- Produces browser helper: `formatEmployeeNumber(number)` returning `#0001` minimum-width format.

- [ ] **Step 1: Write failing API and static-UI tests**

```python
def test_game_users_include_employee_number(client, headers, repository, now):
    repository.create_user("u1", "员工", now, 0)
    item = client.get("/internal/game/users", headers=headers).json()["items"][0]
    assert item["employee_number"] == 1

def test_admin_employee_list_displays_and_searches_employee_number():
    script = Path("src/dzmm_bot/admin/static/admin.js").read_text()
    assert "formatEmployeeNumber(employee.employee_number)" in script
    assert "employee.employee_number" in script
```

- [ ] **Step 2: Run API/admin tests and verify RED**

Run: `pytest -q tests/core/test_app.py tests/admin/test_app.py -k 'employee'`

Expected: FAIL because responses and rendering omit `employee_number`.

- [ ] **Step 3: Implement API mapping and UI formatting**

Add `employee_number` to `_user_response`. In `loadEmployees`, render the name and `<span>#0001</span>` separately, and include both `#0001` and `1` in the client-side filter string. Leave button data attributes based on `platform_id`.

- [ ] **Step 4: Run API/admin tests and verify GREEN**

Run: `pytest -q tests/core/test_app.py tests/admin/test_app.py -k 'employee'`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dzmm_bot/core/api_models.py src/dzmm_bot/core/app.py src/dzmm_bot/admin/static/admin.js tests/core/test_app.py tests/admin/test_app.py
git commit -m "feat: show employee numbers in admin"
```

### Task 6: Run complete regression verification

**Files:**
- Modify only files required by failures directly caused by Tasks 1–5.

**Interfaces:**
- Verifies all employee-number and rename behavior plus unchanged game output.

- [ ] **Step 1: Run formatting and static checks**

Run: `git diff --check main...HEAD`

Expected: no output and exit code `0`.

- [ ] **Step 2: Run the full test suite**

Run: `pytest -q`

Expected: all tests pass with no failures.

- [ ] **Step 3: Verify migration head**

Run: `alembic heads`

Expected: exactly `20260811_37 (head)`.

- [ ] **Step 4: Inspect scope and preserved user files**

Run: `git status --short && git diff --stat main...HEAD`

Expected: only feature files differ; `.DS_Store`, `.env`, and `docs/BOT_MESSAGE_TRANSPORT_HANDOFF.md` remain untracked and unchanged.

- [ ] **Step 5: Route any regression back to its owning task**

If the full suite exposes a feature regression, return to the task that introduced it, add a focused failing test, apply the minimal correction, rerun that task's focused tests, and then rerun Steps 1–4. Do not create an unrelated catch-all change.

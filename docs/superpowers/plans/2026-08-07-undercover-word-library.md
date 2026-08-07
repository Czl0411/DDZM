# 谁是卧底词库 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a persistent, enabled-by-default library of 900 non-duplicate civilian/undercover word pairs for future Who Is the Undercover games.

**Architecture:** Add one ORM record and one self-contained Alembic migration. The migration creates `undercover_word_sets` and bulk-inserts nine categories with 100 curated pairs each. No command, repository API, game-room, card-dealing, voting, AI, or admin UI behavior changes in this plan.

**Tech Stack:** Python 3, SQLAlchemy ORM, Alembic, PostgreSQL/SQLite-compatible migrations, pytest.

## Global Constraints

- All timestamps use the existing Beijing-time `BeijingDateTime` and `beijing_now` convention.
- Initial data consists of exactly 900 enabled pairs: nine categories with 100 pairs each.
- A pair is duplicate even when the civilian and undercover words appear in reverse order.
- Words must be non-empty and remain light, daily/company-safe content.
- Do not add game commands, private-message delivery, AI integration, voting, or admin UI in this change.

---

### Task 1: Add the word-set record and migration coverage test

**Files:**
- Modify: `src/dzmm_bot/core/schema.py`
- Test: `tests/core/test_repository.py`

**Consumes:** Existing `Base`, `BeijingDateTime`, `beijing_now`, and the existing PostgreSQL migration fixture.

**Produces:** `UndercoverWordSetRecord`, and a migration test that will validate the table after the seed migration is introduced.

- [ ] **Step 1: Write the failing migration-table test**

```python
def test_migration_creates_undercover_word_sets_table(migrated_postgres_url):
    engine = create_engine(migrated_postgres_url)

    assert "undercover_word_sets" in inspect(engine).get_table_names()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/core/test_repository.py::test_migration_creates_undercover_word_sets_table -v`

Expected: FAIL because the current migration head has no `undercover_word_sets` table.

- [ ] **Step 3: Add the minimal schema record**

```python
class UndercoverWordSetRecord(Base):
    __tablename__ = "undercover_word_sets"
    __table_args__ = (UniqueConstraint("civilian_word", "undercover_word"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    civilian_word: Mapped[str] = mapped_column(String(64), nullable=False)
    undercover_word: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        BeijingDateTime, default=beijing_now, nullable=False
    )
```

- [ ] **Step 4: Run the migration-table test again**

Run: `pytest tests/core/test_repository.py::test_migration_creates_undercover_word_sets_table -v`

Expected: FAIL because the migration has not been added yet.

### Task 2: Add the 900-pair Alembic migration

**Files:**
- Create: `migrations/versions/20260807_25_undercover_word_sets.py`
- Test: `tests/core/test_repository.py`

**Consumes:** `UndercoverWordSetRecord` table shape from Task 1 and the latest Alembic revision `20260807_24`.

**Produces:** An idempotent upgrade path that creates the table and writes the 900 default enabled word pairs.

- [ ] **Step 1: Write migration-data tests**

```python
def test_migration_seeds_undercover_word_library(migrated_postgres_url):
    engine = create_engine(migrated_postgres_url)
    with engine.connect() as connection:
        rows = connection.execute(text("""
            SELECT category, civilian_word, undercover_word, enabled
            FROM undercover_word_sets
        """)).mappings().all()

    assert len(rows) == 900
    assert all(row["enabled"] for row in rows)
    assert {row["category"] for row in rows} == EXPECTED_UNDERCOVER_CATEGORIES
    assert all(sum(row["category"] == category for row in rows) == 100
               for category in EXPECTED_UNDERCOVER_CATEGORIES)
    assert len({tuple(sorted((row["civilian_word"], row["undercover_word"])))
                for row in rows}) == 900
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `pytest tests/core/test_repository.py -k undercover_word_library -v`

Expected: FAIL because no migration or seed data exists.

- [ ] **Step 3: Create the migration and curated source data**

Create revision `20260807_25`, set `down_revision = "20260807_24"`, and use `op.create_table` with `id`, `category`, `civilian_word`, `undercover_word`, `enabled`, and timezone-aware `created_at` columns. Define one immutable, self-contained Python tuple containing exactly 900 `(category, civilian_word, undercover_word)` entries.

Use `op.bulk_insert` to write rows generated as:

```python
{
    "id": uuid4(),
    "category": category,
    "civilian_word": civilian_word,
    "undercover_word": undercover_word,
    "enabled": True,
    "created_at": datetime.now(UTC),
}
```

Add a module-level guard before `upgrade()` that raises `RuntimeError` unless there are exactly 900 entries, exactly 100 per required category, no blank words, and no duplicate unordered word pairs. `downgrade()` drops only `undercover_word_sets`.

- [ ] **Step 4: Run the focused tests to verify they pass**

Run: `TEST_DATABASE_URL="$TEST_DATABASE_URL" pytest tests/core/test_repository.py -k undercover_word_library -v`

Expected: PASS with 900 records, nine 100-record categories, enabled values, and no empty or unordered duplicate pairs.

- [ ] **Step 5: Validate upgrade compatibility**

Run: `DZMM_DATABASE_URL="$TEST_DATABASE_URL" alembic upgrade head`

Expected: exit code 0 against the configured development database; `undercover_word_sets` exists with 900 rows.

### Task 3: Run regression verification and commit

**Files:**
- Modify: `src/dzmm_bot/core/schema.py`
- Create: `migrations/versions/20260807_25_undercover_word_sets.py`
- Modify: `tests/core/test_repository.py`

**Consumes:** Completed schema, migration, and migration-data tests.

**Produces:** A verified, committed fixed word library ready for future game-room work.

- [ ] **Step 1: Run the core test suite**

Run: `pytest tests/core -q`

Expected: PASS without regressions in existing economy, random-event, hide-and-seek, memory-assessment, rank, or department behavior.

- [ ] **Step 2: Check migration/source quality**

Run: `git diff --check && alembic current`

Expected: no whitespace errors and the migration revision is current after the local upgrade.

- [ ] **Step 3: Commit the implementation**

```bash
git add src/dzmm_bot/core/schema.py \
  migrations/versions/20260807_25_undercover_word_sets.py tests/core/test_repository.py
git commit -m "feat: seed undercover word library"
```

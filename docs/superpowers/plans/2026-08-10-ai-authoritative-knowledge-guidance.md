# AI Authoritative Knowledge and Guidance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the AI supervisor topic-scoped, administrator-editable rule cards plus live database facts and exact enabled command syntax, while preserving the rule that AI explains and guides but never executes.

**Architecture:** Route each player question with deterministic keywords and command aliases, load only matching enabled knowledge cards, build topic-specific live facts from existing business tables, and inject them ahead of stable player impressions. Store exact command syntax alongside the existing command registry so the model never invents a command; expose knowledge-card CRUD in the existing AI supervisor administration view.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, SQLAlchemy 2, Alembic, PostgreSQL/SQLite, DeepSeek chat completions, vanilla JavaScript, pytest.

## Global Constraints

- Complete `2026-08-10-ai-stable-impressions-and-activity-facts.md` first.
- Use Alembic revision `20260810_32` with `down_revision = "20260810_31"`.
- Fixed safety rules and live database facts outrank knowledge cards; knowledge cards outrank stable impressions.
- Stable impressions may change tone only, never numbers, eligibility, rules, commands, or results.
- The AI only explains and directs the player to send an exact command; it never calls command handlers or mutates business state.
- Only commands currently enabled in `command_definitions` may appear in guidance.
- If a business/rule answer has no authoritative card or live provider, instruct the model to say it cannot confirm and direct the player to `/帮助`.
- Do not add vector search, embeddings, a second DeepSeek classification call, or a generic provider framework.
- Do not copy dynamic balances, rewards, prices, stock, enabled departments, or active-game state into knowledge-card text.
- Preserve `.env`, `.DS_Store`, and `docs/BOT_MESSAGE_TRANSPORT_HANDOFF.md` as unrelated untracked files.

---

### Task 1: Persist knowledge cards and exact command syntax

**Files:**
- Create: `migrations/versions/20260810_32_ai_knowledge_cards.py`
- Modify: `src/dzmm_bot/core/schema.py`
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `tests/core/test_repository.py`
- Modify: `tests/deploy/test_artifacts.py`

**Interfaces:**
- Produces: `AIKnowledgeCardRecord`.
- Produces: `CommandDefinitionRecord.syntax` containing exact player-facing command forms.
- Produces fixed topic keys: `economy`, `departments`, `ranks`, `shop`, `checkin_activity`, `random_events`, `hide_and_seek`, `memory_assessment`, `undercover`, `blame_bomb`, `commands_help`, `player_activity`.

- [ ] **Step 1: Write failing persistence tests**

```python
def test_ai_knowledge_schema_and_command_syntax_contract():
    from dzmm_bot.core.schema import AIKnowledgeCardRecord, Base, CommandDefinitionRecord
    assert "ai_knowledge_cards" in Base.metadata.tables
    assert AIKnowledgeCardRecord.__table__.c.keywords.nullable is False
    assert AIKnowledgeCardRecord.__table__.c.enabled.default.arg is True
    assert CommandDefinitionRecord.__table__.c.syntax.nullable is False
```

```python
def test_command_registry_exposes_exact_enabled_syntax(repository):
    commands = {row.command: row.syntax for row in repository.list_enabled_command_definitions()}
    assert commands["/入职"] == "/入职 名字"
    assert commands["/摸鱼躲猫猫"] == "/开始摸鱼躲藏；/躲 编号"
    assert commands["/记忆考核"] == "/记忆考核；/记忆考核 对战；/答案 内容"
    assert commands["/谁是卧底"] == "/谁是卧底 人数"
    assert commands["/甩锅"] == "/甩锅 玩家编号 甩锅理由"
```

Add a migration test asserting revision `20260810_32`, down revision `20260810_31`, the new table, syntax column, and seeded rows.

- [ ] **Step 2: Run tests and verify they fail**

Run: `pytest tests/core/test_repository.py::test_ai_knowledge_schema_and_command_syntax_contract tests/core/test_repository.py::test_command_registry_exposes_exact_enabled_syntax tests/deploy/test_artifacts.py::test_ai_knowledge_migration_seeds_cards_and_syntax -v`

Expected: FAIL because the table and syntax column do not exist.

- [ ] **Step 3: Add the ORM and migration**

Use this record shape:

```python
class AIKnowledgeCardRecord(Base):
    __tablename__ = "ai_knowledge_cards"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    topic: Mapped[str] = mapped_column(String(48), nullable=False)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    keywords: Mapped[list[str]] = mapped_column(JSON_VARIANT, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    created_at: Mapped[datetime] = mapped_column(BeijingDateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(BeijingDateTime, nullable=False)
```

Use the project’s existing JSON/JSONB variant pattern. Add an index on `(topic, enabled, priority)`.

Backfill `command_definitions.syntax` from an explicit migration mapping. At minimum include every current command from `_COMMAND_DEFINITIONS`, with these multi-form values preserved exactly:

```python
{
    "/加入": "/加入；/加入 身份",
    "/摸鱼躲猫猫": "/开始摸鱼躲藏；/躲 编号",
    "/记忆考核": "/记忆考核；/记忆考核 对战；/答案 内容",
    "/谁是卧底": "/谁是卧底 人数",
    "/投票": "/投票 序号",
    "/甩锅游戏": "/甩锅游戏 人数",
    "/甩锅": "/甩锅 玩家编号 甩锅理由",
}
```

Change `_COMMAND_DEFINITIONS` tuples to `(command, syntax, description)` and update `ensure_command_definitions` to insert all three fields without overwriting administrator enablement.

- [ ] **Step 4: Seed stable, non-dynamic knowledge cards**

Seed one enabled card per stable topic with concise content derived from `rule.md`. The migration rows must use these titles and keyword sets:

```python
(
    ("economy", "金币与余额原则", ["金币", "摸鱼币", "赚钱", "收入", "余额"], "余额可能因奖励或惩罚变化；具体可用来源、金额和条件必须以实时数据为准。"),
    ("departments", "部门加入与切换", ["部门", "加入部门", "切换部门", "部门申请"], "首次加入部门与切换部门使用不同流程；普通员工通常需要目标部门更高职位成员审批，核心董事会按系统权限直接处理。"),
    ("ranks", "职位与晋升", ["职位", "职级", "晋升", "升职"], "晋升只申请下一档普通职位，申请时不扣款，同意时按冻结价格结算；核心董事会不能通过普通晋升获得。"),
    ("shop", "商店与物品", ["商店", "商品", "物品", "购买"], "商店只展示当前可用商品；是否存在购买或使用指令必须以实时启用命令为准。"),
    ("checkin_activity", "打卡与活跃度", ["打卡", "活跃", "全勤", "连续打卡"], "成功打卡按自然日计算；普通非指令发言可形成日活跃度，奖励由后台按系统配置结算。"),
    ("random_events", "随机事件", ["随机事件", "事件", "角色报名"], "随机事件按场景报名并进行；只有正式业务结果决定是否完成和获得奖励，过程发言不改变固定规则。"),
    ("hide_and_seek", "摸鱼躲猫猫", ["躲猫猫", "躲藏", "巡查"], "玩家先发起再从系统展示的地点编号中选择；最终奖励、惩罚、次数和时限以当前配置为准。"),
    ("memory_assessment", "记忆考核", ["记忆考核", "答案", "收手", "对战"], "记忆考核分单人和对战；只有机器人确认题目撤回后才接受格式正确的答案，具体难度、奖励与时限以实时配置为准。"),
    ("undercover", "谁是卧底", ["谁是卧底", "卧底", "白板", "投票"], "谁是卧底通过报名、发牌、描述和投票推进；角色配比、投票时间和胜负阈值以当前配置为准。"),
    ("blame_bomb", "甩锅游戏", ["甩锅", "锅", "事故卡", "关键词"], "甩锅游戏按编号公开转交，理由必须满足本局冻结关键词；时间、人数和经济结果以当前对局与配置为准。"),
    ("commands_help", "指令帮助", ["指令", "命令", "帮助", "怎么操作"], "只推荐当前启用且由系统提供准确语法的指令；没有可靠指令时引导玩家查看帮助。"),
    ("player_activity", "个人游戏经历", ["战绩", "玩过", "赢过", "输了", "参加过"], "个人游戏经历只使用系统结算产生的累计参与、胜负和最近结果，不根据聊天自述推断。"),
)
```

- [ ] **Step 5: Run persistence and migration tests**

Run: `pytest tests/core/test_repository.py::test_ai_knowledge_schema_and_command_syntax_contract tests/core/test_repository.py::test_command_registry_exposes_exact_enabled_syntax tests/deploy/test_artifacts.py::test_ai_knowledge_migration_seeds_cards_and_syntax -v`

Expected: PASS.

- [ ] **Step 6: Commit knowledge persistence**

```bash
git add migrations/versions/20260810_32_ai_knowledge_cards.py src/dzmm_bot/core/schema.py src/dzmm_bot/core/repository.py tests/core/test_repository.py tests/deploy/test_artifacts.py
git commit -m "feat: add authoritative AI knowledge cards"
```

---

### Task 2: Implement deterministic topic routing

**Files:**
- Create: `src/dzmm_bot/core/ai_knowledge.py`
- Create: `tests/core/test_ai_knowledge.py`

**Interfaces:**
- Produces: `KNOWLEDGE_TOPICS` and `TOPIC_COMMANDS`.
- Produces: `route_ai_topics(question: str, cards: Sequence[AIKnowledgeCard]) -> tuple[str, ...]`.
- Produces: `select_knowledge_cards(topics: Sequence[str], cards: Sequence[AIKnowledgeCard], *, limit: int = 6) -> tuple[AIKnowledgeCard, ...]`.

- [ ] **Step 1: Write failing route tests**

```python
def test_route_ai_topics_matches_multiple_relevant_topics():
    cards = (
        card("economy", ["金币", "赚钱"], priority=20),
        card("ranks", ["晋升"], priority=10),
    )
    assert route_ai_topics("我怎么赚金币然后申请晋升？", cards) == ("ranks", "economy")

def test_route_ai_topics_uses_exact_command_aliases():
    assert route_ai_topics("/躲 是怎么玩的", ()) == ("hide_and_seek",)
    assert route_ai_topics("/答案 应该怎么发", ()) == ("memory_assessment",)

def test_disabled_cards_are_not_selected():
    cards = (card("economy", ["金币"], enabled=False),)
    assert select_knowledge_cards(("economy",), cards) == ()
```

Also test case-insensitive English keywords, duplicate keywords, whitespace, maximum six selected cards, and deterministic priority/title ordering.

- [ ] **Step 2: Run route tests and verify they fail**

Run: `pytest tests/core/test_ai_knowledge.py -v`

Expected: FAIL because the router module does not exist.

- [ ] **Step 3: Implement literal keyword and alias routing**

Normalize with `strip().casefold()` only. A topic matches when one of its fixed aliases, an enabled card keyword, or an exact slash-command token appears in the question. Return each topic once, ordered by the lowest matching card priority then fixed topic order. Do not call DeepSeek and do not perform fuzzy, vector, or regex-semantic matching.

`TOPIC_COMMANDS` must map topics to canonical command rows. Alias tokens `/开始摸鱼躲藏`, `/躲`, and `/答案` route to their canonical topics but their exact syntax still comes from the canonical enabled command row.

- [ ] **Step 4: Run router tests**

Run: `pytest tests/core/test_ai_knowledge.py -v`

Expected: PASS.

- [ ] **Step 5: Commit deterministic routing**

```bash
git add src/dzmm_bot/core/ai_knowledge.py tests/core/test_ai_knowledge.py
git commit -m "feat: route AI questions to rule topics"
```

---

### Task 3: Add knowledge-card repository and Core API CRUD

**Files:**
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `src/dzmm_bot/core/api_models.py`
- Modify: `src/dzmm_bot/core/app.py`
- Modify: `tests/core/test_repository.py`
- Modify: `tests/core/test_app.py`

**Interfaces:**
- Produces repository methods: `list_ai_knowledge_cards`, `create_ai_knowledge_card`, `update_ai_knowledge_card`, and `delete_ai_knowledge_card`.
- Produces routes: `GET/POST /internal/game/ai-knowledge-cards` and `PUT/DELETE /internal/game/ai-knowledge-cards/{card_id}`.

- [ ] **Step 1: Write failing CRUD tests**

```python
created = client.post("/internal/game/ai-knowledge-cards", headers=headers, json={
    "topic": "economy",
    "title": "额外金币说明",
    "keywords": ["金币", "收入"],
    "content": "金额和开放状态以实时数据为准。",
    "enabled": True,
    "priority": 50,
})
assert created.status_code == 200
card_id = created.json()["id"]
assert client.put(f"/internal/game/ai-knowledge-cards/{card_id}", headers=headers, json={
    **created.json(), "title": "金币说明", "keywords": ["赚钱"],
}).json()["title"] == "金币说明"
assert client.delete(f"/internal/game/ai-knowledge-cards/{card_id}", headers=headers).json() == {"accepted": True}
```

Test unknown topics, duplicate/blank keywords, more than 30 keywords, keyword length over 64, blank/over-128 title, blank/over-12000 content, priority outside `0..10000`, and missing card IDs.

- [ ] **Step 2: Run CRUD tests and verify they fail**

Run: `pytest tests/core/test_repository.py tests/core/test_app.py -k 'knowledge_card' -v`

Expected: FAIL because CRUD does not exist.

- [ ] **Step 3: Implement validation and CRUD**

Trim title/content/keywords, preserve keyword display casing, reject duplicates after `casefold`, and sort list results by `topic`, `priority`, `title`, `id`. Deletion is allowed because cards are not referenced by business settlements.

- [ ] **Step 4: Implement typed Core endpoints**

Use dedicated Pydantic request/response models; never return raw ORM objects. All routes require the existing Core token. Return 404 for missing cards and 422 for validation errors.

- [ ] **Step 5: Run Core CRUD tests**

Run: `pytest tests/core/test_repository.py tests/core/test_app.py -k 'knowledge_card' -v`

Expected: PASS.

- [ ] **Step 6: Commit Core knowledge-card management**

```bash
git add src/dzmm_bot/core/repository.py src/dzmm_bot/core/api_models.py src/dzmm_bot/core/app.py tests/core/test_repository.py tests/core/test_app.py
git commit -m "feat: manage AI knowledge cards"
```

---

### Task 4: Build topic-scoped live facts and enabled command guidance

**Files:**
- Modify: `src/dzmm_bot/core/ai_knowledge.py`
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `tests/core/test_ai_knowledge.py`
- Modify: `tests/core/test_repository.py`

**Interfaces:**
- Produces: `CoreRepository.build_ai_authoritative_context(platform_id: str, question: str, now: datetime) -> AIAuthoritativeContext`.
- Produces `AIAuthoritativeContext(topics, cards_text, live_facts_text, commands_text, has_authoritative_source)`.

- [ ] **Step 1: Write failing live-context tests**

```python
def test_department_context_uses_live_enabled_departments_and_exact_commands(repository, now):
    user, _ = repository.create_user("guide", "引导玩家", now, 0)
    disabled = repository.create_department("停用部门", "不应推荐")
    repository.update_department(disabled.id, "停用部门", "不应推荐", False)
    context = repository.build_ai_authoritative_context("guide", "我能加入哪些部门", now)
    assert "departments" in context.topics
    assert "停用部门" not in context.live_facts_text
    assert "/部门" in context.commands_text
    assert "/加入部门 部门名" in context.commands_text

def test_disabled_command_is_never_in_ai_guidance(repository, now):
    repository.set_command_enabled("/晋升", False)
    context = repository.build_ai_authoritative_context("guide", "我要怎么晋升", now)
    assert "/晋升" not in context.commands_text
```

Add tests proving shop context reflects current stock, economy context reflects current configured currency/rewards, disabled games are labeled unavailable, player-activity context uses only compact facts, and unrelated topics do not load those rows.

- [ ] **Step 2: Run live-context tests and verify they fail**

Run: `pytest tests/core/test_repository.py tests/core/test_ai_knowledge.py -k 'authoritative_context or ai_guidance' -v`

Expected: FAIL because the context builder does not exist.

- [ ] **Step 3: Implement minimal topic providers**

Inside `build_ai_authoritative_context`, load all enabled cards once, route topics, then query only data required by those topics:

- `economy`: currency, onboarding reward, check-in reward, weekly reward, configured activity rewards, and which reward-bearing games are enabled.
- `departments`: player’s current department plus enabled department names/descriptions.
- `ranks`: player’s current rank, enabled ranks, promotion prices, and the next eligible ordinary rank.
- `shop`: active in-stock items with name, description, price, stock, and currency.
- `checkin_activity`: today’s successful check-in state, consecutive days, today’s activity level, and configured thresholds/rewards.
- `random_events`: enabled schedule/settings, current state, open roles when报名中, target/reward facts only from frozen current event when active.
- `hide_and_seek`: enabled state, daily limit, current player usage, entry penalty, win reward, scene count, and selection timeout.
- `memory_assessment`: enabled state, single/duel settings, current active state, and player daily usage.
- `undercover`: enabled state, role rules, vote seconds, whiteboard threshold, and current public session state.
- `blame_bomb`: enabled state, player-count duration ranges, operation timeout, active public session state, and incident-card availability; never reveal hidden explosion seconds/deadline.
- `player_activity`: compact participation/win/loss/latest-result rows from the first plan.
- `commands_help`: all currently enabled command syntax and descriptions.

For topic-specific commands, filter `list_enabled_command_definitions` through `TOPIC_COMMANDS`. Do not infer syntax from prose.

- [ ] **Step 4: Format authority labels**

Return separate strings headed `【实时系统事实】`, `【准确可用指令】`, and `【规则知识卡】`. Add `has_authoritative_source=True` when at least one live provider, enabled command, or enabled card contributes content.

- [ ] **Step 5: Run live-context tests**

Run: `pytest tests/core/test_repository.py tests/core/test_ai_knowledge.py -k 'authoritative_context or ai_guidance' -v`

Expected: PASS.

- [ ] **Step 6: Commit live fact providers**

```bash
git add src/dzmm_bot/core/ai_knowledge.py src/dzmm_bot/core/repository.py tests/core/test_ai_knowledge.py tests/core/test_repository.py
git commit -m "feat: build live AI gameplay guidance"
```

---

### Task 5: Enforce prompt authority and explain-only behavior

**Files:**
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `src/dzmm_bot/core/api_models.py`
- Modify: `src/dzmm_bot/core/app.py`
- Modify: `src/dzmm_bot/admin/app.py`
- Modify: `src/dzmm_bot/admin/static/admin.js`
- Modify: `src/dzmm_bot/admin/templates/index.html`
- Modify: `tests/core/test_repository.py`
- Modify: `tests/core/test_app.py`
- Modify: `tests/admin/test_app.py`

**Interfaces:**
- Changes: `_build_ai_system_prompt` accepts authoritative context and stable impressions in explicit priority order.
- Removes: `gameplay_guide` from active settings APIs and UI; the database column may remain as legacy storage.

- [ ] **Step 1: Write failing prompt-order and boundary tests**

```python
def test_ai_prompt_orders_authority_before_impressions(repository, now):
    claim = _claim_for_question(repository, "我怎么赚金币", now)
    prompt = claim.system_prompt
    assert prompt.index("【固定安全边界】") < prompt.index("【实时系统事实】")
    assert prompt.index("【实时系统事实】") < prompt.index("【规则知识卡】")
    assert prompt.index("【规则知识卡】") < prompt.index("【稳定玩家印象】")
    assert "只能解释并引导玩家自行发送准确指令" in prompt
    assert "不得调用命令处理器、伪造执行成功或承诺已经修改状态" in prompt

def test_unknown_business_rule_requires_help_fallback(repository, now):
    claim = _claim_for_question(repository, "怎么申请系统里没有定义的股票账户", now)
    assert "没有权威来源时明确表示无法确认，并引导玩家发送 /帮助" in claim.system_prompt
```

Also assert that normal social chat still receives persona and stable impression context without being forced into a `/帮助` response.

- [ ] **Step 2: Run prompt tests and verify they fail**

Run: `pytest tests/core/test_repository.py tests/core/test_app.py -k 'prompt_orders_authority or unknown_business_rule' -v`

Expected: FAIL because the prompt still injects one global gameplay guide.

- [ ] **Step 3: Integrate authoritative context into AI claim**

Normalize the current mention once, route/load authority with that exact text, and build the system prompt in this order:

```text
【固定安全边界】
【实时玩家资料】
【实时系统事实】
【准确可用指令】
【规则知识卡】
【稳定玩家印象】
```

The fixed boundary must state that real-time facts override cards, cards override impressions, commands may only be quoted from `【准确可用指令】`, and AI cannot execute. When a section is empty, write `本题无相关权威数据` rather than inventing filler.

- [ ] **Step 4: Apply context-size priorities**

Limit selected card text to 12000 characters total, live facts to 12000, command text to 6000, and stable impressions to 2400. If a block exceeds its limit, truncate cards by lowest priority first and automatic impressions before pinned impressions. Never truncate the fixed safety boundary.

- [ ] **Step 5: Remove the obsolete global gameplay-guide control**

Delete `gameplay_guide` from active Core/admin request and response models, `_with_default_ai_memory_settings`, the settings modal, and JavaScript payload. Leave the old database column untouched so rollback and historical data remain safe.

- [ ] **Step 6: Run AI settings and prompt tests**

Run: `pytest tests/core/test_repository.py tests/core/test_app.py tests/admin/test_app.py tests/ai -v`

Expected: PASS.

- [ ] **Step 7: Commit prompt authority behavior**

```bash
git add src/dzmm_bot/core/repository.py src/dzmm_bot/core/api_models.py src/dzmm_bot/core/app.py src/dzmm_bot/admin/app.py src/dzmm_bot/admin/static/admin.js src/dzmm_bot/admin/templates/index.html tests/core/test_repository.py tests/core/test_app.py tests/admin/test_app.py
git commit -m "feat: ground AI replies in authoritative rules"
```

---

### Task 6: Expose versioned knowledge-card administration APIs

**Files:**
- Modify: `src/dzmm_bot/admin/core_client.py`
- Modify: `src/dzmm_bot/admin/app.py`
- Modify: `tests/admin/test_app.py`

**Interfaces:**
- Produces: `GET/POST /api/ai-knowledge-cards`.
- Produces: `PUT/DELETE /api/ai-knowledge-cards/{card_id}`.
- Consumes: Core CRUD from Task 3.

- [ ] **Step 1: Write failing admin proxy tests**

```python
def test_admin_proxies_versioned_ai_knowledge_card_crud(client, headers):
    listed = client.get("/api/ai-knowledge-cards", headers=headers)
    assert listed.status_code == 200
    created = client.post(
        "/api/ai-knowledge-cards",
        headers={**headers, "Idempotency-Key": "card-create", "If-Match": listed.json()["version"]},
        json={
            "topic": "economy", "title": "金币说明", "keywords": ["金币"],
            "content": "动态金额以实时数据为准。", "enabled": True, "priority": 50,
        },
    )
    assert created.status_code == 200
    assert "version" in created.json()
```

Also test stale `If-Match`, repeated idempotency keys, missing cards, and validation errors passed through without leaking Core tokens.

- [ ] **Step 2: Run admin API tests and verify they fail**

Run: `pytest tests/admin/test_app.py -k 'knowledge_card' -v`

Expected: FAIL because admin routes do not exist.

- [ ] **Step 3: Implement Core client methods and versioned routes**

Use `versioned_configuration_response` for POST/PUT/DELETE with scopes `ai-knowledge-card:create` and `ai-knowledge-card:{card_id}`. GET returns `{"items": [...], "version": ...}`.

- [ ] **Step 4: Run admin API tests**

Run: `pytest tests/admin/test_app.py -k 'knowledge_card' -v`

Expected: PASS.

- [ ] **Step 5: Commit admin API support**

```bash
git add src/dzmm_bot/admin/core_client.py src/dzmm_bot/admin/app.py tests/admin/test_app.py
git commit -m "feat: proxy AI knowledge card management"
```

---

### Task 7: Add the knowledge-card editor to the AI supervisor page

**Files:**
- Modify: `src/dzmm_bot/admin/templates/index.html`
- Modify: `src/dzmm_bot/admin/static/admin.js`
- Modify: `src/dzmm_bot/admin/static/admin.css`
- Modify: `tests/admin/test_app.py`
- Modify: `tests/admin/test_package_data.py`

**Interfaces:**
- Consumes: admin APIs from Task 6.
- Produces: knowledge-card list, create/edit modal, enable toggle, and delete action inside `ai-assistant-view`.

- [ ] **Step 1: Write failing asset assertions**

```python
def test_ai_assistant_page_contains_knowledge_card_editor(client, headers):
    page = client.get("/", headers=headers).text
    script = client.get("/static/admin.js", headers=headers).text
    assert 'id="ai-knowledge-card-list"' in page
    assert 'id="ai-knowledge-card-modal"' in page
    assert 'id="ai-knowledge-card-topic"' in page
    assert 'id="ai-knowledge-card-keywords"' in page
    assert '"/api/ai-knowledge-cards"' in script
```

- [ ] **Step 2: Run UI test and verify it fails**

Run: `pytest tests/admin/test_app.py::test_ai_assistant_page_contains_knowledge_card_editor -v`

Expected: FAIL because the editor is absent.

- [ ] **Step 3: Add the list and modal markup**

Place a “玩法知识卡” panel below the AI settings summary. Render topic, title, keywords, priority, and enabled state. The topic field is a select containing the twelve fixed localized topics. Keywords use one keyword per line. Content uses a 12000-character textarea.

- [ ] **Step 4: Implement list, create, edit, toggle, and delete behavior**

Load cards together with AI settings in `loadAiAssistant`. Sort with the server order. Reuse `runMutation`, `configurationHeaders`, `setResult`, `escapeHtml`, and existing modal close/Escape patterns. Require browser confirmation before delete. After every mutation, use the returned version and reload the list.

- [ ] **Step 5: Run admin tests**

Run: `pytest tests/admin -v`

Expected: PASS.

- [ ] **Step 6: Commit the editor**

```bash
git add src/dzmm_bot/admin/templates/index.html src/dzmm_bot/admin/static/admin.js src/dzmm_bot/admin/static/admin.css tests/admin/test_app.py tests/admin/test_package_data.py
git commit -m "feat: edit AI knowledge cards in admin"
```

---

### Task 8: Verify grounded answers without business mutations

**Files:**
- Modify: `tests/core/test_repository.py`
- Modify: `tests/core/test_app.py`
- Modify: `tests/ai/test_worker.py`
- Modify: `rule.md`

**Interfaces:**
- Verifies the complete authoritative-context flow.

- [ ] **Step 1: Add end-to-end context tests**

Add tests that enqueue and claim visible AI requests for these questions:

1. `我怎么赚金币` includes current currency/reward sources and only enabled commands.
2. `我可以加入哪些部门` includes enabled departments, current department, and exact join/switch syntax.
3. `我怎么晋升` includes current/next rank, live price, and no direct execution promise.
4. `甩锅游戏怎么玩` includes the enabled-state/card/live configuration but never the hidden explosion deadline.
5. `我玩过哪些游戏` includes compact activity totals/results but no stored process dialogue.
6. A disabled command or disabled game is not recommended as available.
7. A made-up business feature has no invented command and includes the `/帮助` fallback instruction.
8. A social message such as `今天好累` still gets persona/impression context without unrelated rule-card bulk.

For each case, inspect the claimed prompt only; do not call the real DeepSeek service.

- [ ] **Step 2: Add a no-mutation worker test**

```python
def test_ai_reply_completion_only_writes_outbound_reply():
    before = snapshot_business_tables(session_factory)
    worker.run_once()
    after = snapshot_business_tables(session_factory)
    assert after == before
    assert outbound_reply_text(session_factory) == "解释和准确指令引导"
```

`snapshot_business_tables` in the test must compare user balances, departments, ranks, inventories, game rows, and random-event rows; exclude AI request status and outbound rows.

- [ ] **Step 3: Run the focused end-to-end tests**

Run: `pytest tests/core/test_repository.py tests/core/test_app.py tests/ai/test_worker.py -k 'authoritative or grounded or no_mutation' -v`

Expected: PASS.

- [ ] **Step 4: Update the rule baseline**

Add an “AI 玩法引导” subsection to `rule.md` stating:

- AI only explains and guides exact enabled commands.
- Dynamic values come from current business configuration.
- Administrators may edit stable rule cards but cannot override live facts or safety boundaries.
- Unknown business rules are not guessed and should fall back to `/帮助`.

- [ ] **Step 5: Run the complete project verification**

Run: `pytest -q`

Expected: all tests PASS.

Run: `git diff --check`

Expected: no output.

- [ ] **Step 6: Commit end-to-end coverage and documentation**

```bash
git add tests/core/test_repository.py tests/core/test_app.py tests/ai/test_worker.py rule.md
git commit -m "test: verify grounded AI gameplay guidance"
```

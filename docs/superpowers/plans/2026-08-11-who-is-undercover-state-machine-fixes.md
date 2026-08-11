# 谁是卧底状态机修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** 修复《谁是卧底》的发牌失败恢复、下一轮退出、投票弃票、规则快照、完整结算和通用指令引导，并保证部署前所有迁移及回归测试通过。

**Architecture:** 保留现有 CoreRepository 事务边界和会话/轮次模型，在轮次上固化规则快照，在会话成员上持久化下一轮退出，在独立表中持久化弃票。命令处理器只负责按当前游戏路由和渲染模板；发牌取消、投票完成判断、超时弃票与结算集中在 repository 中，保证命令触发和后台任务使用同一套状态转换。

**Tech Stack:** Python 3.13、SQLAlchemy 2、Alembic、FastAPI、pytest、PostgreSQL（生产）与 SQLite（单元测试）。

## Global Constraints

- 仅修改谁是卧底及 /跳过、/当前游戏 的必要公共路由，不重构其他玩法。
- 谁是卧底继续限制为 4–8 人，不增加经济奖励或 AI 词牌。
- 报名阶段 /退出 立即生效；发牌开始后 /退出 与 /退出谁是卧底 只影响下一轮。
- 任意一名其他存活玩家可用 /跳过 编号 令尚未投票者本轮弃票；不可跳过自己。
- 投票超时时，所有尚未完成者自动弃票；有效票为零时无人出局并返回自由发言。
- 每轮冻结投票秒数、白板阈值、词组与身份配比；管理端更新只影响后续轮次。
- 发牌失败保留其他报名者，仅失败者重新 /加入；旧身份牌全部作废。
- 默认模板迁移不得覆盖管理员自定义模板。
- 不部署；实现和全量验证完成后等待用户再次确认。

---

### Task 1: 持久化规则快照、下一轮退出与弃票

**Files:**
- Create: migrations/versions/20260811_38_undercover_state_machine_fixes.py
- Modify: src/dzmm_bot/core/schema.py:191-323
- Modify: tests/core/test_repository.py:2127-2160
- Create: tests/deploy/test_undercover_state_machine_migration.py

**Interfaces:**
- Produces: UndercoverGameRecord.vote_seconds_snapshot: int
- Produces: UndercoverGameRecord.whiteboard_win_remaining_snapshot: int
- Produces: UndercoverSessionMemberRecord.leave_after_round: bool
- Produces: UndercoverAbstentionRecord(game_id, round_number, player_user_id, reason, requested_by_user_id, created_at)
- Constraint: UniqueConstraint("game_id", "round_number", "player_user_id")

- [ ] **Step 1: Write failing schema and migration tests**

Seed a historical game/member at revision 37, upgrade to head, and assert snapshot backfill plus the false exit flag:

    def test_undercover_state_machine_migration_backfills_snapshots(
        migrated_postgres_url
    ):
        engine = create_engine(migrated_postgres_url)
        with engine.connect() as connection:
            snapshot = connection.execute(text(
                "SELECT vote_seconds_snapshot, whiteboard_win_remaining_snapshot "
                "FROM undercover_games ORDER BY created_at LIMIT 1"
            )).one()
            leave_after_round = connection.execute(text(
                "SELECT leave_after_round FROM undercover_session_members LIMIT 1"
            )).scalar_one()
        assert snapshot == (120, 3)
        assert leave_after_round is False

Also assert the abstention foreign keys and unique key in model metadata and migrated PostgreSQL.

- [ ] **Step 2: Run tests and verify failure**

    PYTHONPATH="$PWD/src" .venv/bin/pytest -q       tests/core/test_repository.py -k undercover_schema_declares_game_persistence_contract       tests/deploy/test_undercover_state_machine_migration.py

Expected: revision 38, columns and table are missing.

- [ ] **Step 3: Add models and migration**

Define:

    class UndercoverAbstentionRecord(Base):
        __tablename__ = "undercover_abstentions"
        __table_args__ = (
            UniqueConstraint("game_id", "round_number", "player_user_id"),
        )

        id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
        game_id: Mapped[UUID] = mapped_column(
            ForeignKey("undercover_games.id"), nullable=False
        )
        round_number: Mapped[int] = mapped_column(Integer, nullable=False)
        player_user_id: Mapped[UUID] = mapped_column(
            ForeignKey("users.id"), nullable=False
        )
        reason: Mapped[str] = mapped_column(String(24), nullable=False)
        requested_by_user_id: Mapped[UUID | None] = mapped_column(
            ForeignKey("users.id")
        )
        created_at: Mapped[datetime] = mapped_column(
            BeijingDateTime, nullable=False
        )

Migration 20260811_38 adds nullable snapshot columns, backfills from undercover_settings(id=1), makes them non-null, adds leave_after_round with false default, and creates the abstention table. Downgrade drops the table before columns.

- [ ] **Step 4: Verify and commit**

    PYTHONPATH="$PWD/src" .venv/bin/pytest -q       tests/core/test_repository.py -k undercover_schema_declares_game_persistence_contract       tests/deploy/test_undercover_state_machine_migration.py       tests/deploy/test_artifacts.py
    git add migrations/versions/20260811_38_undercover_state_machine_fixes.py       src/dzmm_bot/core/schema.py tests/core/test_repository.py       tests/deploy/test_undercover_state_machine_migration.py
    git commit -m "feat: persist undercover round state"

Expected: selected tests pass and Alembic has one head at 20260811_38.

### Task 2: Repair failed dealing and cancel obsolete cards

**Files:**
- Modify: src/dzmm_bot/core/repository.py:3630-3690,4631-4718,4992-5024,5150-5323
- Modify: tests/core/test_repository.py:2956-3067,3110-3123
- Modify: tests/core/test_group_commands.py:646-710

**Interfaces:**
- Produces: CoreRepository._cancel_undercover_card_outbounds(session, game_id) -> None
- Produces: join_undercover transition delivery_failed -> joined
- Statuses: delivery_failed, rejoined_signup, dealing, ended
- Consumes Task 1 schema fields.

- [ ] **Step 1: Write failing recovery tests**

    failed = repository.record_undercover_card_delivery(
        dealing.game_id, platform_ids[0], False, now
    )
    assert failed.status == "delivery_failed"
    assert repository.undercover_session_summary().player_count == 3

    restarted = repository.join_undercover(platform_ids[0], now)
    assert restarted.status == "dealing"
    assert restarted.player_count == 4
    assert restarted.game_id != dealing.game_id

Also assert all old pending/leased cards become failed, a fifth player never expands a four-person target, participant/admin end during dealing leaves no claimable undercover_card, and late receipts do not reopen discarded/ended rounds.

- [ ] **Step 2: Run tests and verify failure**

    PYTHONPATH="$PWD/src" .venv/bin/pytest -q tests/core/test_repository.py       -k "undercover and (delivery or dealing or obsolete or late)"

Expected: current code leaves four joined members, rejects rejoin, or still leases old cards.

- [ ] **Step 3: Implement cancellation and recovery**

_cancel_undercover_card_outbounds updates only linked card messages in pending/leased state:

    session.execute(
        update(OutboundRecord)
        .where(
            OutboundRecord.id.in_(card_ids),
            OutboundRecord.status.in_(("pending", "leased")),
        )
        .values(
            status="failed",
            lease_worker_id=None,
            lease_token=None,
            lease_expires_at=None,
        )
    )

On failure, discard the game, cancel old cards, mark only the failed member delivery_failed, and return to signup. Rejoining changes that member back to joined. Start only when joined count equals target. Reuse cancellation for participant end and admin force-end.

- [ ] **Step 4: Verify and commit**

    PYTHONPATH="$PWD/src" .venv/bin/pytest -q       tests/core/test_repository.py -k undercover       tests/core/test_group_commands.py -k undercover
    git add src/dzmm_bot/core/repository.py       tests/core/test_repository.py tests/core/test_group_commands.py
    git commit -m "fix: recover failed undercover dealing"

### Task 3: Defer exits until the next round

**Files:**
- Modify: src/dzmm_bot/core/repository.py:4861-4910,4992-5070,5362-5454
- Modify: src/dzmm_bot/core/commands.py:1225-1252
- Modify: tests/core/test_repository.py:3080-3255
- Modify: tests/core/test_group_commands.py:646-735

**Interfaces:**
- Statuses: left_signup, leave_after_round, left_waiting_continue, cannot_leave
- Extends UndercoverGameResult with actor_seat, actor_display_name, next_round_exit_labels
- Produces: _apply_undercover_next_round_exits(session, session_id, now) -> tuple[str, ...]

- [ ] **Step 1: Write failing lifecycle tests**

    result = repository.leave_undercover(platform_ids[0], now)
    assert result.status == "leave_after_round"
    assert repository.undercover_session_summary().state == "speaking"
    assert active_player.state == "alive"
    assert session_member.leave_after_round is True

Add continuation coverage proving flagged players are absent from the next game, candidates fill seats in queue order, signup exit is immediate, and awaiting-continue exit is immediate.

- [ ] **Step 2: Run tests and verify failure**

    PYTHONPATH="$PWD/src" .venv/bin/pytest -q tests/core/test_repository.py       -k "undercover and (exit or leave or continuation)"

Expected: current code marks the active player exited and may settle immediately.

- [ ] **Step 3: Implement state-specific exit**

    if session_record.state == "signup":
        member.state = "left"
        member.left_at = now
        return UndercoverGameResult("left_signup", session_id=session_record.id)
    if session_record.state == "awaiting_continue":
        member.state = "left"
        member.left_at = now
        return UndercoverGameResult(
            "left_waiting_continue", session_id=session_record.id
        )
    member.leave_after_round = True
    return UndercoverGameResult(
        "leave_after_round",
        session_id=session_record.id,
        game_id=game.id,
        actor_seat=player.seat_number,
        actor_display_name=user.display_name,
    )

Apply flags only on settled games, capture labels for final output, and never call winner evaluation from /退出.

- [ ] **Step 4: Verify and commit**

    PYTHONPATH="$PWD/src" .venv/bin/pytest -q       tests/core/test_repository.py -k undercover       tests/core/test_group_commands.py -k "undercover or generic_exit"
    git add src/dzmm_bot/core/repository.py src/dzmm_bot/core/commands.py       tests/core/test_repository.py tests/core/test_group_commands.py
    git commit -m "fix: defer undercover exits to next round"

### Task 4: Add vote progress and abstention

**Files:**
- Modify: src/dzmm_bot/core/repository.py:4720-4798,4912-4990,5349-5454
- Modify: src/dzmm_bot/core/commands.py:70-90,1177-1223
- Modify: src/dzmm_bot/core/reply_templates.py:187-204
- Modify: tests/core/test_repository.py:3026-3108
- Modify: tests/core/test_group_commands.py:646-710

**Interfaces:**
- Produces: skip_undercover_vote(platform_id, target_seat, now) -> UndercoverGameResult
- Produces: _undercover_vote_progress(session, game) -> tuple[int, int, int]
- Produces: _complete_undercover_vote_if_ready(session, session_record, game, now) -> UndercoverGameResult
- Extends UndercoverGameResult with actor seat/name, vote_count, abstention_count, completed_count, eligible_count and abstained_labels.
- Statuses: vote_recorded, abstained, duplicate_vote, already_abstained, cannot_skip_self, invalid_skip_target, cannot_skip, tied, eliminated, settled, vote_expired.

- [ ] **Step 1: Write failing vote tests**

    first = repository.cast_undercover_vote(platform_ids[0], target_seat, now)
    assert (
        first.vote_count,
        first.abstention_count,
        first.completed_count,
        first.eligible_count,
    ) == (1, 0, 1, 4)

    skipped = repository.skip_undercover_vote(platform_ids[1], 3, now)
    assert skipped.status == "abstained"
    assert (
        skipped.vote_count,
        skipped.abstention_count,
        skipped.completed_count,
    ) == (1, 1, 2)

Cover self-skip, skip-after-vote, vote-after-skip, early completion, timeout-created abstentions, partial votes at timeout and all players abstaining.

- [ ] **Step 2: Run tests and verify failure**

    PYTHONPATH="$PWD/src" .venv/bin/pytest -q tests/core/test_repository.py       -k "undercover and (vote or abstain or skip)"

Expected: method/fields are absent and timeout does not persist abstentions.

- [ ] **Step 3: Implement voting**

Use game.vote_seconds_snapshot for explicit and implicit starts. Votes and abstentions are application-level mutually exclusive and protected by row locks plus unique constraints. One other living player can skip an unfinished living target; self-skip is rejected.

After every vote/skip, settle when votes + abstentions equals living count. At deadline, insert timeout records for every unfinished living player, announce them, then call the same completion function. Zero valid votes returns to speaking without elimination.

- [ ] **Step 4: Verify and commit**

    PYTHONPATH="$PWD/src" .venv/bin/pytest -q       tests/core/test_repository.py -k undercover       tests/core/test_group_commands.py -k "undercover or skip"
    git add src/dzmm_bot/core/repository.py src/dzmm_bot/core/commands.py       src/dzmm_bot/core/reply_templates.py tests/core/test_repository.py       tests/core/test_group_commands.py
    git commit -m "feat: track undercover vote completion"

Expected: vote replies show seat/name and 1/4-style progress without revealing targets; number-bomb skip remains green.

### Task 5: Publish complete settlement and freeze winner rules

**Files:**
- Modify: src/dzmm_bot/core/repository.py:4961-4990,5362-5498
- Modify: src/dzmm_bot/core/commands.py:1196-1275
- Modify: src/dzmm_bot/core/reply_templates.py:194-204
- Modify: tests/core/test_repository.py:3080-3178
- Modify: tests/core/test_group_commands.py:646-710

**Interfaces:**
- Produces: UndercoverPlayerReveal(seat_number, display_name, role, state)
- Extends UndercoverGameResult with civilian_word, undercover_word, player_reveals, manual_abstention_labels, timeout_abstention_labels and next_round_exit_labels.
- Produces: undercover_settlement_template_values(result) -> dict[str, object]

- [ ] **Step 1: Write failing settlement tests**

Change live settings after dealing, finish the original game, and assert the original snapshot decides the winner. Assert command-triggered and timeout-triggered final replies include both words, every player seat/name/role, winner, eliminated player, abstentions and next-round exits.

    assert result.winner == expected_from_original_threshold
    assert {item.seat_number for item in result.player_reveals} == {1, 2, 3, 4}
    assert result.civilian_word == "咖啡"
    assert result.undercover_word == "奶茶"

- [ ] **Step 2: Run tests and verify failure**

    PYTHONPATH="$PWD/src" .venv/bin/pytest -q       tests/core/test_repository.py -k "undercover and (settle or winner or snapshot)"       tests/core/test_group_commands.py -k undercover_group_commands

Expected: winner uses live settings and final reply lacks full reveals.

- [ ] **Step 3: Implement a shared complete result**

Make _undercover_winner accept the game record and read game.whiteboard_win_remaining_snapshot. On settlement, collect all reveals and abstentions before applying deferred exits. Use undercover_settlement_template_values from both command replies and background vote-timeout messages. Never disclose all identities for a nonterminal elimination or tie.

- [ ] **Step 4: Verify and commit**

    PYTHONPATH="$PWD/src" .venv/bin/pytest -q       tests/core/test_repository.py -k undercover       tests/core/test_group_commands.py -k undercover
    git add src/dzmm_bot/core/repository.py src/dzmm_bot/core/commands.py       src/dzmm_bot/core/reply_templates.py tests/core/test_repository.py       tests/core/test_group_commands.py
    git commit -m "feat: disclose complete undercover settlements"

Expected: complete settlement passes and AI activity win/loss/ended facts remain unchanged.

### Task 6: Correct routing, current-game guidance and templates

**Files:**
- Modify: src/dzmm_bot/core/commands.py:60-90,158-220
- Modify: src/dzmm_bot/core/repository.py:3331-3473
- Modify: src/dzmm_bot/core/reply_templates.py:180-204
- Modify: migrations/versions/20260811_38_undercover_state_machine_fixes.py
- Modify: tests/core/test_group_commands.py:240-410,646-735
- Modify: tests/core/test_repository.py:1035-1060,3575-3600
- Modify: tests/deploy/test_undercover_state_machine_migration.py

**Interfaces:**
- Consumes active_gameplay_summary and skip_undercover_vote.
- Produces state-specific ActiveGameplaySummary.available_commands.
- Produces template scenarios delivery_failed, leave_after_round, vote_recorded, manual_abstention, timeout_abstention and settled.

- [ ] **Step 1: Write failing routing and template-preservation tests**

Assert /跳过 2 4 reaches number bomb, /跳过 2 reaches undercover during voting, and no matching game returns unavailable. Assert outsider/current/candidate command lists for signup, dealing/speaking, voting and awaiting-continue. Seed an unchanged default plus a customized template before migration and assert only the unchanged default changes.

- [ ] **Step 2: Run tests and verify failure**

    PYTHONPATH="$PWD/src" .venv/bin/pytest -q       tests/core/test_group_commands.py -k "skip or current_game or undercover"       tests/deploy/test_undercover_state_machine_migration.py

Expected: /跳过 always routes to number bomb and summaries omit valid undercover commands.

- [ ] **Step 3: Route by current game**

    if command == "/跳过":
        summary = self._repository.active_gameplay_summary(
            message.sender_platform_id, received_at
        )
        if summary.game_type == "number_bomb":
            return self._number_bomb_skip(
                message.sender_platform_id, content, received_at
            )
        if summary.game_type == "undercover":
            return self._undercover_skip(
                message.sender_platform_id, content, received_at
            )
        if summary.game_type == "conflict":
            return self._reply("/当前游戏", "conflict", received_at)
        return self._reply("/跳过", "no_current_game", received_at)

Update available commands exactly as approved, including /加入 for outsiders during active undercover and /跳过 编号 during voting.

- [ ] **Step 4: Add defaults without overwriting custom text**

Register exact variables in reply_templates.py. Migration upgrade updates old rows only when command, scenario and exact old template match; new scenarios are inserted only when absent. Downgrade reverses exact new defaults and preserves customized rows.

- [ ] **Step 5: Verify and commit**

    PYTHONPATH="$PWD/src" .venv/bin/pytest -q       tests/core/test_group_commands.py       tests/core/test_repository.py -k "undercover or active_gameplay_summary"       tests/core/test_app.py -k "game_management or command"       tests/admin/test_app.py -k "command or template"       tests/deploy/test_undercover_state_machine_migration.py
    git add src/dzmm_bot/core/commands.py src/dzmm_bot/core/repository.py       src/dzmm_bot/core/reply_templates.py       migrations/versions/20260811_38_undercover_state_machine_fixes.py       tests/core/test_group_commands.py tests/core/test_repository.py       tests/deploy/test_undercover_state_machine_migration.py
    git commit -m "fix: align undercover commands and templates"

### Task 7: Full regression and release readiness

**Files:**
- Modify only when a regression is directly caused by Tasks 1–6. Do not clean unrelated code.

**Interfaces:**
- Consumes all prior task outputs.
- Produces a verified feature branch; does not deploy.

- [ ] **Step 1: Verify migrations**

    PYTHONPATH="$PWD/src" .venv/bin/pytest -q       tests/deploy/test_undercover_state_machine_migration.py       tests/deploy/test_artifacts.py

Expected: upgrade/downgrade tests pass and Alembic has one head.

- [ ] **Step 2: Run focused gameplay regression**

    PYTHONPATH="$PWD/src" .venv/bin/pytest -q       tests/core/test_repository.py -k "undercover or number_bomb or multiplayer"       tests/core/test_group_commands.py -k "undercover or number_bomb or skip or current_game"

Expected: all selected gameplay tests pass.

- [ ] **Step 3: Run complete suite**

    PYTHONPATH="$PWD/src" .venv/bin/pytest -q

Expected: no failures; existing environment-dependent skips and known deprecation warnings are allowed.

- [ ] **Step 4: Inspect final state**

    git diff --check main...HEAD
    git status --short --branch
    git log --oneline main..HEAD

Expected: only planned files changed; .env and unrelated untracked files are not staged.

- [ ] **Step 5: Report readiness**

Report migration head, focused/full test counts, commits, warnings and production verification steps. Wait for explicit deployment confirmation.

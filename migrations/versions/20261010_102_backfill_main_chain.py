"""Backfill the main-chain schema the server feature-test chain never ran.

服务器迁移链从 birthday_blessing(20260917_76, down=20260915_75) 直接续
liar_dice(20261002_77)，从未跑过 origin/main 的 8 个迁移：

- 20260915_76 company_lottery_economy_and_sale_window（数据迁移）
- 20260917_77 random_event_votes（7 列 + 3 表）
- 20260917_78 random_event_vote_command_gate（数据迁移）
- 20260917_79 random_event_ad_slots（2 表）
- 20260917_80 random_event_ad_schedule_reservations（列/FK/数据）
- 20260918_81 black_history（1 表）
- 20260919_82 black_history_delete_drafts（1 表）
- 20260930_83 shop_scratch_reward_ranges（2 列 + 数据）

本迁移按"最终形态"补齐全部结构与数据，所有操作幂等，可在任意中间状态重跑。
"""

from collections.abc import Sequence
from datetime import timedelta

from alembic import op
import sqlalchemy as sa


revision: str = "20261010_102"
down_revision: str | None = "20261010_101"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    _lottery_economy()
    _random_event_vote_columns()
    _random_event_vote_tables()
    _vote_command_gate()
    _random_event_ad_slots()
    _black_history_entries()
    _black_history_delete_drafts()
    _scratch_reward_ranges()


def downgrade() -> None:
    pass


def _columns(table: str) -> set[str]:
    return {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns(table)
    }


def _add_columns_if_missing(table: str, columns: list[sa.Column]) -> None:
    if not sa.inspect(op.get_bind()).has_table(table):
        return
    existing = _columns(table)
    for column in columns:
        if column.name not in existing:
            op.add_column(table, column)


def _lottery_economy() -> None:
    """main 20260915_76：彩票经济数值 + 未开售票轮次提前关闭。"""
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("company_lottery_settings"):
        return
    settings = sa.table(
        "company_lottery_settings",
        sa.column("id", sa.Integer()),
        sa.column("red_pool", sa.Integer()),
        sa.column("red_count", sa.Integer()),
        sa.column("blue_pool", sa.Integer()),
        sa.column("ticket_price", sa.Integer()),
        sa.column("head_prize", sa.Integer()),
        sa.column("second_prize", sa.Integer()),
        sa.column("third_prize", sa.Integer()),
        sa.column("fourth_prize", sa.Integer()),
        sa.column("fifth_prize", sa.Integer()),
        sa.column("pool_ceiling", sa.Integer()),
        sa.column("per_person_cap", sa.Integer()),
        sa.column("max_tickets_per_day", sa.Integer()),
        sa.column("max_tickets_per_round", sa.Integer()),
        sa.column("close_offset_minutes", sa.Integer()),
    )
    values = {
        "head_prize": 500,
        "second_prize": 120,
        "third_prize": 20,
        "fourth_prize": 5,
        "fifth_prize": 1,
        "pool_ceiling": 1000,
        "per_person_cap": 500,
        "close_offset_minutes": 30,
    }
    bind.execute(settings.update().where(settings.c.id == 1).values(**values))
    current = bind.execute(
        sa.select(settings).where(settings.c.id == 1)
    ).mappings().first()
    if current is None:
        return

    snapshot = {
        "red_pool": current["red_pool"],
        "red_count": current["red_count"],
        "blue_pool": current["blue_pool"],
        "ticket_price": current["ticket_price"],
        "head_prize": current["head_prize"],
        "second_prize": current["second_prize"],
        "third_prize": current["third_prize"],
        "fourth_prize": current["fourth_prize"],
        "fifth_prize": current["fifth_prize"],
        "pool_ceiling": current["pool_ceiling"],
        "per_person_cap": current["per_person_cap"],
        "max_tickets_per_day": current["max_tickets_per_day"],
        "max_tickets_per_round": current["max_tickets_per_round"],
    }
    rounds = sa.table(
        "company_lottery_rounds",
        sa.column("id", sa.Uuid()),
        sa.column("state", sa.String()),
        sa.column("tickets_sold", sa.Integer()),
        sa.column("close_at", sa.DateTime(timezone=True)),
        sa.column("draw_at", sa.DateTime(timezone=True)),
        sa.column("rules_snapshot", sa.JSON()),
    )
    rows = bind.execute(
        sa.select(rounds.c.id, rounds.c.draw_at).where(
            rounds.c.state == "open", rounds.c.tickets_sold == 0
        )
    ).mappings()
    for row in rows:
        bind.execute(
            rounds.update()
            .where(rounds.c.id == row["id"])
            .values(
                close_at=row["draw_at"] - timedelta(minutes=30),
                rules_snapshot=snapshot,
            )
        )


VOTE_SETTINGS_COLUMNS = (
    sa.Column(
        "vote_enabled", sa.Boolean(), nullable=False, server_default=sa.false()
    ),
    sa.Column(
        "vote_close_offset_minutes",
        sa.Integer(),
        nullable=False,
        server_default="10",
    ),
    sa.Column(
        "vote_broadcast_interval_minutes",
        sa.Integer(),
        nullable=False,
        server_default="30",
    ),
    sa.Column(
        "vote_random_candidates", sa.Integer(), nullable=False, server_default="3"
    ),
    sa.Column("vote_ad_slot_limit", sa.Integer(), nullable=False, server_default="1"),
    sa.Column(
        "vote_fallback_minutes", sa.Integer(), nullable=False, server_default="30"
    ),
    sa.Column(
        "vote_allow_change", sa.Boolean(), nullable=False, server_default=sa.true()
    ),
)


def _random_event_vote_columns() -> None:
    """main 20260917_77 前半：设置表投票列。"""
    _add_columns_if_missing("random_event_settings", list(VOTE_SETTINGS_COLUMNS))


def _random_event_vote_tables() -> None:
    """main 20260917_77 后半：投票三表。"""
    if not sa.inspect(op.get_bind()).has_table("random_event_polls"):
        op.create_table(
            "random_event_polls",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("target_schedule_id", sa.Uuid(), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("closes_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("winner_candidate_id", sa.Uuid(), nullable=True),
            sa.Column("announced_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_tally_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("fallback_reason", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["target_schedule_id"], ["random_event_schedules.id"]
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("target_schedule_id"),
        )
        op.create_index(
            "ix_random_event_polls_status_close",
            "random_event_polls",
            ["status", "closes_at"],
        )
    if not sa.inspect(op.get_bind()).has_table("random_event_poll_candidates"):
        op.create_table(
            "random_event_poll_candidates",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("poll_id", sa.Uuid(), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.Column("source", sa.String(length=16), nullable=False),
            sa.Column("scene_id", sa.Uuid(), nullable=True),
            sa.Column("template_id", sa.Uuid(), nullable=True),
            sa.Column("scene_name", sa.String(length=64), nullable=True),
            sa.Column("event_name", sa.String(length=64), nullable=True),
            sa.Column("seat_summary", sa.String(length=255), nullable=True),
            sa.Column("author_name", sa.String(length=64), nullable=True),
            sa.Column("reward", sa.Integer(), nullable=True),
            sa.Column("target_rounds", sa.Integer(), nullable=True),
            sa.Column("vacant", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["poll_id"], ["random_event_polls.id"]),
            sa.ForeignKeyConstraint(["scene_id"], ["random_event_scenes.id"]),
            sa.ForeignKeyConstraint(
                ["template_id"], ["random_event_scene_openings.id"]
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("poll_id", "position"),
            sa.UniqueConstraint("poll_id", "scene_id"),
        )
    if not sa.inspect(op.get_bind()).has_table("random_event_poll_votes"):
        op.create_table(
            "random_event_poll_votes",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("poll_id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("candidate_id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["poll_id"], ["random_event_polls.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(
                ["candidate_id"], ["random_event_poll_candidates.id"]
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("poll_id", "user_id"),
        )


def _vote_command_gate() -> None:
    """main 20260917_78：把投票指令追加进放行清单（幂等）。"""
    vote_commands = ("/事件投票", "/事件投票情况")
    allow_columns = ("signup_allowed_commands", "in_progress_allowed_commands")
    if not sa.inspect(op.get_bind()).has_table("random_event_settings"):
        return
    settings = sa.table(
        "random_event_settings",
        sa.column("id", sa.Integer()),
        sa.column("signup_allowed_commands", sa.JSON()),
        sa.column("in_progress_allowed_commands", sa.JSON()),
    )
    bind = op.get_bind()
    for row in bind.execute(sa.select(settings)).mappings():
        updates = {}
        for column in allow_columns:
            values = list(row[column] or [])
            changed = False
            for command in vote_commands:
                if command not in values:
                    values.append(command)
                    changed = True
            if changed:
                updates[column] = values
        if updates:
            bind.execute(
                sa.update(settings).where(settings.c.id == row["id"]).values(updates)
            )


def _random_event_ad_slots() -> None:
    """main 20260917_79 + 20260917_80：广告卡两表（最终形态）与数据。"""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("random_event_ad_slots"):
        op.create_table(
            "random_event_ad_slots",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("scene_id", sa.Uuid(), nullable=False),
            sa.Column("item_id", sa.Uuid(), nullable=False),
            sa.Column("schedule_id", sa.Uuid(), nullable=False),
            sa.Column("poll_id", sa.Uuid(), nullable=True),
            sa.Column("candidate_id", sa.Uuid(), nullable=True),
            sa.Column(
                "status",
                sa.String(length=16),
                nullable=False,
                server_default="consumed",
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["scene_id"], ["random_event_scenes.id"]),
            sa.ForeignKeyConstraint(["item_id"], ["items.id"]),
            sa.ForeignKeyConstraint(["poll_id"], ["random_event_polls.id"]),
            sa.ForeignKeyConstraint(
                ["candidate_id"], ["random_event_poll_candidates.id"]
            ),
            sa.ForeignKeyConstraint(
                ["schedule_id"],
                ["random_event_schedules.id"],
                name="fk_random_event_ad_slots_schedule_id",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("poll_id", "user_id"),
        )
        op.create_index(
            "ix_random_event_ad_slots_poll", "random_event_ad_slots", ["poll_id"]
        )
    if not inspector.has_table("random_event_ad_slot_drafts"):
        op.create_table(
            "random_event_ad_slot_drafts",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("item_id", sa.Uuid(), nullable=False),
            sa.Column("schedule_id", sa.Uuid(), nullable=True),
            sa.Column("poll_id", sa.Uuid(), nullable=True),
            sa.Column("group_chat_id", sa.Uuid(), nullable=False),
            sa.Column("current_step", sa.String(length=32), nullable=False),
            sa.Column("scene_id", sa.Uuid(), nullable=True),
            sa.Column("work_page", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["item_id"], ["items.id"]),
            sa.ForeignKeyConstraint(["poll_id"], ["random_event_polls.id"]),
            sa.ForeignKeyConstraint(["scene_id"], ["random_event_scenes.id"]),
            sa.ForeignKeyConstraint(
                ["schedule_id"],
                ["random_event_schedules.id"],
                name="fk_random_event_ad_slot_drafts_schedule_id",
            ),
            sa.ForeignKeyConstraint(
                ["group_chat_id"],
                ["group_chats.id"],
                name="fk_random_event_ad_slot_drafts_group_chat_id",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id"),
        )
    op.execute("UPDATE random_event_settings SET vote_ad_slot_limit = 3")


def _black_history_entries() -> None:
    """main 20260918_81：员工小黑历史表。"""
    if sa.inspect(op.get_bind()).has_table("black_history_entries"):
        return
    op.create_table(
        "black_history_entries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("subject_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("recorder_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("group_chat_id", sa.Uuid(), sa.ForeignKey("group_chats.id"), nullable=False),
        sa.Column("source_platform_message_id", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=16), nullable=False),
        sa.Column("text_content", sa.Text()),
        sa.Column("image_url", sa.Text()),
        sa.Column("image_alt", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("group_chat_id", "source_platform_message_id"),
    )
    op.create_index(
        "ix_black_history_entries_subject_id",
        "black_history_entries",
        ["subject_user_id", "id"],
    )


def _black_history_delete_drafts() -> None:
    """main 20260919_82：小黑历史删除分页草稿表。"""
    if sa.inspect(op.get_bind()).has_table("black_history_delete_drafts"):
        return
    op.create_table(
        "black_history_delete_drafts",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("page", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def _scratch_reward_ranges() -> None:
    """main 20260930_83：刮刮卡奖励区间列与默认值。"""
    _add_columns_if_missing(
        "items",
        [
            sa.Column("scratch_reward_min", sa.Integer(), nullable=True),
            sa.Column("scratch_reward_max", sa.Integer(), nullable=True),
        ],
    )
    for key, minimum, maximum in (
        ("scratch_a", 1, 10),
        ("scratch_b", 5, 15),
        ("scratch_c", 10, 30),
    ):
        op.execute(
            sa.text(
                "UPDATE items SET scratch_reward_min = :minimum, "
                "scratch_reward_max = :maximum WHERE system_key = :key"
            ).bindparams(key=key, minimum=minimum, maximum=maximum)
        )

"""Reserve event advertisement cards against future schedules."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260917_80"
down_revision: str | None = "20260917_79"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "random_event_ad_slots",
        sa.Column("schedule_id", sa.Uuid(), nullable=True),
    )
    op.execute(
        "UPDATE random_event_ad_slots AS slot "
        "SET schedule_id = poll.target_schedule_id "
        "FROM random_event_polls AS poll WHERE slot.poll_id = poll.id"
    )
    _alter_slots_for_upgrade()

    op.add_column(
        "random_event_ad_slot_drafts",
        sa.Column("schedule_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "random_event_ad_slot_drafts",
        sa.Column("group_chat_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "random_event_ad_slot_drafts",
        sa.Column("work_page", sa.Integer(), nullable=False, server_default="1"),
    )
    op.execute("DELETE FROM random_event_ad_slot_drafts")
    _alter_drafts_for_upgrade()
    op.execute("UPDATE random_event_settings SET vote_ad_slot_limit = 3")


def downgrade() -> None:
    op.execute("DELETE FROM random_event_ad_slot_drafts")
    op.execute("DELETE FROM random_event_ad_slots WHERE poll_id IS NULL")
    _alter_drafts_for_downgrade()
    _alter_slots_for_downgrade()
    op.execute("UPDATE random_event_settings SET vote_ad_slot_limit = 1")


def _alter_slots_for_upgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("random_event_ad_slots") as batch:
            batch.alter_column("schedule_id", existing_type=sa.Uuid(), nullable=False)
            batch.alter_column("poll_id", existing_type=sa.Uuid(), nullable=True)
            batch.create_foreign_key(
                "fk_random_event_ad_slots_schedule_id",
                "random_event_schedules",
                ["schedule_id"],
                ["id"],
            )
        return
    op.alter_column("random_event_ad_slots", "schedule_id", nullable=False)
    op.alter_column("random_event_ad_slots", "poll_id", nullable=True)
    op.create_foreign_key(
        "fk_random_event_ad_slots_schedule_id",
        "random_event_ad_slots",
        "random_event_schedules",
        ["schedule_id"],
        ["id"],
    )


def _alter_drafts_for_upgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("random_event_ad_slot_drafts") as batch:
            batch.alter_column("poll_id", existing_type=sa.Uuid(), nullable=True)
            batch.alter_column("group_chat_id", existing_type=sa.Uuid(), nullable=False)
            batch.create_foreign_key(
                "fk_random_event_ad_slot_drafts_schedule_id",
                "random_event_schedules",
                ["schedule_id"],
                ["id"],
            )
            batch.create_foreign_key(
                "fk_random_event_ad_slot_drafts_group_chat_id",
                "group_chats",
                ["group_chat_id"],
                ["id"],
            )
        return
    op.alter_column("random_event_ad_slot_drafts", "poll_id", nullable=True)
    op.alter_column("random_event_ad_slot_drafts", "group_chat_id", nullable=False)
    op.create_foreign_key(
        "fk_random_event_ad_slot_drafts_schedule_id",
        "random_event_ad_slot_drafts",
        "random_event_schedules",
        ["schedule_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_random_event_ad_slot_drafts_group_chat_id",
        "random_event_ad_slot_drafts",
        "group_chats",
        ["group_chat_id"],
        ["id"],
    )


def _alter_drafts_for_downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("random_event_ad_slot_drafts") as batch:
            batch.drop_constraint(
                "fk_random_event_ad_slot_drafts_group_chat_id", type_="foreignkey"
            )
            batch.drop_constraint(
                "fk_random_event_ad_slot_drafts_schedule_id", type_="foreignkey"
            )
            batch.drop_column("work_page")
            batch.drop_column("schedule_id")
            batch.drop_column("group_chat_id")
            batch.alter_column("poll_id", existing_type=sa.Uuid(), nullable=False)
        return
    op.drop_constraint(
        "fk_random_event_ad_slot_drafts_group_chat_id",
        "random_event_ad_slot_drafts",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_random_event_ad_slot_drafts_schedule_id",
        "random_event_ad_slot_drafts",
        type_="foreignkey",
    )
    op.drop_column("random_event_ad_slot_drafts", "work_page")
    op.drop_column("random_event_ad_slot_drafts", "schedule_id")
    op.drop_column("random_event_ad_slot_drafts", "group_chat_id")
    op.alter_column("random_event_ad_slot_drafts", "poll_id", nullable=False)


def _alter_slots_for_downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("random_event_ad_slots") as batch:
            batch.drop_constraint(
                "fk_random_event_ad_slots_schedule_id", type_="foreignkey"
            )
            batch.drop_column("schedule_id")
            batch.alter_column("poll_id", existing_type=sa.Uuid(), nullable=False)
        return
    op.drop_constraint(
        "fk_random_event_ad_slots_schedule_id",
        "random_event_ad_slots",
        type_="foreignkey",
    )
    op.drop_column("random_event_ad_slots", "schedule_id")
    op.alter_column("random_event_ad_slots", "poll_id", nullable=False)

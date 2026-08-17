"""Add random event tipping and unique employee names."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260817_44"
down_revision: str | None = "20260815_43"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _unique_employee_names() -> None:
    connection = op.get_bind()
    while True:
        duplicate_names = list(
            connection.execute(
                sa.text(
                    "SELECT display_name FROM users "
                    "GROUP BY display_name HAVING COUNT(*) > 1 "
                    "ORDER BY display_name"
                )
            ).scalars()
        )
        if not duplicate_names:
            return
        for display_name in duplicate_names:
            employees = connection.execute(
                sa.text(
                    "SELECT id, employee_number FROM users "
                    "WHERE display_name = :display_name "
                    "ORDER BY employee_number, id"
                ),
                {"display_name": display_name},
            ).all()
            for employee_id, employee_number in employees:
                suffix = f"#{employee_number:04d}"
                unique_name = f"{display_name[:64 - len(suffix)]}{suffix}"
                connection.execute(
                    sa.text(
                        "UPDATE users SET display_name = :display_name "
                        "WHERE id = :employee_id"
                    ),
                    {"display_name": unique_name, "employee_id": employee_id},
                )


def upgrade() -> None:
    with op.batch_alter_table("random_event_settings") as batch_op:
        batch_op.add_column(
            sa.Column(
                "tipping_duration_seconds",
                sa.Integer(),
                nullable=False,
                server_default="120",
            )
        )
    with op.batch_alter_table("random_events") as batch_op:
        batch_op.add_column(
            sa.Column("tipping_started_at", sa.DateTime(timezone=True))
        )
        batch_op.add_column(
            sa.Column("tipping_deadline", sa.DateTime(timezone=True))
        )

    op.create_table(
        "random_event_tips",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("sender_user_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_user_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("inbound_message_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["random_events.id"]),
        sa.ForeignKeyConstraint(["sender_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["recipient_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["inbound_message_id"], ["inbound_messages.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("inbound_message_id"),
    )
    op.create_index(
        "ix_random_event_tips_event_id", "random_event_tips", ["event_id"]
    )

    op.drop_index("ux_random_events_one_active_group", table_name="random_events")
    op.create_index(
        "ux_random_events_one_active_group",
        "random_events",
        ["group_key"],
        unique=True,
        postgresql_where=sa.text("state IN ('signup', 'in_progress', 'tipping')"),
        sqlite_where=sa.text("state IN ('signup', 'in_progress', 'tipping')"),
    )

    _unique_employee_names()
    op.create_index(
        "ux_users_display_name", "users", ["display_name"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ux_users_display_name", table_name="users")
    op.drop_index("ux_random_events_one_active_group", table_name="random_events")
    op.create_index(
        "ux_random_events_one_active_group",
        "random_events",
        ["group_key"],
        unique=True,
        postgresql_where=sa.text("state IN ('signup', 'in_progress')"),
        sqlite_where=sa.text("state IN ('signup', 'in_progress')"),
    )
    op.drop_index("ix_random_event_tips_event_id", table_name="random_event_tips")
    op.drop_table("random_event_tips")
    with op.batch_alter_table("random_events") as batch_op:
        batch_op.drop_column("tipping_deadline")
        batch_op.drop_column("tipping_started_at")
    with op.batch_alter_table("random_event_settings") as batch_op:
        batch_op.drop_column("tipping_duration_seconds")

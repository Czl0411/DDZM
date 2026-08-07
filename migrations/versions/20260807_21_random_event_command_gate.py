"""Configure the random-event command gate."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260807_21"
down_revision: str | None = "20260806_20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("random_event_settings") as batch:
        batch.add_column(
            sa.Column(
                "signup_allowed_commands",
                sa.JSON(),
                nullable=False,
                server_default='["/加入", "/退出"]',
            )
        )
        batch.add_column(
            sa.Column(
                "in_progress_allowed_commands",
                sa.JSON(),
                nullable=False,
                server_default='["/退出"]',
            )
        )
        batch.add_column(
            sa.Column(
                "blocked_message",
                sa.Text(),
                nullable=False,
                server_default="当前有随机事件发生，监事不会处理。",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("random_event_settings") as batch:
        batch.drop_column("blocked_message")
        batch.drop_column("in_progress_allowed_commands")
        batch.drop_column("signup_allowed_commands")

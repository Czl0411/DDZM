"""Add profile images and profile versions."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260813_41"
down_revision: str | None = "20260812_40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("profile_image_url", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "profile_version",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
    with op.batch_alter_table("outbound_messages") as batch_op:
        batch_op.add_column(
            sa.Column(
                "content_type", sa.String(length=16), nullable=False,
                server_default="text",
            )
        )
        batch_op.add_column(sa.Column("image_url", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("image_alt", sa.String(length=512), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("outbound_messages") as batch_op:
        batch_op.drop_column("image_alt")
        batch_op.drop_column("image_url")
        batch_op.drop_column("content_type")
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("profile_version")
        batch_op.drop_column("profile_image_url")

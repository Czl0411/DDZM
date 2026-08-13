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
    op.create_table(
        "profile_image_uploads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("temp_path", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=64), nullable=False),
        sa.Column("expected_profile_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("lease_worker_id", sa.String(length=255), nullable=True),
        sa.Column("lease_token", sa.Uuid(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("result_url", sa.Text(), nullable=True),
        sa.Column("failure_summary", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_profile_image_uploads_claim",
        "profile_image_uploads",
        ["status", "lease_expires_at", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_profile_image_uploads_claim", table_name="profile_image_uploads"
    )
    op.drop_table("profile_image_uploads")
    with op.batch_alter_table("outbound_messages") as batch_op:
        batch_op.drop_column("image_alt")
        batch_op.drop_column("image_url")
        batch_op.drop_column("content_type")
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("profile_version")
        batch_op.drop_column("profile_image_url")

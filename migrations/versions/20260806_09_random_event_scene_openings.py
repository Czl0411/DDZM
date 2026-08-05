"""Split random event scene sign-up and formal openings."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260806_09"
down_revision: str | None = "20260806_08"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True)
    op.alter_column("random_event_scenes", "opening_text", new_column_name="signup_text")
    op.alter_column("random_events", "opening_text", new_column_name="signup_text")
    op.create_table(
        "random_event_scene_openings",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("scene_id", uuid_type, nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["scene_id"], ["random_event_scenes.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scene_id", "position"),
    )
    op.execute(
        "INSERT INTO random_event_scene_openings (id, scene_id, position, content) "
        "SELECT gen_random_uuid(), id, 0, signup_text FROM random_event_scenes"
    )
    op.add_column(
        "random_events", sa.Column("formal_opening_text", sa.Text(), nullable=True)
    )
    op.execute("UPDATE random_events SET formal_opening_text = signup_text")
    op.alter_column("random_events", "formal_opening_text", nullable=False)


def downgrade() -> None:
    op.drop_column("random_events", "formal_opening_text")
    op.drop_table("random_event_scene_openings")
    op.alter_column("random_events", "signup_text", new_column_name="opening_text")
    op.alter_column("random_event_scenes", "signup_text", new_column_name="opening_text")

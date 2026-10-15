"""Mistrealm single-player story progress and public lobby channel."""
from alembic import op
import sqlalchemy as sa


revision = "20261015_114"
down_revision = "20261015_113"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "mistrealm_players",
        sa.Column("channel_muted_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_mistrealm_players_channel_muted_until",
        "mistrealm_players",
        ["channel_muted_until"],
    )
    op.create_table(
        "mistrealm_story_progress",
        sa.Column(
            "player_id",
            sa.Uuid(),
            sa.ForeignKey("mistrealm_players.id"),
            primary_key=True,
        ),
        sa.Column("completed_chapters", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "mistrealm_channel_messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "player_id",
            sa.Uuid(),
            sa.ForeignKey("mistrealm_players.id"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("text", sa.String(200)),
        sa.Column("room_id", sa.Uuid(), sa.ForeignKey("mistrealm_rooms.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_mistrealm_channel_messages_player_id",
        "mistrealm_channel_messages",
        ["player_id"],
    )
    op.create_index(
        "ix_mistrealm_channel_messages_created_at",
        "mistrealm_channel_messages",
        ["created_at"],
    )


def downgrade():
    op.drop_index(
        "ix_mistrealm_channel_messages_created_at",
        table_name="mistrealm_channel_messages",
    )
    op.drop_index(
        "ix_mistrealm_channel_messages_player_id",
        table_name="mistrealm_channel_messages",
    )
    op.drop_table("mistrealm_channel_messages")
    op.drop_table("mistrealm_story_progress")
    op.drop_index(
        "ix_mistrealm_players_channel_muted_until",
        table_name="mistrealm_players",
    )
    op.drop_column("mistrealm_players", "channel_muted_until")

"""Public Mistrealm players, rooms, active seats and idempotent requests."""
from alembic import op
import sqlalchemy as sa

revision = "20261015_111"
down_revision = "20261014_110"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mistrealm_players",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("platform_uid", sa.String(255), unique=True, nullable=False),
        sa.Column("name", sa.String(40), nullable=False),
        sa.Column("avatar", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rate_limits", sa.JSON(), nullable=False),
    )
    op.create_table(
        "mistrealm_rooms",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("host_id", sa.Uuid(), sa.ForeignKey("mistrealm_players.id"), nullable=False),
        sa.Column("active_code", sa.String(6), unique=True),
        sa.Column("phase", sa.String(20), nullable=False),
        sa.Column("match_id", sa.Uuid()),
        sa.Column("state", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_mistrealm_rooms_phase", "mistrealm_rooms", ["phase"])
    op.create_index("ix_mistrealm_rooms_deadline", "mistrealm_rooms", ["deadline"])
    op.create_table(
        "mistrealm_seats",
        sa.Column("room_id", sa.Uuid(), sa.ForeignKey("mistrealm_rooms.id"), primary_key=True),
        sa.Column("seat_index", sa.Integer(), primary_key=True),
        sa.Column("player_id", sa.Uuid(), sa.ForeignKey("mistrealm_players.id"), unique=True, nullable=False),
    )
    op.create_table(
        "mistrealm_requests",
        sa.Column("player_id", sa.Uuid(), sa.ForeignKey("mistrealm_players.id"), primary_key=True),
        sa.Column("request_id", sa.Uuid(), primary_key=True),
        sa.Column("room_id", sa.Uuid(), sa.ForeignKey("mistrealm_rooms.id"), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    for name in ("mistrealm_requests", "mistrealm_seats", "mistrealm_rooms", "mistrealm_players"):
        op.drop_table(name)

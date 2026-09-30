"""Persist configurable scratch-card reward ranges."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260930_83"
down_revision: str | None = "20260919_82"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table("items"):
        return
    op.add_column("items", sa.Column("scratch_reward_min", sa.Integer(), nullable=True))
    op.add_column("items", sa.Column("scratch_reward_max", sa.Integer(), nullable=True))
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


def downgrade() -> None:
    op.drop_column("items", "scratch_reward_max")
    op.drop_column("items", "scratch_reward_min")

"""Merge PR #6 gameplay migrations with the deployed main chain."""

from collections.abc import Sequence


revision: str = "20261013_106"
down_revision: tuple[str, str] = ("20261012_105", "20261012_103")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

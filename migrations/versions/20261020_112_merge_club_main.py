"""merge club mahjong and main migration heads

Revision ID: 20261020_112
Revises: 20261020_111, 20261020_108
"""

from collections.abc import Sequence


revision: str = "20261020_112"
down_revision: tuple[str, str] = ("20261020_111", "20261020_108")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

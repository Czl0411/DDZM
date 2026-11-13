"""Add Bull Fight to the shared Club economy settings."""

from alembic import op
import sqlalchemy as sa


revision = "20261113_114_club_niuniu"
down_revision = "20261113_113_season_rake"
branch_labels = None
depends_on = None


_CONSTRAINT = "ck_club_game_economy_settings_game"
_GAMES_WITH_NIUNIU = (
    "game IN ('mahjong', 'chess', 'doudizhu', 'drawguess', "
    "'texas', 'zhajinhua', 'blackjack', 'niuniu')"
)
_GAMES_WITHOUT_NIUNIU = (
    "game IN ('mahjong', 'chess', 'doudizhu', 'drawguess', "
    "'texas', 'zhajinhua', 'blackjack')"
)


def upgrade() -> None:
    with op.batch_alter_table("club_game_economy_settings") as batch:
        batch.drop_constraint(_CONSTRAINT, type_="check")
        batch.create_check_constraint(_CONSTRAINT, _GAMES_WITH_NIUNIU)
    op.execute(sa.text(
        "INSERT INTO club_game_economy_settings "
        "(game, coin_stakes, rake_percent) "
        "VALUES ('niuniu', '[5, 10, 20]', 20)"
    ))


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM club_game_economy_settings WHERE game = 'niuniu'"
        )
    )
    with op.batch_alter_table("club_game_economy_settings") as batch:
        batch.drop_constraint(_CONSTRAINT, type_="check")
        batch.create_check_constraint(_CONSTRAINT, _GAMES_WITHOUT_NIUNIU)

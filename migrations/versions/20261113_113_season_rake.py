"""Add Club economy settings and company-season titles."""

from alembic import op
import sqlalchemy as sa


revision = "20261113_113_season_rake"
down_revision = "20261111_112_company_seasons"
branch_labels = None
depends_on = None


def upgrade() -> None:
    club_game_economy_settings = op.create_table(
        "club_game_economy_settings",
        sa.Column("game", sa.String(16), primary_key=True),
        sa.Column("coin_stakes", sa.JSON(), nullable=False),
        sa.Column(
            "rake_percent",
            sa.Integer(),
            server_default=sa.text("20"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "game IN ('mahjong', 'chess', 'doudizhu', 'drawguess', "
            "'texas', 'zhajinhua', 'blackjack')",
            name="ck_club_game_economy_settings_game",
        ),
        sa.CheckConstraint(
            "rake_percent >= 0 AND rake_percent <= 100",
            name="ck_club_game_economy_settings_rake_percent",
        ),
    )
    op.bulk_insert(
        club_game_economy_settings,
        [
            {"game": game, "coin_stakes": [5, 10, 20], "rake_percent": 20}
            for game in (
                "mahjong",
                "chess",
                "doudizhu",
                "drawguess",
                "texas",
                "zhajinhua",
                "blackjack",
            )
        ],
    )

    with op.batch_alter_table("texas_holdem_games") as batch_op:
        batch_op.add_column(
            sa.Column(
                "rake_percent_snapshot",
                sa.Integer(),
                server_default=sa.text("0"),
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "rake_amount",
                sa.Integer(),
                server_default=sa.text("0"),
                nullable=False,
            )
        )
        batch_op.create_check_constraint(
            "ck_texas_holdem_games_rake_percent_snapshot",
            "rake_percent_snapshot >= 0 AND rake_percent_snapshot <= 100",
        )
        batch_op.create_check_constraint(
            "ck_texas_holdem_games_rake_amount",
            "rake_amount >= 0",
        )

    with op.batch_alter_table("club_card_hands") as batch_op:
        batch_op.add_column(
            sa.Column(
                "rake_percent",
                sa.Integer(),
                server_default=sa.text("0"),
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "rake_amount",
                sa.Integer(),
                server_default=sa.text("0"),
                nullable=False,
            )
        )
        batch_op.create_check_constraint(
            "ck_club_card_hands_rake_percent",
            "rake_percent >= 0 AND rake_percent <= 100",
        )
        batch_op.create_check_constraint(
            "ck_club_card_hands_rake_amount",
            "rake_amount >= 0",
        )

    with op.batch_alter_table("game_settings") as batch_op:
        batch_op.add_column(
            sa.Column(
                "season_title_minimum_rank_order",
                sa.Integer(),
                server_default=sa.text("8"),
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "season_title_daily_reward",
                sa.Integer(),
                server_default=sa.text("5"),
                nullable=False,
            )
        )
        batch_op.create_check_constraint(
            "ck_game_settings_season_title_minimum_rank_order",
            "season_title_minimum_rank_order >= 1 "
            "AND season_title_minimum_rank_order <= 1000",
        )
        batch_op.create_check_constraint(
            "ck_game_settings_season_title_daily_reward",
            "season_title_daily_reward >= 0 "
            "AND season_title_daily_reward <= 999",
        )

    op.create_table(
        "company_season_titles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "season_code",
            sa.String(16),
            sa.ForeignKey("company_seasons.code"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title_name", sa.String(64), nullable=False),
        sa.Column("defined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "season_code", "user_id", name="uq_company_season_title_user"
        ),
    )


def downgrade() -> None:
    op.drop_table("company_season_titles")

    with op.batch_alter_table("game_settings") as batch_op:
        batch_op.drop_constraint(
            "ck_game_settings_season_title_daily_reward", type_="check"
        )
        batch_op.drop_constraint(
            "ck_game_settings_season_title_minimum_rank_order", type_="check"
        )
        batch_op.drop_column("season_title_daily_reward")
        batch_op.drop_column("season_title_minimum_rank_order")

    with op.batch_alter_table("club_card_hands") as batch_op:
        batch_op.drop_constraint(
            "ck_club_card_hands_rake_amount", type_="check"
        )
        batch_op.drop_constraint(
            "ck_club_card_hands_rake_percent", type_="check"
        )
        batch_op.drop_column("rake_amount")
        batch_op.drop_column("rake_percent")

    with op.batch_alter_table("texas_holdem_games") as batch_op:
        batch_op.drop_constraint(
            "ck_texas_holdem_games_rake_amount", type_="check"
        )
        batch_op.drop_constraint(
            "ck_texas_holdem_games_rake_percent_snapshot", type_="check"
        )
        batch_op.drop_column("rake_amount")
        batch_op.drop_column("rake_percent_snapshot")

    op.drop_table("club_game_economy_settings")

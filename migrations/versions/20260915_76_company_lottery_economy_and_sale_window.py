"""Update lottery economics and prevent next-day tickets selling early."""

from collections.abc import Sequence
from datetime import timedelta

from alembic import op
import sqlalchemy as sa


revision: str = "20260915_76"
down_revision: str | None = "20260915_75"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    settings = sa.table(
        "company_lottery_settings",
        sa.column("id", sa.Integer()),
        sa.column("red_pool", sa.Integer()),
        sa.column("red_count", sa.Integer()),
        sa.column("blue_pool", sa.Integer()),
        sa.column("ticket_price", sa.Integer()),
        sa.column("head_prize", sa.Integer()),
        sa.column("second_prize", sa.Integer()),
        sa.column("third_prize", sa.Integer()),
        sa.column("fourth_prize", sa.Integer()),
        sa.column("fifth_prize", sa.Integer()),
        sa.column("pool_ceiling", sa.Integer()),
        sa.column("per_person_cap", sa.Integer()),
        sa.column("max_tickets_per_day", sa.Integer()),
        sa.column("max_tickets_per_round", sa.Integer()),
        sa.column("close_offset_minutes", sa.Integer()),
    )
    values = {
        "head_prize": 500,
        "second_prize": 120,
        "third_prize": 20,
        "fourth_prize": 5,
        "fifth_prize": 1,
        "pool_ceiling": 1000,
        "per_person_cap": 500,
        "close_offset_minutes": 30,
    }
    bind.execute(settings.update().where(settings.c.id == 1).values(**values))
    current = bind.execute(sa.select(settings).where(settings.c.id == 1)).mappings().first()
    if current is None:
        return

    snapshot = {
        "red_pool": current["red_pool"],
        "red_count": current["red_count"],
        "blue_pool": current["blue_pool"],
        "ticket_price": current["ticket_price"],
        "head_prize": current["head_prize"],
        "second_prize": current["second_prize"],
        "third_prize": current["third_prize"],
        "fourth_prize": current["fourth_prize"],
        "fifth_prize": current["fifth_prize"],
        "pool_ceiling": current["pool_ceiling"],
        "per_person_cap": current["per_person_cap"],
        "max_tickets_per_day": current["max_tickets_per_day"],
        "max_tickets_per_round": current["max_tickets_per_round"],
    }
    rounds = sa.table(
        "company_lottery_rounds",
        sa.column("id", sa.Uuid()),
        sa.column("state", sa.String()),
        sa.column("tickets_sold", sa.Integer()),
        sa.column("close_at", sa.DateTime(timezone=True)),
        sa.column("draw_at", sa.DateTime(timezone=True)),
        sa.column("rules_snapshot", sa.JSON()),
    )
    rows = bind.execute(
        sa.select(rounds.c.id, rounds.c.draw_at).where(
            rounds.c.state == "open", rounds.c.tickets_sold == 0
        )
    ).mappings()
    for row in rows:
        bind.execute(
            rounds.update().where(rounds.c.id == row["id"]).values(
                close_at=row["draw_at"] - timedelta(minutes=30),
                rules_snapshot=snapshot,
            )
        )


def downgrade() -> None:
    # 这是生产配置数据迁移；回退结构版本时不逆转已经公布的规则。
    pass

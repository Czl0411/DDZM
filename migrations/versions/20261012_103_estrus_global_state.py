"""merge estrus state into one shared row per user"""

from collections.abc import Sequence
from datetime import datetime
from zoneinfo import ZoneInfo

from alembic import op
import sqlalchemy as sa


revision: str = "20261012_103"
down_revision: str | None = "20261010_102"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("estrus_states"):
        return

    states = sa.table(
        "estrus_states",
        sa.column("id", sa.Uuid()),
        sa.column("user_id", sa.Uuid()),
        sa.column("heat", sa.Integer()),
        sa.column("chopped_count", sa.Integer()),
        sa.column("total_climaxes", sa.Integer()),
        sa.column("today_climaxes", sa.Integer()),
        sa.column("last_active_date", sa.Date()),
        sa.column("opted_out", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    user_ids = list(
        bind.execute(sa.select(states.c.user_id).group_by(states.c.user_id)).scalars()
    )
    for user_id in user_ids:
        rows = list(
            bind.execute(
                sa.select(states)
                .where(states.c.user_id == user_id)
                .order_by(states.c.created_at, states.c.id)
            ).mappings()
        )
        if len(rows) <= 1:
            continue

        current_rows = [row for row in rows if row["last_active_date"] == today]
        canonical = rows[0]
        bind.execute(
            states.update()
            .where(states.c.id == canonical["id"])
            .values(
                heat=sum(int(row["heat"] or 0) for row in rows),
                chopped_count=sum(int(row["chopped_count"] or 0) for row in rows),
                total_climaxes=sum(int(row["total_climaxes"] or 0) for row in rows),
                today_climaxes=sum(
                    int(row["today_climaxes"] or 0) for row in current_rows
                ),
                last_active_date=today if current_rows else max(
                    (
                        row["last_active_date"]
                        for row in rows
                        if row["last_active_date"] is not None
                    ),
                    default=None,
                ),
                opted_out=any(bool(row["opted_out"]) for row in rows),
                created_at=min(row["created_at"] for row in rows),
                updated_at=max(row["updated_at"] for row in rows),
            )
        )
        bind.execute(
            states.delete().where(
                states.c.id.in_([row["id"] for row in rows[1:]])
            )
        )

    with op.batch_alter_table("estrus_states") as batch:
        batch.create_unique_constraint(
            "ux_estrus_state_user", ["user_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("estrus_states") as batch:
        batch.drop_constraint("ux_estrus_state_user", type_="unique")

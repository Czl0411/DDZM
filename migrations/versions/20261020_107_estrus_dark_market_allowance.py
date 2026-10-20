"""Update estrus heat values and add dark-market department allowance kind."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20261020_107"
down_revision: str | None = "20261013_106"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


OLD_KINDS = (
    "'dept_checkin', 'dept_event', 'dept_game_host', 'dept_game_play', "
    "'dept_submission', 'dept_chat', 'dept_referral', 'dept_fine'"
)
NEW_KINDS = (
    "'dept_checkin', 'dept_event', 'dept_dark_market', 'dept_game_host', "
    "'dept_game_play', 'dept_submission', 'dept_chat', 'dept_referral', "
    "'dept_fine'"
)


def _replace_allowance_constraint(kinds: str) -> None:
    if not sa.inspect(op.get_bind()).has_table("department_allowances"):
        return
    with op.batch_alter_table("department_allowances") as batch:
        batch.drop_constraint("ck_department_allowance_kind", type_="check")
        batch.create_check_constraint(
            "ck_department_allowance_kind", f"kind IN ({kinds})"
        )


def upgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("estrus_settings"):
        bind.execute(sa.text("UPDATE estrus_settings SET g_spot_heat_bonus = 20"))
    _replace_allowance_constraint(NEW_KINDS)


def downgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("department_allowances"):
        bind.execute(
            sa.text(
                "DELETE FROM department_allowances WHERE kind = 'dept_dark_market'"
            )
        )
    _replace_allowance_constraint(OLD_KINDS)
    if sa.inspect(bind).has_table("estrus_settings"):
        bind.execute(sa.text("UPDATE estrus_settings SET g_spot_heat_bonus = 10"))

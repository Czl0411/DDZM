"""Allow all qualifying employees to receive a check-in honor.

Revision ID: 20261005_99
Revises: 20261005_98
"""

from alembic import op
import sqlalchemy as sa


revision = "20261005_99"
down_revision = "20261005_98"
branch_labels = None
depends_on = None
convention = {"uq": "uq_%(table_name)s_%(column_0_name)s_%(column_1_name)s"}


def upgrade():
    if op.get_context().dialect.name == "postgresql":
        op.drop_constraint("honor_awards_period_id_title_key_key", "honor_awards", type_="unique")
        op.create_unique_constraint("uq_honor_awards_period_title_user", "honor_awards", ["period_id", "title_key", "user_id"])
    else:
        with op.batch_alter_table("honor_awards", naming_convention=convention) as batch:
            batch.drop_constraint("uq_honor_awards_period_id_title_key", type_="unique")
            batch.create_unique_constraint("uq_honor_awards_period_title_user", ["period_id", "title_key", "user_id"])


def downgrade():
    if not op.get_context().as_sql and op.get_bind().scalar(sa.text(
        "SELECT COUNT(*) FROM (SELECT period_id, title_key FROM honor_awards "
        "GROUP BY period_id, title_key HAVING COUNT(*) > 1) AS multiple_winners"
    )):
        raise RuntimeError("Cannot restore one-winner uniqueness while multi-winner honors exist; preserve these records before downgrading")
    if op.get_context().dialect.name == "postgresql":
        op.drop_constraint("uq_honor_awards_period_title_user", "honor_awards", type_="unique")
        op.create_unique_constraint("honor_awards_period_id_title_key_key", "honor_awards", ["period_id", "title_key"])
    else:
        with op.batch_alter_table("honor_awards") as batch:
            batch.drop_constraint("uq_honor_awards_period_title_user", type_="unique")
            batch.create_unique_constraint("uq_honor_awards_period_id_title_key", ["period_id", "title_key"])

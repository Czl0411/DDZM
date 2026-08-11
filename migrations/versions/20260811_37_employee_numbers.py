"""Add permanent employee numbers."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260811_37"
down_revision: str | None = "20260811_36"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("employee_number", sa.Integer(), nullable=True)
    )
    users = sa.table(
        "users",
        sa.column("id", sa.Uuid()),
        sa.column("joined_at", sa.DateTime(timezone=True)),
        sa.column("employee_number", sa.Integer()),
    )
    connection = op.get_bind()
    user_ids = connection.execute(
        sa.select(users.c.id).order_by(users.c.joined_at, users.c.id)
    ).scalars()
    next_number = 1
    for user_id in user_ids:
        connection.execute(
            users.update()
            .where(users.c.id == user_id)
            .values(employee_number=next_number)
        )
        next_number += 1

    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "employee_number", existing_type=sa.Integer(), nullable=False
        )
        batch_op.create_unique_constraint(
            "uq_users_employee_number", ["employee_number"]
        )

    op.create_table(
        "employee_number_counters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("next_number", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    counters = sa.table(
        "employee_number_counters",
        sa.column("id", sa.Integer()),
        sa.column("next_number", sa.Integer()),
    )
    op.bulk_insert(counters, [{"id": 1, "next_number": next_number}])


def downgrade() -> None:
    op.drop_table("employee_number_counters")
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint("uq_users_employee_number", type_="unique")
        batch_op.drop_column("employee_number")

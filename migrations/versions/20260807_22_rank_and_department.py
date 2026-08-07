"""Add employee ranks, departments, and promotion approvals."""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

from alembic import op
import sqlalchemy as sa


revision: str = "20260807_22"
down_revision: str | None = "20260807_21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


default_rank_id = uuid4()
default_department_id = uuid4()


def upgrade() -> None:
    op.create_table(
        "ranks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, unique=True),
        sa.Column("name", sa.String(length=64), nullable=False, unique=True),
        sa.Column("level_label", sa.String(length=16), nullable=False, unique=True),
        sa.Column("promotion_price", sa.Integer(), nullable=False),
        sa.Column("vote_weight", sa.Integer(), nullable=False),
        sa.Column("multiplayer_game_limit", sa.Integer(), nullable=False),
        sa.Column("has_group_management", sa.Boolean(), nullable=False),
        sa.Column("is_board", sa.Boolean(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "departments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    ranks = sa.table(
        "ranks",
        sa.column("id", sa.Uuid()),
        sa.column("sort_order", sa.Integer()),
        sa.column("name", sa.String()),
        sa.column("level_label", sa.String()),
        sa.column("promotion_price", sa.Integer()),
        sa.column("vote_weight", sa.Integer()),
        sa.column("multiplayer_game_limit", sa.Integer()),
        sa.column("has_group_management", sa.Boolean()),
        sa.column("is_board", sa.Boolean()),
        sa.column("enabled", sa.Boolean()),
    )
    rank_ids = [default_rank_id, *[uuid4() for _ in range(10)]]
    op.bulk_insert(
        ranks,
        [
            {
                "id": rank_id,
                "sort_order": sort_order,
                "name": name,
                "level_label": level_label,
                "promotion_price": promotion_price,
                "vote_weight": vote_weight,
                "multiplayer_game_limit": multiplayer_game_limit,
                "has_group_management": has_group_management,
                "is_board": is_board,
                "enabled": True,
            }
            for rank_id, (
                sort_order,
                name,
                level_label,
                promotion_price,
                vote_weight,
                multiplayer_game_limit,
                has_group_management,
                is_board,
            ) in zip(rank_ids, _DEFAULT_RANKS, strict=True)
        ],
    )
    departments = sa.table(
        "departments",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("is_default", sa.Boolean()),
        sa.column("enabled", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    department_ids = [default_department_id, *[uuid4() for _ in range(8)]]
    op.bulk_insert(
        departments,
        [
            {
                "id": department_id,
                "name": name,
                "description": "",
                "is_default": is_default,
                "enabled": True,
                "created_at": datetime.now(UTC),
            }
            for department_id, (name, is_default) in zip(
                department_ids, _DEFAULT_DEPARTMENTS, strict=True
            )
        ],
    )

    op.add_column("users", sa.Column("rank_id", sa.Uuid(), nullable=True))
    op.add_column("users", sa.Column("department_id", sa.Uuid(), nullable=True))
    users = sa.table(
        "users",
        sa.column("rank_id", sa.Uuid()),
        sa.column("department_id", sa.Uuid()),
    )
    op.execute(
        users.update().values(
            rank_id=default_rank_id,
            department_id=default_department_id,
        )
    )
    op.create_foreign_key("fk_users_rank", "users", "ranks", ["rank_id"], ["id"])
    op.create_foreign_key(
        "fk_users_department", "users", "departments", ["department_id"], ["id"]
    )
    op.alter_column("users", "rank_id", nullable=False)
    op.alter_column("users", "department_id", nullable=False)

    op.create_table(
        "promotion_requests",
        sa.Column("id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("number", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("applicant_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("source_rank_id", sa.Uuid(), sa.ForeignKey("ranks.id"), nullable=False),
        sa.Column("target_rank_id", sa.Uuid(), sa.ForeignKey("ranks.id"), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ux_promotion_requests_pending_employee",
        "promotion_requests",
        ["applicant_id"],
        unique=True,
        postgresql_where=sa.text("state = 'pending'"),
        sqlite_where=sa.text("state = 'pending'"),
    )
    op.create_table(
        "promotion_approvals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "request_id", sa.Uuid(), sa.ForeignKey("promotion_requests.id"), nullable=False, unique=True
        ),
        sa.Column("approver_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("promotion_approvals")
    op.drop_index("ux_promotion_requests_pending_employee", table_name="promotion_requests")
    op.drop_table("promotion_requests")
    op.drop_constraint("fk_users_department", "users", type_="foreignkey")
    op.drop_constraint("fk_users_rank", "users", type_="foreignkey")
    op.drop_column("users", "department_id")
    op.drop_column("users", "rank_id")
    op.drop_table("departments")
    op.drop_table("ranks")


_DEFAULT_RANKS = (
    (1, "实习生", "LV1", 0, 0, 0, False, False),
    (2, "正式员工", "LV2", 80, 1, 0, False, False),
    (3, "小组长", "LV3", 200, 1, 0, False, False),
    (4, "副主管", "LV4", 500, 1, 1, False, False),
    (5, "主管", "LV5", 500, 1, 1, False, False),
    (6, "部门副经理", "LV6", 800, 2, 2, False, False),
    (7, "部门经理", "LV7", 800, 2, 2, False, False),
    (8, "部门副总监", "LV8", 1000, 3, 3, True, False),
    (9, "部门总监", "LV9", 1000, 3, 3, True, False),
    (10, "公司负责人", "LV10", 2000, 5, 5, True, False),
    (11, "核心董事会", "LvMax", 0, 10, -1, True, True),
)
_DEFAULT_DEPARTMENTS = (
    ("未分配部门", True),
    ("色色事业部", False),
    ("小游戏娱乐部", False),
    ("次元外联部", False),
    ("风纪监察部", False),
    ("核心技术部", False),
    ("摸鱼研究部", False),
    ("抽象艺术部", False),
    ("学院", False),
)

"""Persist Who Is the Undercover state-machine fixes."""

from collections.abc import Sequence
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import Connection


revision: str = "20260811_38"
down_revision: str | None = "20260811_37"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


OLD_RECORDED_TEMPLATE = "投票已记录，等待其他存活玩家投票。"
NEW_RECORDED_TEMPLATE = (
    "【谁是卧底】{编号}号 {玩家名称} 已投票"
    "（{已完成人数}/{存活人数}）。"
)
OLD_SETTLED_TEMPLATE = (
    "【谁是卧底】{淘汰玩家} 出局，身份：{身份}。\n"
    "{胜利阵营}阵营获胜。发送 /继续 可开启下一局。"
)
NEW_SETTLED_TEMPLATE = (
    "【谁是卧底】{胜利阵营}阵营获胜。\n"
    "平民词：{平民词}\n卧底词：{卧底词}\n本轮淘汰：{淘汰情况}\n"
    "手动弃票：{手动弃票}\n超时弃票：{超时弃票}\n"
    "下一轮退出：{下一轮退出}\n全部身份：\n{全部身份}\n"
    "发送 /继续 可开启下一局。"
)
NEW_TEMPLATES = (
    (
        "/谁是卧底",
        "delivery_failed",
        "【谁是卧底】身份私聊发放失败，所有旧身份牌已作废；"
        "其他玩家保留报名，发放失败的玩家请发送 /加入。",
    ),
    ("/投票", "already_abstained", "你本轮已经弃票，不能再投票。"),
    (
        "/投票",
        "timeout_abstention",
        "【谁是卧底】投票时间结束。{弃票玩家列表} 未投票，本轮自动弃票。",
    ),
    ("/跳过", "no_current_game", "当前没有可执行跳过的游戏。"),
    ("/跳过", "undercover_usage", "谁是卧底投票阶段请发送 /跳过 编号。"),
    (
        "/跳过",
        "undercover_abstained",
        "【谁是卧底】{编号}号 {玩家名称} 本轮弃票"
        "（{已完成人数}/{存活人数}，已投票 {投票人数} 人、"
        "弃票 {弃票人数} 人）。",
    ),
    (
        "/跳过",
        "undercover_cannot_skip_self",
        "不能让自己弃票；请由另一名存活玩家操作。",
    ),
    (
        "/跳过",
        "undercover_already_voted",
        "该玩家本轮已经投票，不能再标记弃票。",
    ),
    ("/跳过", "undercover_already_abstained", "该玩家本轮已经弃票。"),
    (
        "/跳过",
        "undercover_invalid_target",
        "该编号不是当前存活玩家，请重新确认。",
    ),
    (
        "/跳过",
        "undercover_cannot_skip",
        "当前不能执行谁是卧底弃票，或你不是存活参与者。",
    ),
    (
        "/跳过",
        "undercover_vote_expired",
        "【谁是卧底】本轮无人投票，继续自由发言。",
    ),
)


def _reply_templates():
    return sa.table(
        "command_reply_templates",
        sa.column("id", sa.Uuid()),
        sa.column("command", sa.String()),
        sa.column("scenario", sa.String()),
        sa.column("template", sa.Text()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )


def _upgrade_reply_templates(connection: Connection) -> None:
    templates = _reply_templates()
    connection.execute(
        templates.update()
        .where(
            templates.c.command == "/投票",
            templates.c.scenario == "recorded",
            templates.c.template == OLD_RECORDED_TEMPLATE,
        )
        .values(template=NEW_RECORDED_TEMPLATE)
    )
    connection.execute(
        templates.update()
        .where(
            templates.c.command == "/投票",
            templates.c.scenario == "settled",
            templates.c.template == OLD_SETTLED_TEMPLATE,
        )
        .values(template=NEW_SETTLED_TEMPLATE)
    )
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    for command, scenario, template in NEW_TEMPLATES:
        exists = connection.scalar(
            sa.select(templates.c.id).where(
                templates.c.command == command,
                templates.c.scenario == scenario,
            )
        )
        if exists is None:
            connection.execute(
                templates.insert().values(
                    id=uuid4(),
                    command=command,
                    scenario=scenario,
                    template=template,
                    created_at=now,
                    updated_at=now,
                )
            )


def _downgrade_reply_templates(connection: Connection) -> None:
    templates = _reply_templates()
    connection.execute(
        templates.update()
        .where(
            templates.c.command == "/投票",
            templates.c.scenario == "recorded",
            templates.c.template == NEW_RECORDED_TEMPLATE,
        )
        .values(template=OLD_RECORDED_TEMPLATE)
    )
    connection.execute(
        templates.update()
        .where(
            templates.c.command == "/投票",
            templates.c.scenario == "settled",
            templates.c.template == NEW_SETTLED_TEMPLATE,
        )
        .values(template=OLD_SETTLED_TEMPLATE)
    )
    for command, scenario, template in NEW_TEMPLATES:
        connection.execute(
            templates.delete().where(
                templates.c.command == command,
                templates.c.scenario == scenario,
                templates.c.template == template,
            )
        )


def upgrade() -> None:
    op.add_column(
        "undercover_games",
        sa.Column("vote_seconds_snapshot", sa.Integer(), nullable=True),
    )
    op.add_column(
        "undercover_games",
        sa.Column(
            "whiteboard_win_remaining_snapshot", sa.Integer(), nullable=True
        ),
    )
    connection = op.get_bind()
    settings = sa.table(
        "undercover_settings",
        sa.column("id", sa.Integer()),
        sa.column("vote_seconds", sa.Integer()),
        sa.column("whiteboard_win_remaining", sa.Integer()),
    )
    games = sa.table(
        "undercover_games",
        sa.column("vote_seconds_snapshot", sa.Integer()),
        sa.column("whiteboard_win_remaining_snapshot", sa.Integer()),
    )
    current = connection.execute(
        sa.select(
            settings.c.vote_seconds,
            settings.c.whiteboard_win_remaining,
        ).where(settings.c.id == 1)
    ).one()
    connection.execute(
        games.update().values(
            vote_seconds_snapshot=current.vote_seconds,
            whiteboard_win_remaining_snapshot=current.whiteboard_win_remaining,
        )
    )
    with op.batch_alter_table("undercover_games") as batch_op:
        batch_op.alter_column(
            "vote_seconds_snapshot", existing_type=sa.Integer(), nullable=False
        )
        batch_op.alter_column(
            "whiteboard_win_remaining_snapshot",
            existing_type=sa.Integer(),
            nullable=False,
        )
    op.add_column(
        "undercover_session_members",
        sa.Column(
            "leave_after_round",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_table(
        "undercover_abstentions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("game_id", sa.Uuid(), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("player_user_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.String(length=24), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["game_id"], ["undercover_games.id"]),
        sa.ForeignKeyConstraint(["player_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "game_id",
            "round_number",
            "player_user_id",
            name="uq_undercover_abstention_player_round",
        ),
    )
    _upgrade_reply_templates(connection)


def downgrade() -> None:
    _downgrade_reply_templates(op.get_bind())
    op.drop_table("undercover_abstentions")
    with op.batch_alter_table("undercover_session_members") as batch_op:
        batch_op.drop_column("leave_after_round")
    with op.batch_alter_table("undercover_games") as batch_op:
        batch_op.drop_column("whiteboard_win_remaining_snapshot")
        batch_op.drop_column("vote_seconds_snapshot")

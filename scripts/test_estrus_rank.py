"""干跑脚本：不向群里发任何消息，仅打印发情值排名的真实数据与推送文案。

用法: /opt/dzmm/venv/bin/python test_estrus_rank.py
"""
import datetime
from zoneinfo import ZoneInfo

from dzmm_bot.core.database import create_session_factory
from dzmm_bot.core.repository import CoreRepository
from dzmm_bot.core.schema import PRIMARY_GROUP_CHAT_ID
from dzmm_bot.runtime.settings import Settings

NOW = datetime.datetime.now(ZoneInfo("Asia/Shanghai"))

settings = Settings.from_environment()
repo = CoreRepository(create_session_factory(settings.database_url))

print("===== 1. 发情值状态原始数据 =====")
from sqlalchemy import create_engine, text as sql_text  # noqa: E402

engine = create_engine(settings.database_url.replace("postgresql+psycopg", "postgresql"))
with engine.connect() as conn:
    rows = conn.execute(
        sql_text(
            """
            SELECT u.display_name, s.heat, s.chopped_count,
                   s.total_climaxes, s.today_climaxes, s.opted_out
            FROM estrus_states s JOIN users u ON u.id = s.user_id
            ORDER BY s.heat DESC, s.chopped_count DESC
            """
        )
    ).all()
for row in rows:
    print(" ", row)
if not rows:
    print("  （暂无任何 estrus_states 记录）")

print("===== 2. estrus_rankings() 前 5 =====")
entries = repo.estrus_rankings(PRIMARY_GROUP_CHAT_ID, NOW)
for entry in entries:
    print(" ", entry)
if not entries:
    print("  （无人上榜）")

print("===== 3. 定时推送文案（_estrus_rank_text 干跑） =====")
print(repo._estrus_rank_text(PRIMARY_GROUP_CHAT_ID, NOW.strftime("%H:%M"), NOW))

print("===== 4. 指令种子是否启用 =====")
with engine.connect() as conn:
    rows = conn.execute(
        sql_text(
            "SELECT command, enabled FROM command_definitions "
            "WHERE command IN ('/我的发情值', '/发情值排名')"
        )
    ).all()
for row in rows:
    print(" ", row)

print("===== 5. 收益榜推送时刻（发情值榜跟随这些时刻推送） =====")
print(" ", repo.get_activity_settings().report_times)

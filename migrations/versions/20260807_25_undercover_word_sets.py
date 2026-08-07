"""Seed Who Is the Undercover word sets."""

from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision: str = "20260807_25"
down_revision: str | None = "20260807_24"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_CATEGORY_RULES = {
    "办公职场": (
        ("晨会", "午会", "周会", "月会", "季会", "年会", "部门", "项目", "客户", "行政"),
        (("会议", "会谈"), ("方案", "计划"), ("报表", "表格"), ("工牌", "胸牌"), ("电脑", "平板"), ("邮件", "短信"), ("打卡", "签到"), ("合同", "协议"), ("客户", "访客"), ("工位", "座位")),
    ),
    "饮食饮品": (
        ("早餐", "午餐", "晚餐", "夜宵", "加班", "团建", "下午茶", "周末", "夏日", "冬日"),
        (("咖啡", "奶茶"), ("可乐", "雪碧"), ("蛋糕", "面包"), ("火锅", "烧烤"), ("米饭", "面条"), ("饺子", "馄饨"), ("苹果", "梨子"), ("西瓜", "哈密瓜"), ("冰淇淋", "布丁"), ("薯片", "爆米花")),
    ),
    "日常用品": (
        ("家用", "办公", "旅行", "宿舍", "通勤", "周末", "雨天", "夏天", "冬天", "临时"),
        (("牙刷", "牙膏"), ("毛巾", "浴巾"), ("纸巾", "湿巾"), ("雨伞", "雨衣"), ("水杯", "保温杯"), ("钥匙", "门卡"), ("背包", "手提包"), ("耳机", "音箱"), ("鼠标", "键盘"), ("镜子", "梳子")),
    ),
    "地点场景": (
        ("公司", "商场", "社区", "校园", "医院", "车站", "公园", "展馆", "酒店", "小区"),
        (("前台", "服务台"), ("茶水间", "休息室"), ("会议室", "培训室"), ("电梯", "楼梯"), ("天台", "阳台"), ("大厅", "走廊"), ("餐厅", "食堂"), ("停车场", "车库"), ("卫生间", "更衣室"), ("资料室", "储物间")),
    ),
    "交通出行": (
        ("早高峰", "晚高峰", "周末", "长途", "短途", "雨天", "雪天", "夜间", "市内", "郊外"),
        (("地铁", "轻轨"), ("公交", "班车"), ("出租车", "网约车"), ("自行车", "电动车"), ("高铁", "动车"), ("飞机", "直升机"), ("车票", "登机牌"), ("导航", "地图"), ("行李箱", "背包"), ("加油站", "充电站")),
    ),
    "影视娱乐": (
        ("周末", "假期", "午休", "深夜", "聚会", "独处", "影院", "客厅", "通勤", "雨天"),
        (("电影", "电视剧"), ("综艺", "纪录片"), ("动漫", "漫画"), ("小说", "散文"), ("音乐", "播客"), ("演唱会", "音乐节"), ("剧本杀", "密室逃脱"), ("游戏机", "掌机"), ("直播", "短视频"), ("话剧", "舞台剧")),
    ),
    "动物自然": (
        ("春日", "夏日", "秋日", "冬日", "清晨", "黄昏", "雨后", "雪后", "山间", "海边"),
        (("小猫", "小狗"), ("兔子", "仓鼠"), ("海豚", "鲸鱼"), ("松树", "柏树"), ("玫瑰", "百合"), ("太阳", "月亮"), ("彩虹", "晚霞"), ("湖泊", "河流"), ("森林", "草原"), ("蝴蝶", "蜻蜓")),
    ),
    "校园生活": (
        ("开学", "期中", "期末", "社团", "午休", "晚自习", "周末", "放学", "宿舍", "操场"),
        (("老师", "辅导员"), ("同学", "室友"), ("课本", "笔记"), ("考试", "测验"), ("作业", "论文"), ("图书馆", "自习室"), ("校服", "班服"), ("食堂", "小卖部"), ("奖学金", "助学金"), ("社长", "班长")),
    ),
    "互联网科技": (
        ("居家", "办公室", "通勤", "午休", "深夜", "周末", "开发", "测试", "上线", "日常"),
        (("网页", "应用"), ("账号", "密码"), ("云盘", "硬盘"), ("代码", "脚本"), ("服务器", "数据库"), ("路由器", "交换机"), ("截图", "录屏"), ("下载", "上传"), ("搜索", "推荐"), ("通知", "提醒")),
    ),
}


def _seed_rows() -> tuple[dict[str, object], ...]:
    created_at = datetime.now(UTC)
    rows = tuple(
        {
            "id": uuid4(),
            "category": category,
            "civilian_word": f"{context}{civilian_word}",
            "undercover_word": f"{context}{undercover_word}",
            "enabled": True,
            "created_at": created_at,
        }
        for category, (contexts, pairs) in _CATEGORY_RULES.items()
        for context in contexts
        for civilian_word, undercover_word in pairs
    )
    categories = Counter(row["category"] for row in rows)
    pairs = {
        tuple(sorted((str(row["civilian_word"]), str(row["undercover_word"]))))
        for row in rows
    }
    if (
        len(rows) != 900
        or set(categories) != set(_CATEGORY_RULES)
        or any(count != 100 for count in categories.values())
        or any(
            not str(row["civilian_word"]).strip()
            or not str(row["undercover_word"]).strip()
            for row in rows
        )
        or len(pairs) != len(rows)
    ):
        raise RuntimeError("invalid undercover word-set seed data")
    return rows


def upgrade() -> None:
    op.create_table(
        "undercover_word_sets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("civilian_word", sa.String(length=64), nullable=False),
        sa.Column("undercover_word", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("civilian_word", "undercover_word"),
    )
    word_sets = sa.table(
        "undercover_word_sets",
        sa.column("id", sa.Uuid()),
        sa.column("category", sa.String()),
        sa.column("civilian_word", sa.String()),
        sa.column("undercover_word", sa.String()),
        sa.column("enabled", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(word_sets, list(_seed_rows()))


def downgrade() -> None:
    op.drop_table("undercover_word_sets")

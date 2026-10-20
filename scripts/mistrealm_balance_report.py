"""Internal report. Run with the service's DZMM_DATABASE_URL; never publish credentials."""
import argparse
from datetime import datetime,timedelta,timezone
from html import escape
import json
from pathlib import Path
from sqlalchemy import select
from dzmm_bot.core.database import create_session_factory
from dzmm_bot.core.schema import MistrealmBalanceMatchRecord as Match
from dzmm_bot.core.mistrealm_balance import summarize
from dzmm_bot.runtime.settings import Settings
from dzmm_bot.core.mistrealm_v3_cards import CARDS,FACTIONS


def write_report(report,directory):
    directory.mkdir(parents=True,exist_ok=True)
    (directory/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    columns=[('population','对战类型'),('mode','模式'),('revision','规则版本'),('player_kind','参赛方'),('dimension','维度'),('key','对象'),('entries','样本'),('usage','使用率%'),('wins','胜'),('losses','负'),('draws','平'),('win_rate','胜率%'),('win_interval','95%区间'),('sample','说明')]
    names={'pvp':'真人对战','pve':'人机对战','story':'剧情','casual':'休闲','ranked':'排位','human':'真人','bot':'人机','faction':'阵营','leader':'领袖','deck':'卡组指纹','initiative':'首局先后手','first':'先手','second':'后手','unknown':'未记录',**FACTIONS,**{k:v['name'] for k,v in CARDS.items()}}
    def display(row,key):
        value=row[key]
        return names.get(str(value),str(value)) if key not in ('revision','entries','usage','wins','losses','draws','win_rate','win_interval') else str(value)
    table='<tr>'+''.join('<th>'+name+'</th>' for _,name in columns)+'</tr>'
    table+=''.join('<tr>'+''.join('<td>'+escape(display(row,k))+'</td>' for k,_ in columns)+'</tr>' for row in report['rows'])
    if not report['rows']:table+='<tr><td colspan="14">暂无已采集的完整比赛。部署后将开始累计，不补造历史数据。</td></tr>'
    html='<!doctype html><html lang="zh"><meta charset="utf-8"><title>雾境平衡观察</title><style>body{font:14px system-ui;margin:28px;background:#101d26;color:#e7e0cf}table{border-collapse:collapse;width:100%}td,th{border:1px solid #52636a;padding:8px;text-align:left}th{background:#273b43}p{line-height:1.7}</style><h1>雾境 · 平衡观察</h1><p>完整比赛 '+str(report['matches'])+' 场</p>'+''.join('<p>'+escape(n)+'</p>' for n in report['notes'])+'<table>'+table+'</table></html>'
    (directory/'index.html').write_text(html)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--days',type=int,default=28);parser.add_argument('--output',type=Path,default=Path('outputs/mistrealm-balance-report'));args=parser.parse_args()
    if args.days<1:parser.error('--days must be positive')
    factory=create_session_factory(Settings.from_environment().database_url)
    with factory() as session:
        matches=session.scalars(select(Match).where(Match.finished_at>=datetime.now(timezone.utc)-timedelta(days=args.days))).all()
        write_report(summarize(matches),args.output)
    print(args.output/'index.html')

if __name__=='__main__':main()

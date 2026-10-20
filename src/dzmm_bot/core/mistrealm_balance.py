"""Internal balance telemetry: one immutable sample per finished whole match."""
from hashlib import sha256
import json
from math import sqrt

from .schema import MistrealmBalanceMatchRecord as Match
from .mistrealm_v3_cards import CARDS
CATALOGUE_REVISION=sha256(json.dumps(CARDS,sort_keys=True).encode()).hexdigest()[:12]


def record_match(session,room,now):
    s=room.state
    if s.get('rules_version')!=3 or s.get('balance_revision',0)<2 or s['phase']!='finished' or not room.match_id:return
    if session.get(Match,room.match_id):return
    participants=[]
    for seat,p in enumerate(s['players']):
        deck=p['selection']
        counts={k:v for k,v in deck['counts'].items() if v}
        signature=json.dumps([deck['faction'],deck['leader'],sorted(counts.items())],separators=(',',':'))
        participants.append(dict(seat=seat,kind='bot' if seat==1 and s.get('mode') in ('bot','story') else 'human',
                                 faction=deck['faction'],leader=deck['leader'],deck=sha256(signature.encode()).hexdigest()[:16],counts=counts))
    session.add(Match(match_id=room.match_id,room_id=room.id,finished_at=now,
        rules_revision=f"3.{s.get('balance_revision',0)}:{CATALOGUE_REVISION}",mode='ranked' if s.get('ranked_match') else 'story' if s.get('mode')=='story' else 'casual',
        population='story' if s.get('mode')=='story' else 'pve' if s.get('mode')=='bot' else 'pvp',
        first_seat=s.get('balance_first'),winner=s['winner'],rounds=s['round'],
        end_reason='concede' if any(e['kind']=='concede' for e in s.get('action_log',[])) else 'normal',participants=participants))


def summarize(matches):
    """Rates use whole-match participant entries; mirrors intentionally count twice."""
    buckets={}
    for m in matches:
        for p in m.participants:
            context=(m.rules_revision,m.mode,m.population,p['kind'])
            for dimension,value in [('faction',p['faction']),('leader',p['leader']),('deck',p['deck']),('initiative','first' if p['seat']==m.first_seat else 'second' if m.first_seat is not None else 'unknown')]:
                key=(*context,dimension,value)
                b=buckets.setdefault(key,dict(revision=context[0],mode=context[1],population=context[2],player_kind=context[3],dimension=dimension,key=value,entries=0,wins=0,losses=0,draws=0,concedes=0))
                b['entries']+=1;b['draws' if m.winner is None else 'wins' if m.winner==p['seat'] else 'losses']+=1
                b['concedes']+=m.end_reason=='concede'
    totals={}
    for key,b in buckets.items():
        if b['dimension']=='faction':totals[key[:4]]=totals.get(key[:4],0)+b['entries']
    for key,b in buckets.items():
        n=b['entries'];rate=b['wins']/n;z=1.96;den=1+z*z/n
        mid=(rate+z*z/(2*n))/den;half=z*sqrt(rate*(1-rate)/n+z*z/(4*n*n))/den
        b.update(win_rate=round(rate*100,1),usage=round(n/totals[key[:4]]*100,1),
                 win_interval=[round(max(0,mid-half)*100,1),round(min(1,mid+half)*100,1)],sample='样本不足' if n<30 else '仅供观察，非平衡结论')
    return dict(matches=len(matches),rows=sorted(buckets.values(),key=lambda b:(b['population'],b['mode'],b['player_kind'],b['dimension'],-b['entries'])),
                notes=['统计整场比赛，不把小局当作独立样本；平局单列，不计胜场。','使用率以同版本、模式、对手类型及玩家类型的参赛方为分母；镜像对局记两条参赛方记录。','先手指第一小局先手；未采集到的标为unknown，不倒推。','胜率区间为95% Wilson区间；真人、人机、剧情及版本分别统计。','报告不含玩家UID、昵称或私信；历史未采集的比赛不会补造数据。'])

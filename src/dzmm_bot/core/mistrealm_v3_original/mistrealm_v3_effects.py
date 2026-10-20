"""V3 effects, finite choices and simultaneous death resolution.

The work queue is JSON data so a choice survives reconnects and server restarts.
"""
from itertools import combinations
from .mistrealm_v3_cards import ROW_CAPACITY, SPELL_CAPACITY
from .mistrealm_v3_scoring import definition, sealed, row_power_details


def units(state, seat):
    return [c for row in state['players'][seat]['rows'] for c in row]


def location(state, uid):
    for seat,p in enumerate(state['players']):
        for row,cards in enumerate(p['rows']):
            for c in cards:
                if c['id']==uid: return seat,row,c
    return None


def entity(state, uid):
    found=location(state,uid)
    if found: return found[2]
    for p in state['players']:
        for zone in ('hand','deck','discard','spells','resolving'):
            for c in p[zone]:
                if c['id']==uid:return c
    return None


def normal(c):
    return definition(c)['type']=='unit' and not definition(c)['hero']


def reusable(c):
    return normal(c) and 'spy' not in definition(c)['abilities']


def reset(c):
    for key in ('boost','damage','shield','sealed','targets','row','entered'):
        c.pop(key,None)


def detach_targets(state,c):
    for p in state['players']:
        for spell in p['spells']:
            if c['id'] in spell.get('targets',[]):spell['targets'].remove(c['id'])


def discard(state,c):
    detach_targets(state,c)
    reset(c)
    state['players'][c['owner']]['discard'].append(c)


def draw(p,n):
    n=min(n,len(p['deck']))
    for _ in range(n):p['hand'].append(p['deck'].pop())
    return n


def op(kind, **values):
    return dict(kind=kind,**values)


def option(label,ops,card=None,row=-1):
    value=dict(label=label,ops=ops,row=row)
    if card is not None:value['card']=dict(card)
    return value


def target_options(cards, kind, amount=0, **extra):
    return [option(definition(c)['name'],[op(kind,targets=[c['id']],amount=amount,**extra)],c) for c in cards]


def groups(cards,maximum=2):
    return [list(group) for n in range(1,min(maximum,len(cards))+1) for group in combinations(cards,n)]


def label(cards):
    return ' + '.join(definition(c)['name'] for c in cards)


def moves(state,seat,cards,shield=0,own_row=None):
    return [option(f"{definition(c)['name']} → {['近战','远程','攻城'][r]}",
                   [op('move',targets=[c['id']],row=r,amount=shield)],c,r)
            for c in cards for r in range(3) if (own_row is None or r==own_row)
            and location(state,c['id'])[1]!=r and len(state['players'][seat]['rows'][r])<ROW_CAPACITY]


def summon_options(state,seat,group=None,ceiling=None):
    p=state['players'][seat]
    return [option(f"{definition(c)['name']} → {['近战','远程','攻城'][r]}",
                   [op('summon',targets=[c['id']],row=r)],c,r)
            for c in p['deck'] if reusable(c)
            and (group is None or c['card'] in group)
            and (ceiling is None or definition(c)['power']<=ceiling)
            for r in definition(c)['rows'] if len(p['rows'][r])<ROW_CAPACITY]


def revive_options(state,seat,ceiling=3):
    p=state['players'][seat]
    return [option(f"复活 {definition(c)['name']} → {['近战','远程','攻城'][r]}",
                   [op('revive',targets=[c['id']],row=r)],c,r)
            for c in p['discard'] if reusable(c) and definition(c)['power']<=ceiling
            and c.get('revived_round')!=state['round']
            for r in definition(c)['rows'] if len(p['rows'][r])<ROW_CAPACITY]


def menu(state,seat,source):
    """Choices for this card now. Empty unit menus simply skip deployment effects."""
    cid=source['card'];p=state['players'][seat];enemy=state['players'][1-seat]
    own=units(state,seat);foes=units(state,1-seat)
    others=[c for c in own if c['id']!=source['id']]
    here=location(state,source['id']);row=here[1] if here else -1
    def targets(cards,kind,n=0,**extra):return target_options(cards,kind,n,**extra)
    if cid=='c004':return targets(others,'boost',1)
    if cid=='c005':return targets([c for c in others if normal(c)],'shield',2)
    if cid=='c007':return targets(enemy['rows'][1],'damage',1)
    if cid=='c011':return [option(definition(c)['name'],[op('strip_shield',targets=[c['id']]),op('damage',targets=[c['id']],amount=1)],c) for c in foes]
    if cid=='c013':return [option(definition(c)['name'],[op('heal',targets=[c['id']],amount=3),op('shield',targets=[c['id']],amount=1)],c) for c in own]
    if cid in ('c014','c034','c054','c074','c114'):
        return [option(['近战','远程','攻城'][r],[op('mark_row',source=source['id'],row=r)],row=r) for r in range(3)]
    if cid=='c019':return [option(label(g),[op('heal',targets=[c['id'] for c in g],amount=2)],g[0]) for g in groups([c for c in own if c.get('damage',0)>0])]
    if cid=='c020':return [option(label(g),[op('boost',targets=[c['id'] for c in g],amount=1),op('shield',targets=[c['id'] for c in g],amount=1)],g[0]) for g in groups([c for c in own if normal(c)])]
    if cid=='c022':return [option(definition(c)['name'],[op('damage',targets=[c['id']],amount=3 if c.get('damage',0) else 2)],c) for c in foes]
    if cid=='c027':return targets(foes,'strip_boost',2)
    if cid in ('c029','c051','c105','c080'):return revive_options(state,seat)
    if cid=='c030':
        low=[c for r in range(3) for c,d in zip(enemy['rows'][r],row_power_details(state,1-seat,r)) if normal(c) and d['power']<=2]
        return targets(low,'bounce')
    if cid in ('c031','c040'):
        if source.get('resource_used'):return []
        return targets([c for c in p['discard'] if reusable(c) and definition(c)['power']<=4],'recover',source=source['id'])
    if cid=='c032':return targets(enemy['rows'][2],'damage',2 if len(enemy['hand'])>len(p['hand']) else 1)
    if cid=='c033':return [option(definition(c)['name'],[op('strip_boost',targets=[c['id']],amount=2),op('damage',targets=[c['id']],amount=2)],c) for c in foes]
    if cid=='c039':return targets(foes,'seal')
    if cid=='c041':return moves(state,seat,[c for c in others if normal(c)])
    if cid=='c042' and enemy['rows'][row]:return targets(enemy['rows'][row],'damage',1)
    if cid in ('c045','c046','c047'):return summon_options(state,seat,['c045','c046','c047'])
    if cid in ('c048','c049','c050'):return summon_options(state,seat,['c048','c049','c050'])
    if cid=='c052':return moves(state,1-seat,[c for c in foes if normal(c)])
    if cid=='c053':
        options=moves(state,1-seat,[c for c in foes if normal(c)])
        for o in options:o['ops'].append(op('damage',targets=[o['card']['id']],amount=1))
        return options
    if cid=='c059':return moves(state,seat,own,shield=1)
    if cid=='c060':return targets(enemy['spells'],'destroy_spell')+[option('抽1张，然后弃1张',[op('cycle',draw=1,drop=1)])] if p['deck'] else targets(enemy['spells'],'destroy_spell')
    if cid in ('c061','c062','c063'):return summon_options(state,seat,['c061','c062','c063'])
    if cid in ('c064','c065','c066'):return summon_options(state,seat,['c064','c065','c066'])
    if cid=='c068' and len(others)>=3:return targets(others,'heal',2)
    if cid=='c069':return [option('牺牲 '+definition(c)['name'],[op('sacrifice',targets=[c['id']]),op('cycle',draw=2,drop=1)],c) for c in others if normal(c)]
    if cid=='c072':return [option(definition(c)['name'],[op('damage',targets=[source['id']],amount=1),op('shield',targets=[c['id']],amount=2)],c) for c in others if normal(c)]
    if cid=='c073':return [option('牺牲 '+definition(a)['name']+' → '+definition(b)['name'],[op('sacrifice',targets=[a['id']]),op('damage',targets=[b['id']],amount=4)],b) for a in own if normal(a) for b in foes]
    if cid=='c078' and len(own)<len(foes):return summon_options(state,seat,ceiling=2)
    if cid=='c079':return summon_options(state,seat,ceiling=3)
    if cid=='c083':return targets(foes,'damage',2 if p['spells'] else 1)
    if cid=='c084':return [option('置于牌库顶：'+definition(c)['name'],[op('top',targets=[c['id']])],c) for c in p['deck'][-2:]]
    if cid=='c086' and p['instant_count']>0:return targets(others,'shield',1)
    if cid=='c087':return targets(p['spells'],'bounce_spell')
    if cid=='c090':return [option(definition(c)['name'],[op('heal',targets=[c['id']],amount=2)]+([op('shield',targets=[c['id']],amount=1)] if p['spells'] else []),c) for c in others]
    if cid in ('c091','c099'):
        if source.get('resource_used'):return []
        return targets([c for c in p['discard'] if definition(c)['type']=='special' and not definition(c)['persistent'] and not c.get('recovered')],'recover',source=source['id'])
    if cid=='c092':return [option(definition(c)['name'],[op('heal',targets=[c['id']],amount=2 if definition(c)['hero'] else 3)],c) for c in others if c.get('damage',0)]
    if cid=='c093':return [option(definition(a)['name']+' 强化'+(' / '+definition(b)['name']+' 护盾' if b else ''),[op('boost',targets=[a['id']],amount=2)]+([op('shield',targets=[b['id']],amount=1)] if b else []),a) for a in own for b in [None]+[c for c in own if c['id']!=a['id']]]
    if cid=='c094':return [option('放置沉舟回响',[])]
    if cid=='c100':return [option(definition(c)['name'],[op('shield',targets=[c['id']],amount=2),op('cycle',draw=1,drop=1)],c) for c in own if definition(c)['hero']]
    if cid=='c103':return targets(foes,'damage',1)
    if cid=='c106':return targets(others,'boost',1)
    if cid=='c107':return moves(state,seat,[c for c in others if normal(c)],own_row=row)
    if cid=='c111':return targets(foes,'damage',3)
    if cid=='c112':return [option(definition(c)['name'],[op('unseal',targets=[c['id']]),op('heal',targets=[c['id']],amount=3)],c) for c in own]
    if cid in ('c113','c118'):
        pools=enemy['rows'] if cid=='c113' else [own]
        return [option(label(g),[op('mark',source=source['id'],targets=[c['id'] for c in g])],g[0]) for pool in pools for g in groups(pool)]
    if cid=='c115':
        # Ordered pairs allow the caster to select which target receives the marked-row bonus.
        return [option(label(g),[op('damage',targets=[c['id'] for c in g],amount=1)],g[0]) for g in groups(foes) for g in ([g,list(reversed(g))] if len(g)==2 else [g])]
    if cid=='c116':return targets(p['spells']+enemy['spells'],'destroy_spell')
    if cid=='c117':return targets([c for c in own if normal(c)],'bounce')
    if cid=='c119':return targets([c for r in range(3) for c,d in zip(enemy['rows'][r],row_power_details(state,1-seat,r)) if d['power']>=7],'damage',4)
    if cid=='c120':return [option(definition(c)['name'],[op('mark',source=source['id'],targets=[c['id']])],c) for c in foes]
    return []


def settle(state):
    """Remove each simultaneously lethal batch before reevaluating conditions."""
    deaths=[]
    while True:
        batch=[(seat,row,c,bool(sealed(state,c))) for seat in (0,1) for row in range(3)
               for c,d in zip(state['players'][seat]['rows'][row],row_power_details(state,seat,row)) if d['raw']<=0]
        if not batch:break
        for seat,row,c,is_sealed in batch:
            state['players'][seat]['rows'][row].remove(c)
            deaths.append((seat,c['entered'],dict(c),is_sealed))
            p=state['players'][seat]
            if normal(c):
                p['normal_deaths']+=1
                if c['id'] not in p['dead_normal']:p['dead_normal'].append(c['id'])
            if c['id'] not in p['dead']:p['dead'].append(c['id'])
            state['events'].append(f"{definition(c)['name']} 战力归零，阵亡")
            discard(state,c)
    queued=[]
    for seat,_,old,is_sealed in sorted(deaths,key=lambda x:(x[0]!=state['actor'],x[1])):
        c=entity(state,old['id'])
        if not is_sealed and c['card']=='c067' and not c.get('death_used'):
            c['death_used']=True;queued.append(op('draw',seat=c['owner'],amount=1))
        if not is_sealed and c['card']=='c071' and c.get('death_round')!=state['round']:
            c['death_round']=state['round'];queued.append(op('death_boost',seat=seat,source=c['id']))
    state['work'][0:0]=queued


def damage(state,seat,targets,amount):
    enhanced=False
    for uid in targets:
        found=location(state,uid)
        if not found:continue
        side,row,c=found;n=amount
        for spell in state['players'][seat]['spells']:
            if not enhanced and seat==state['actor'] and side!=seat and spell['card']=='c034' and spell.get('row')==row and spell.get('action_used')!=state['action_id']:
                n+=1;spell['action_used']=state['action_id'];enhanced=True
        for spell in state['players'][side]['spells']:
            if spell['card']=='c014' and spell.get('row')==row and n>0 and spell.get('action_used')!=state['action_id']:
                n=max(0,n-1);spell['action_used']=state['action_id']
        absorbed=min(n,c.get('shield',0));c['shield']=c.get('shield',0)-absorbed
        c['damage']=c.get('damage',0)+n-absorbed
        state['events'].append(f"{definition(c)['name']} 受到 {n-absorbed} 点伤害（护盾抵消 {absorbed}）")


def put(state,seat,c,row):
    if len(state['players'][seat]['rows'][row])>=ROW_CAPACITY:raise ValueError('该战列已满（4/4）')
    state['entry_id']+=1;c['entered']=state['entry_id']
    state['players'][seat]['rows'][row].append(c)
    state['entered_action'].append(dict(id=c['id'],seat=seat,row=row))


def remove_unit(state,uid,death=False):
    found=location(state,uid)
    if not found:return
    seat,row,c=found
    if death:
        # Sacrifice bypasses shields; the same death batch and trigger pipeline applies.
        c['damage']=1000
        return
    state['players'][seat]['rows'][row].remove(c);detach_targets(state,c);reset(c)
    state['players'][c['owner']]['hand'].append(c)


def execute(state,seat,item):
    kind=item['kind'];p=state['players'][seat];targets=item.get('targets',[]);n=item.get('amount',0)
    if kind=='draw':draw(p,n)
    elif kind=='cycle':
        if draw(p,item['draw']):state['work'].insert(0,op('discard_choice',seat=seat,count=item['drop']))
    elif kind=='discard_hand':
        for uid in targets:
            c=next((c for c in p['hand'] if c['id']==uid),None)
            if c:p['hand'].remove(c);discard(state,c)
    elif kind=='damage':damage(state,seat,targets,n)
    elif kind in ('boost','heal','shield','strip_boost','strip_shield','seal','unseal'):
        for uid in targets:
            found=location(state,uid)
            if not found:continue
            side,row,c=found
            if kind=='boost':c['boost']=min(4,c.get('boost',0)+n)
            if kind=='heal':c['damage']=max(0,c.get('damage',0)-n)
            if kind=='shield' and not any(s['card']=='c114' and s.get('row')==row for s in state['players'][1-side]['spells']):c['shield']=min(3,c.get('shield',0)+n)
            if kind=='strip_boost':c['boost']=max(0,c.get('boost',0)-n)
            if kind=='strip_shield':c['shield']=0
            if kind=='seal':c['sealed']=True
            if kind=='unseal':
                c.pop('sealed',None)
                for owner in state['players']:
                    for spell in owner['spells']:
                        if spell['card']=='c120' and uid in spell.get('targets',[]):spell['targets'].remove(uid)
    elif kind=='bounce':remove_unit(state,targets[0])
    elif kind=='sacrifice':remove_unit(state,targets[0],True)
    elif kind in ('destroy_spell','bounce_spell'):
        c=entity(state,targets[0])
        if c:
            owner=state['players'][c['owner']]
            if c in owner['spells']:
                owner['spells'].remove(c);reset(c)
                if kind=='destroy_spell':discard(state,c)
                else:owner['hand'].append(c)
    elif kind in ('mark','mark_row'):
        c=entity(state,item['source'])
        if c:
            if kind=='mark':c['targets']=targets
            else:c['row']=item['row']
    elif kind=='move':
        found=location(state,targets[0])
        if found:
            side,old,c=found;row=item['row'];owner=state['players'][side]
            if old!=row and len(owner['rows'][row])<ROW_CAPACITY:
                owner['rows'][old].remove(c);owner['rows'][row].append(c)
                if state['action_id'] not in p['moved_actions']:p['moved_actions'].append(state['action_id'])
                state['entered_action'].append(dict(id=c['id'],seat=side,row=row))
                if n:state['work'].insert(0,op('shield',seat=seat,targets=[c['id']],amount=n))
    elif kind in ('summon','revive'):
        zone=p['deck'] if kind=='summon' else p['discard']
        c=next((c for c in zone if c['id']==targets[0]),None)
        if c and len(p['rows'][item['row']])<ROW_CAPACITY:
            zone.remove(c);reset(c)
            if kind=='revive':c['revived_round']=state['round']
            elif c['id'] not in p['summoned']:p['summoned'].append(c['id'])
            put(state,seat,c,item['row'])
    elif kind=='recover':
        c=next((c for c in p['discard'] if c['id']==targets[0]),None)
        if c:
            p['discard'].remove(c);reset(c);p['hand'].append(c)
            if item.get('source'):entity(state,item['source'])['resource_used']=True
            if definition(c)['type']=='special':c['recovered']=True
    elif kind=='top':
        top=p['deck'][-2:];p['deck']=p['deck'][:-len(top)]
        selected=next(c for c in top if c['id']==targets[0])
        p['deck']=[c for c in top if c is not selected]+p['deck']+[selected]


def queue_menu(state,seat,options,title='选择目标'):
    if options:state['work'].insert(0,op('choice',seat=seat,options=options,title=title))


def deployment(state,seat,c):
    if not location(state,c['id']) or sealed(state,c):return
    p=state['players'][seat];enemy=state['players'][1-seat];cid=c['card'];row=location(state,c['id'])[1]
    automatic=[]
    if 'spy' in definition(c)['abilities'] and not c.get('spy_used'):
        c['spy_used']=True;automatic=[op('draw',amount=2)]
    if cid in ('c002','c044','c057') or (cid=='c003' and len(p['rows'][row])==1):automatic=[op('shield',targets=[c['id']],amount=1)]
    if cid=='c006' and len(p['rows'][row])>=3 or cid=='c009' or cid=='c085' and p['spell_count']>0:automatic=[op('cycle',draw=1,drop=1)]
    if cid=='c026' and len(units(state,seat))==1 and not c.get('resource_used'):
        c['resource_used']=True;automatic=[op('draw',amount=1)]
    if cid=='c042' and not enemy['rows'][row]:automatic=[op('boost',targets=[c['id']],amount=1)]
    if cid=='c070' and enemy['dead'] and not c.get('resource_used'):
        c['resource_used']=True;automatic=[op('draw',amount=1)]
    if cid=='c078' and len(units(state,seat))>=len(units(state,1-seat)):automatic=[op('boost',targets=[c['id']],amount=1)]
    if cid=='c082' and p['instant_count']>0:automatic=[op('boost',targets=[c['id']],amount=2)]
    if cid=='c102':automatic=[op('shield',targets=[c['id']],amount=1)]
    for item in automatic:item['seat']=seat
    if automatic:state['work'][0:0]=automatic;return
    options=menu(state,seat,c)
    if cid in ('c061','c062','c063','c064','c065','c066'):
        if options:state['work'].insert(0,op('repeat_menu',seat=seat,source=c['id'],exclude=[]))
    if cid in ('c041','c052','c069','c072','c087','c107','c045','c046','c047','c048','c049','c050','c061','c062','c063','c064','c065','c066') and options:options.append(option('跳过',[op('cancel_repeat')] if 'muster' in definition(c)['abilities'] else []))
    queue_menu(state,seat,options)


def drain(state):
    while state['work'] and not state['pending']:
        item=state['work'].pop(0);seat=item.get('seat',state['actor']);kind=item['kind'];p=state['players'][seat]
        if kind=='choice':
            options=item['options']
            for index,o in enumerate(options):
                o['token']=str(index)
                targets=dict.fromkeys(uid for effect in o['ops'] for uid in effect.get('targets',[]))
                hints=[]
                for uid in targets:
                    found=location(state,uid)
                    if found:
                        side,row,c=found;slot=state['players'][side]['rows'][row].index(c)
                        power=row_power_details(state,side,row)[slot]['power']
                        hints.append(f"{'己方' if side==seat else '敌方'}{['近战','远程','攻城'][row]}{slot+1}位 · 战力{power} · 盾{c.get('shield',0)}")
                o['hint']=' / '.join(hints)
            state['pending']=dict(actor=seat,kind='v3',title=item['title'],options=options,continuation='finish_action')
        elif kind=='deploy':deployment(state,seat,entity(state,item['source']))
        elif kind=='cancel_repeat':state['work']=[x for x in state['work'] if x['kind']!='repeat_menu']
        elif kind=='spell_menu':
            c=entity(state,item['source'])
            queue_menu(state,seat,menu(state,seat,c),definition(c)['name']+'：选择目标')
        elif kind=='repeat_menu':
            c=entity(state,item['source']);options=menu(state,seat,c)
            if options:queue_menu(state,seat,options+[option('结束召集',[])],'继续召集（剩余1张）')
        elif kind=='second_move':
            options=moves(state,seat,[c for c in units(state,seat) if c['id']!=item['exclude']],shield=1)
            queue_menu(state,seat,options+[option('结束转阵',[])],'可再移动一名不同的单位')
        elif kind=='discard_choice':
            count=min(item['count'],len(p['hand']))
            if count:queue_menu(state,seat,[option('弃置 '+label(list(g)),[op('discard_hand',targets=[c['id'] for c in g])],g[0]) for g in combinations(p['hand'],count)],'选择弃置的手牌')
        elif kind=='death_boost':queue_menu(state,seat,target_options(units(state,seat),'boost',2),'阵亡：选择强化目标')
        elif kind=='finish_spell':
            c=entity(state,item['source']);p['resolving'].remove(c);discard(state,c)
            for unit in units(state,seat):
                if unit['card']=='c089' and not sealed(state,unit) and unit.get('growth_round',0)<3:
                    unit['growth_round']=unit.get('growth_round',0)+1
                    execute(state,seat,op('boost',targets=[unit['id']],amount=1))
            for spell in list(p['spells']):
                if spell['card']=='c094' and spell.get('healed_round',0)<2:
                    injured=sorted((c for c in units(state,seat) if c.get('damage',0)),key=lambda c:(-c['damage'],c['entered'],c['id']))
                    if injured:execute(state,seat,op('heal',targets=[injured[0]['id']],amount=1));spell['healed_round']=spell.get('healed_round',0)+1
        elif kind=='end_triggers':
            for side in (seat,1-seat):
                for spell in list(state['players'][side]['spells']):
                    if spell['card']=='c054' and side!=seat:
                        candidates=[x for x in state['entered_action'] if x['seat']==seat and x['row']==spell.get('row') and location(state,x['id']) and location(state,x['id'])[:2]==(seat,x['row'])]
                        if candidates:state['work'].append(op('damage',seat=side,targets=[candidates[0]['id']],amount=1))
            state['work'].append(op('end_heal',seat=seat))
        elif kind=='end_heal':
            if p['normal_deaths']>state['dead_before'][seat]:
                for spell in p['spells']:
                    if spell['card']=='c074':
                        injured=sorted((c for c in p['rows'][spell.get('row',0)] if c.get('damage',0)),key=lambda c:(-c['damage'],c['entered'],c['id']))
                        if injured:state['work'].append(op('heal',seat=seat,targets=[injured[0]['id']],amount=1))
        else:execute(state,seat,item)
        settle(state)


def start_action(state,seat):
    state['actor']=seat;state['action_id']+=1;state['entered_action']=[];state['events']=[]
    state['dead_before']=[p['normal_deaths'] for p in state['players']]


def can_play(state,seat,c,row):
    d=definition(c);p=state['players'][seat]
    if type(row) is not int:return False
    if d['type']=='unit':
        destination=1-seat if 'spy' in d['abilities'] else seat
        return row in d['rows'] and len(state['players'][destination]['rows'][row])<ROW_CAPACITY
    if d['type']!='special' or row!=-1:return False
    return (not d['persistent'] or len(p['spells'])<SPELL_CAPACITY) and bool(menu(state,seat,c))


def play_card(state,seat,c,row,rng):
    d=definition(c);p=state['players'][seat]
    if not can_play(state,seat,c,row):raise ValueError('无法出牌：战列已满、术位已满或没有合法目标')
    start_action(state,seat);p['hand'].remove(c)
    if d['type']=='unit':
        put(state,1-seat if 'spy' in d['abilities'] else seat,c,row)
        state['work']=[op('deploy',seat=seat,source=c['id']),op('end_triggers',seat=seat)]
    else:
        p['spell_count']+=1
        if d['persistent']:p['spells'].append(c)
        else:p['instant_count']+=1;p['resolving'].append(c)
        state['work']=[op('spell_menu',seat=seat,source=c['id'])]
        if not d['persistent']:state['work'].append(op('finish_spell',seat=seat,source=c['id']))
        state['work'].append(op('end_triggers',seat=seat))
    settle(state);drain(state)


def choose(state,seat,token,rng):
    pending=state['pending']
    if not pending or pending['actor']!=seat:raise ValueError('当前无需选择')
    selected=next((o for o in pending['options'] if o['token']==token),None)
    if selected is None:raise ValueError('选择已失效')
    state['pending']=None
    state['work'][0:0]=[dict(item,seat=seat) for item in selected['ops']]
    drain(state)


def can_lead(state,seat):
    p=state['players'][seat]
    return not p['leader_used'] and bool(menu(state,seat,dict(card=p['leader'],id='leader')))


def leader(state,seat,rng):
    p=state['players'][seat]
    if not can_lead(state,seat):raise ValueError('领袖已使用或没有合法目标')
    options=menu(state,seat,dict(card=p['leader'],id='leader'))
    start_action(state,seat);p['leader_used']=True
    # Leaders are not card entities. Their own once-per-match flag is sufficient.
    for o in options:
        if p['leader']=='c059':o['ops'].append(op('second_move',exclude=o['card']['id']))
        for item in o['ops']:
            if item.get('source')=='leader':item['source']=None
    state['work']=[op('choice',seat=seat,options=options,title='领袖：选择目标'),op('end_triggers',seat=seat)]
    drain(state)

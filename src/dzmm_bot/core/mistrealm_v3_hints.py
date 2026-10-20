"""Read-only player hints derived from authoritative card state."""
from .mistrealm_v3_scoring import definition, sealed
from . import mistrealm_v3_effects as effects

CONDITIONAL_UNITS={'c001','c003','c010','c012','c015','c016','c017','c018','c021','c035','c036','c038','c055','c058','c075','c096','c097','c109','c110'}


def card_status(state,seat,card,zone,detail=None):
    p=state['players'][seat];enemy=state['players'][1-seat];cid=card['card'];result=[]
    def add(text,short,tone='neutral'):result.append(dict(text=text,short=short,tone=tone))
    on_board=zone=='rows';muted=on_board and sealed(state,card)
    if muted:add('已封印：自身技能暂不生效','已封印','off')
    limit=None
    if cid=='c043':limit=('移动抽牌',card.get('move_draw_round')==state['round'],'本小局')
    if cid=='c089':limit=('部署抽牌',card.get('young_draw_used',False),'整场')
    if cid=='c093':limit=('祝祷施放',p.get('prayer_round')==state['round'],'本小局')
    if cid=='c050':limit=('移动回手',card.get('bounce_round')==state['round'],'本小局')
    if cid=='c067':limit=('阵亡抽牌',card.get('death_round')==state['round'],'本小局')
    if cid=='c085':limit=('交换',card.get('exchange_used',False),'整场')
    if cid in ('c026','c031','c040','c091','c099'):limit=('资源技能',card.get('resource_used',False),'整场')
    if 'spy' in definition(card)['abilities']:limit=('间谍抽牌',card.get('spy_used',False),'整场')
    if limit:
        name,used,scope=limit
        add(f'{name}：{scope}{"已使用" if used else "剩余1次"}',f'{"回手" if cid=="c050" else name[:2]}{"已用" if used else "1次"}','off' if used else 'ready')
    if card.get('ritualist_used'):
        add('湖心仪师施放：整场已使用，不能再次被湖心仪师施放','仪师已用','off')
    if definition(card)['type']=='unit' and card.get('revived_round')==state['round']:
        add('本小局已复活，不能再次复活','复活已用','off')
    if zone=='spells':
        counters={'c014':('入场抽牌','entry_draws',2),'c054':('封路伤害','trap_used',3),'c094':('即时术强化','healed_round',2),'c114':('灰幕伤害','ticks',3)}
        if cid in counters:
            name,key,total=counters[cid];left=max(0,total-card.get(key,0))
            add(f'{name}：剩余{left}/{total}次',f'剩{left}次','ready' if left else 'off')
            if cid=='c114':
                if enemy['passed']:add('对方已停手，停止扣血','已停止','off')
                elif not any(effects.location(state,uid) for uid in card.get('targets',[])):add('目标已离场，停止扣血','无目标','off')
        if cid=='c034':
            left=sum(effects.location(state,uid) is not None for uid in card.get('targets',[]))
            add(f'仍有{left}名单位的下一次伤害＋2标记',f'标记{left}名','ready' if left else 'off')
    if on_board and detail and (cid in CONDITIONAL_UNITS or 'bond' in definition(card)['abilities']):
        gain=detail.get('intrinsic',0)
        add(f'自身条件效果：{"已生效，战力＋"+str(gain) if gain else "未生效"}',f'条件＋{gain}' if gain else '条件未生效','ready' if gain else 'off')
    if cid=='c098' and on_board:
        add(f'空手加成：{"已生效" if not p["hand"] and not muted else "未生效"}', '空手生效' if not p['hand'] and not muted else '空手未生效','ready' if not p['hand'] and not muted else 'off')
    if zone=='hand':
        condition=None
        if cid in ('c082','c083','c086'):condition=('本小局已打出即时术',p['instant_count']>0)
        if cid=='c056':condition=('本小局已打出持续术',p['spell_count']>p['instant_count'])
        if cid in ('c081','c089'):condition=('本小局己方已有牌进入弃牌区',p.get('discarded_this_round',False))
        if condition:
            text,met=condition;add(f'部署条件：{text}（{"已满足" if met else "未满足"}）','条件已满足' if met else '条件未满足','ready' if met else 'off')
    return result


def unavailable_reason(state,seat,card):
    p=state['players'][seat];d=definition(card)
    if state['phase']!='playing':return '当前阶段不能出牌'
    if p['passed']:return '你已停手，本小局不能继续出牌'
    if state['pending']:return '请先完成当前选择' if state['pending']['actor']==seat else '等待对手完成选择'
    if state['turn']!=seat:return '等待对手行动'
    if d['type']=='unit':
        if card['card']=='c076' and sum(effects.normal(c) for c in effects.units(state,seat)+effects.units(state,1-seat))<2:return '双方场上合计需要两名普通单位用于献祭'
        side=1-seat if 'spy' in d['abilities'] else seat
        if all(len(state['players'][side]['rows'][r])>=4 for r in d['rows']):return '可部署的战列已满（每排4位）'
    else:
        if card['card']=='c093' and p.get('prayer_round')==state['round']:return '本小局已施放过碎镜祝祷，下小局可再次施放'
        if d['persistent'] and len(p['spells'])>=3:return '己方持续术位已满（3/3）'
        if not effects.menu(state,seat,card):return '没有合法目标，或尚未满足这张术卡的使用条件'
    return ''


def choice_guidance(state,seat,pending):
    """Annotate only the acting player's options; no hidden identities escape."""
    kinds={effect['kind'] for o in pending['options'] for effect in o['ops']}
    if 'move' in kinds:prompt='选择单位及移动目的战列'
    elif 'devour' in kinds:prompt='选择双方场上两名普通单位作为献祭目标'
    elif 'sacrifice' in kinds:prompt='选择献祭目标及后续效果目标'
    elif 'boost' in kinds and kinds <= {'boost','cancel_repeat'}:prompt='选择要强化的己方单位或目标组合'
    elif 'damage' in kinds:prompt='选择伤害目标或目标战列'
    elif kinds & {'revive','recover','recast','return_deck','recycle','exchange'}:prompt='选择要取用或交换的卡牌'
    elif 'summon' in kinds:prompt='选择要召集的单位及部署战列'
    elif 'mark_row' in kinds:prompt='选择效果作用的战列'
    else:prompt=pending['title']
    pending['prompt']=prompt
    for choice in pending['options']:
        ids=list(dict.fromkeys(uid for op in choice['ops'] for uid in (op.get('targets',[])+([op['source']] if op['kind']=='deploy' else []))))
        choice['target_ids']=[uid for uid in ids if effects.location(state,uid) or any(c['id']==uid for p in state['players'] for c in p['spells'])]
        sides=[]
        for uid in ids:
            found=effects.location(state,uid)
            if found:
                side,_,card=found
            else:
                found=next(((i,c) for i,p in enumerate(state['players']) for zone in ('hand','deck','discard','spells','resolving') for c in p[zone] if c['id']==uid),None)
                if not found:continue
                side,card=found
            board=effects.location(state,uid)
            zone='战场' if board else next(z for z in ('hand','deck','discard','spells','resolving') if card in state['players'][side][z])
            detail=dict(id=uid,card=card['card'],side='own' if side==seat else 'enemy',label=definition(card)['name'],zone={'hand':'手牌','deck':'牌库','discard':'弃牌区','spells':'持续术区','resolving':'结算区'}.get(zone,zone))
            if board:
                detail.update(row=board[1],power=effects.row_power_details(state,side,board[1])[state['players'][side]['rows'][board[1]].index(card)]['power'])
            sides.append(detail)
        for op in choice['ops']:
            if op['kind']=='mark_row':
                source=effects.entity(state,op['source'])
                sides.append(dict(side='enemy' if source['card']=='c054' else 'own',label=['近战','远程','攻城'][op['row']]))
        choice['target_sides']=sides
        choice['selection_hint']=f'已选{len(ids)}张牌' if ids else '已选择此效果'
        changes=[]
        for op in choice['ops']:
            kind=op['kind'];amount=op.get('amount',0)
            if kind=='move':
                changes.append('移至'+['近战','远程','攻城'][op['row']])
                if amount:changes.append('强化＋'+str(amount))
            if kind in ('boost','damage','draw') and amount:changes.append({'boost':'强化＋','damage':'伤害','draw':'抽牌'}[kind]+str(amount))
        choice['effect_hint']=' · '.join(dict.fromkeys(changes))
        choice['preview'],choice['preview_note']=choice_preview(state,seat,choice)
    annotate_multi_select(pending)
    pending['target_reasons']=target_reasons(state,seat,pending)


def annotate_multi_select(pending):
    """Expose individual selectable entities, retaining authoritative option tokens."""
    selections=[]
    for choice in pending['options']:
        ops=[op for op in choice['ops'] if op['kind']!='cancel_repeat']
        if not ops:selections.append([]);continue
        if choice.get('row',-1)!=-1 or not choice.get('card'):return
        if len(ops)==1 and ops[0]['kind'] in ('boost','damage','mark','devour'):
            selections.append(ops[0].get('targets',[]))
        elif ops[-1]['kind']=='boost' and all(op['kind']=='return_deck' for op in ops[:-1]) and len(ops)>1:
            selections.append([uid for op in ops[:-1] for uid in op['targets']])
        else:return
    if not selections or max(map(len,selections))<2:return
    targets={t['id']:t for o in pending['options'] for t in o['target_sides'] if 'id' in t}
    ids=list(dict.fromkeys(uid for selection in selections for uid in selection))
    if any(uid not in targets for uid in ids):return
    ordered=len({tuple(sorted(x)) for x in selections})<len(selections)
    pending['multi_select']=dict(cards=[targets[uid] for uid in ids],minimum=min(map(len,selections)),maximum=max(map(len,selections)),ordered=ordered)
    pending['prompt']='逐张选择要洗回牌库的普通单位' if any(op['kind']=='return_deck' for o in pending['options'] for op in o['ops']) else pending['prompt'].replace('或目标组合','').replace('选择','逐张选择',1)
    for choice,ids in zip(pending['options'],selections):
        choice['select_ids']=ids
        choice['selection_hint']=f'已选{len(ids)}张牌'


def choice_preview(state,seat,choice):
    """Resolve only the first public step on a copy; never predict hidden draws."""
    from copy import deepcopy
    from .mistrealm_v3_feedback import board_snapshot
    ops=choice['ops']
    if not ops:return [],''
    first=ops[0];kind=first['kind']
    safe={'damage','boost','move','bounce','sacrifice','devour','seal','unseal','mark','mark_row','destroy_spell','bounce_spell','revive','summon'}
    if kind not in safe:
        labels={'draw':f"抽取至多{first.get('amount',0)}张牌",'recover':'将所选牌从弃牌区回收到手牌','return_deck':'将所选牌洗回牌库','deploy':'重新触发所选单位的部署效果','exchange':'交换所选手牌与弃牌','recast':'施放所选即时术，随后继续选择目标','bottom':'将所选牌置于牌库底','recycle':'将所选牌洗回牌库'}
        return [labels[kind]] if kind in labels else [],'后续目标或连锁效果按实际结算'
    # Historical logs and nested pending options are irrelevant to this one step.
    simulated=deepcopy({k:v for k,v in state.items() if k not in ('history','action_log','action_frames','pending','work','effect_cues','events')})
    simulated.update(work=[],events=[],pending=None)
    before=board_snapshot(simulated)
    # Marked targets can be removed during simulated deaths; keep choice ops untouched.
    effects.execute(simulated,seat,deepcopy(first))
    effects.settle(simulated)
    after=board_snapshot(simulated);lines=[]
    targets=effects.damage_targets(state,seat,first.get('targets',[])) if kind=='damage' else first.get('targets',[])
    for uid in dict.fromkeys(targets+([first['source']] if kind=='devour' else [])):
        old=before.get(uid);new=after.get(uid);c=effects.entity(state,uid)
        if not c:continue
        name=definition(c)['name']
        if old and not new:
            lines.append(name+('：返回原持有者手牌' if kind=='bounce' else '：将被献祭' if kind in ('sacrifice','devour') else '：战力归零，将阵亡'))
        elif old and new:
            text=f"{name}：战力 {old['power']} → {new['power']}"
            if kind=='move':text+=' · 移至'+['近战','远程','攻城'][new['row']]
            if kind=='seal':text+=' · 封印'
            lines.append(text)
        elif new:lines.append(f"{name}：{'复活' if kind=='revive' else '召集'}至{['近战','远程','攻城'][new['row']]} · 战力{new['power']}")
        elif kind in ('destroy_spell','bounce_spell'):lines.append(name+('：摧毁' if kind=='destroy_spell' else '：返回原持有者手牌'))
    if kind=='mark_row':
        source=effects.entity(state,first['source']);lines.append(('敌方' if source['card']=='c054' else '己方')+['近战','远程','攻城'][first['row']]+'排：设置持续术效果')
    return lines,'仅预览当前步骤；后续触发可能改变结果' if simulated['work'] or len(ops)>1 or state['work'] else '当前步骤预览'


def target_reasons(state,seat,pending):
    """Explain public candidates absent from legal options without inventing targets."""
    ops=[op for o in pending['options'] for op in o['ops']]
    kinds={op['kind'] for op in ops};allowed={uid for o in pending['options'] for uid in o['target_ids']}
    sources={op.get('cue_source') for op in ops};reasons={}
    candidates=[(i,'rows',c) for i in (0,1) for c in effects.units(state,i)]
    if kinds & {'revive','recover','return_deck','recast','exchange','recycle'}:
        candidates.extend((seat,'discard',c) for c in state['players'][seat]['discard'])
    all_ids={uid for op in ops for uid in op.get('targets',[])}
    for side,zone,c in candidates:
        uid=c['id']
        if uid in allowed or uid in all_ids:continue
        reason='此牌不符合当前效果的目标条件'
        if 'move' in kinds:
            found=effects.location(state,uid)
            if not effects.normal(c):reason='只能移动普通单位，英雄不可选'
            elif found and all(r==found[1] or len(lane)>=4 for r,lane in enumerate(state['players'][side]['rows'])):reason='其他战列已满，无法移动'
        if zone=='discard' and 'revive' in kinds:
            if not effects.reusable(c):reason='只能复活普通非间谍单位'
            elif c.get('revived_round')==state['round']:reason='本小局已复活过，不能再次复活'
            elif 'c051' in sources and definition(c)['power']>4:reason='基础战力超过4，不能被此效果复活'
            elif all(len(state['players'][seat]['rows'][r])>=4 for r in definition(c)['rows']):reason='可复活至的战列已满'
        if 'damage' in kinds and side==seat and not any(effects.location(state,uid) and effects.location(state,uid)[0]==seat for uid in all_ids):reason='此效果只能选择敌方目标'
        if kinds <= {'boost','cancel_repeat'} and side!=seat:reason='此效果只能强化己方单位'
        reasons[uid]=reason
    return reasons

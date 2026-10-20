"""Version 3 lifecycle; old room engines remain unchanged."""
from copy import deepcopy
import random
import json
from .mistrealm_v3_cards import validate_deck
from .mistrealm_v3_scoring import definition, row_power_details, score_rows
from . import mistrealm_v3_effects as effects
from .mistrealm_v3_hints import card_status, unavailable_reason, choice_guidance

TURN_MS = 60_000
WAIT_MS = 30 * 60_000
FIELDS = {
    'join': {'uid', 'deck'}, 'select_deck': {'deck'}, 'lock': set(), 'unlock': set(),
    'first': {'seat'}, 'mulligan': {'cards'}, 'play': {'card', 'row'},
    'pass': set(), 'concede': set(), 'leave':set(), 'rematch':set(), 'choose': {'option'}, 'leader': set(),
}


def _snapshot(deck):
    if not isinstance(deck, dict): raise ValueError('请选择合法牌组')
    snapshot=validate_deck(deck.get('faction'), deck.get('leader'), deck.get('counts'))
    if deck.get('deck_id'): snapshot['deck_id']=deck['deck_id']
    return snapshot


def _player(uid, deck):
    if not isinstance(uid, str) or not uid or len(uid) > 255: raise ValueError('无效玩家')
    return dict(uid=uid, selection=_snapshot(deck), locked=False, hand=[], deck=[], discard=[],
                rows=[[], [], []], supports=[[], [], []], leader_horns=[False]*3,
                passed=False, rematch=False, leader_used=False, leader_disabled=False, mulligan_done=False, spells=[], resolving=[], melee_hits=0, moved_actions=[], dead_normal=[], normal_deaths=0, dead=[], death_counts={}, summoned=[], instant_count=0, spell_count=0, discarded_this_round=False)


def new_state(host, deck_snapshot, now_ms):
    return dict(rules_version=3, balance_revision=2, version=0, phase='waiting', players=[_player(host, deck_snapshot), None],
                lives=[2, 2], round=0, turn=None, first=None, chooser=None, winner=None,
                weather=[], pending=None, deadline_ms=now_ms+WAIT_MS, server_time_ms=now_ms,
                history=[], action_log=[], actor=0, action_id=0, entry_id=0, work=[], events=[], entered_action=[], dead_before=[0,0])


def _log(state, kind, text, seat=None, card=None, details=None):
    # Public history only: never store hands, draw results or private choice options.
    log=state.setdefault('action_log',[])
    log.append(dict(id=len(log)+1, round=state['round'], kind=kind, seat=seat,
                    card=card, text=text, details=list(details or []),
                    effects=deepcopy(state.get('effect_cues',[])) if kind in ('play','leader','choose') else []))


def _remember_frame(state, previous, action=None, payload=None, seat=None):
    log=state.get('action_log',[])
    new=log[len(previous.get('action_log',[])):]
    if not new or not state['round']: return
    event=next((e for e in new if e['kind'] in ('play','leader')),None)
    board={k:deepcopy(state[k]) for k in ('phase','round','lives','turn','winner','events')}
    board['players']=[]
    for side,p in enumerate(state['players']):
        public={k:deepcopy(p[k]) for k in ('rows','spells','discard','passed','leader_used')}
        public.update(hand_count=len(p['hand']),deck_count=len(p['deck']),row_scores=score_rows(state,side))
        public['score']=sum(public['row_scores'])
        for row,cards in enumerate(public['rows']):
            for card,detail in zip(cards,row_power_details(state,side,row)):
                card.update(power=detail['power'],power_detail=detail,ui_status=card_status(state,side,card,'rows',detail))
        for card in public['spells']:card['ui_status']=card_status(state,side,card,'spells')
        for card in public['discard']:card['ui_status']=card_status(state,side,card,'discard')
        board['players'].append(public)
    landing=None
    if action=='play':
        card=next(c for c in previous['players'][seat]['hand'] if c['id']==payload['card'])
        d=definition(card);side=1-seat if 'spy' in d['abilities'] else seat
        if d['type']=='unit':
            landing=dict(seat=side,row=payload['row'],slot=len(previous['players'][side]['rows'][payload['row']]))
        elif d['persistent']:
            landing=dict(seat=seat,row=-1,slot=len(previous['players'][seat]['spells']))
    # Serialize immutable board frames once; subsequent engine deep copies reuse the strings.
    frames=state.setdefault('action_frames',[])
    frames.append(dict(version=state['version'],log_id=log[-1]['id'],event_id=event['id'] if event else None,
                       played=payload['card'] if action=='play' else None,landing=landing,effects=deepcopy(state.get('effect_cues',[])) if action in ('play','choose','leader') else [],board_json=json.dumps(board,separators=(',',':'))))
    # A single AI response executes at most 80 steps. No private hand or deck enters these frames.
    state['action_frames']=frames[-80:]


def _draw(player, count):
    for _ in range(min(count, len(player['deck']))): player['hand'].append(player['deck'].pop())


def _deal(state, now_ms, rng):
    for seat, player in enumerate(state['players']):
        selection = player['selection']
        player.update(faction=selection['faction'], leader=selection['leader'])
        player['deck'] = [dict(id=f'{seat}:{cid}:{i}', card=cid, owner=seat)
                          for cid, count in selection['counts'].items() for i in range(count)]
        rng.shuffle(player['deck'])
        _draw(player, 7)
    state['first'] = rng.randrange(2)
    state['phase'] = 'mulligan'
    state['deadline_ms'] = now_ms + TURN_MS


def _begin_round(state, now_ms, rng):
    state['round'] += 1
    for player in state['players']:
        for row in player['rows']:
            for card in row: effects.discard(state,card)
            row.clear()
        for card in player['spells']: effects.discard(state,card)
        player['spells']=[]
        player.update(passed=False, melee_hits=0, moved_actions=[], dead_normal=[], normal_deaths=0, dead=[], death_counts={}, summoned=[], instant_count=0, spell_count=0, discarded_this_round=False)
        for zone in ('hand','deck','discard'):
            for card in player[zone]:
                card.pop('healed_round',None);card.pop('trap_used',None);card.pop('modifier_used',None)
        if state['round']>1: _draw(player,2)
    state.update(move_count=0,phase='playing',turn=state['first'],deadline_ms=now_ms+TURN_MS,events=[],work=[],pending=None)
    _log(state,'round_start',f"第 {state['round']} 局开始")


def _end_round(state, now_ms, rng):
    scores = [sum(score_rows(state, i)) for i in range(2)]
    winner = None
    if scores[0] != scores[1]: winner = int(scores[1] > scores[0])
    for i in range(2):
        if winner != i: state['lives'][i] -= 1
    state['history'].append(dict(round=state['round'], scores=scores, winner=winner))
    _log(state,'round_end',f"本局结算 · {scores[0]} : {scores[1]}",winner)
    if min(state['lives']) == 0:
        state.update(phase='finished', turn=None, winner=None if state['lives']==[0,0] else int(state['lives'][1]>0), deadline_ms=None)
        return
    state.update(phase='round_result', turn=None,
                 first=winner if winner is not None else rng.randrange(2), deadline_ms=now_ms+5000)


def _end_action(state, seat, now_ms, rng):
    if all(p['passed'] for p in state['players']): _end_round(state, now_ms, rng)
    else:
        state['turn'] = seat if state['players'][1-seat]['passed'] else 1-seat
        state['deadline_ms'] = now_ms + TURN_MS


def apply_action(state, seat, action, payload, now_ms, rng=None):
    rng = rng or random.SystemRandom()
    if type(seat) is not int or seat not in (0,1): raise ValueError('无效座位')
    if action not in FIELDS or not isinstance(payload, dict) or set(payload) != FIELDS[action]:
        raise ValueError('无效行动参数')
    result = deepcopy(state)
    result['effect_cues']=[]
    phase = result['phase']
    if action == 'join':
        if seat != 1 or phase != 'waiting' or result['players'][1] is not None: raise ValueError('房间不可加入')
        if payload['uid'] == result['players'][0]['uid']: raise ValueError('不能与自己对战')
        result['players'][1] = _player(payload['uid'], payload['deck'])
    else:
        player = result['players'][seat]
        if player is None: raise ValueError('玩家尚未加入')
        if action in ('select_deck','lock','unlock'):
            if phase != 'waiting': raise ValueError('双方已锁定牌组')
            if action == 'select_deck':
                if player['locked']: raise ValueError('请先解锁牌组')
                player['selection'] = _snapshot(payload['deck'])
            else: player['locked'] = action == 'lock'
            if all(p and p['locked'] for p in result['players']): _deal(result, now_ms, rng)
        elif action == 'first':
            if phase != 'choose_first' or result['chooser'] != seat: raise ValueError('当前不可选择先手')
            if type(payload['seat']) is not int or payload['seat'] not in (0,1): raise ValueError('无效先手')
            result.update(first=payload['seat'], phase='mulligan', chooser=None, deadline_ms=now_ms+TURN_MS)
        elif action == 'mulligan':
            ids = payload['cards']
            if phase != 'mulligan' or player['mulligan_done']: raise ValueError('当前不可换牌')
            if not isinstance(ids,list) or any(not isinstance(i,str) for i in ids) or len(ids)>2 or len(set(ids))!=len(ids): raise ValueError('最多换两张不同的牌')
            old = [c for c in player['hand'] if c['id'] in ids]
            if len(old) != len(ids): raise ValueError('手牌不存在')
            player['hand'] = [c for c in player['hand'] if c['id'] not in ids]
            _draw(player,len(old))
            player['deck'].extend(old)
            rng.shuffle(player['deck'])
            player['mulligan_done'] = True
            if all(p['mulligan_done'] for p in result['players']): _begin_round(result,now_ms,rng)
        elif action == 'leave':
            if phase not in ('waiting','finished'): raise ValueError('请先认输再离开')
            result.update(phase='closed',deadline_ms=None,turn=None)
        elif action == 'rematch':
            if phase!='finished': raise ValueError('对局尚未结束')
            player['rematch']=True
            if all(p['rematch'] for p in result['players']):
                players=result['players'];version=result['version']
                result=new_state(players[0]['uid'],players[0]['selection'],now_ms)
                result['players'][1]=_player(players[1]['uid'],players[1]['selection'])
                result['version']=version
        elif action == 'concede':
            if phase in ('waiting','finished','closed'): raise ValueError('尚未开局或已经结束')
            for owner in result['players']:
                for card in owner['resolving']:effects.discard(result,card)
                owner['resolving']=[]
            result['work']=[]
            result.update(phase='finished',winner=1-seat,turn=None,deadline_ms=None,pending=None)
            _log(result,'concede','认输',seat)
        else:
            actor=result['pending']['actor'] if result['pending'] else result['turn']
            if phase != 'playing' or actor != seat or (player['passed'] and not result['pending']): raise ValueError('当前不可行动')
            if result['pending'] and action != 'choose': raise ValueError('请先完成卡牌选择')
            previous_events=len(result['events']) if action=='choose' else 0
            played=None
            if action == 'choose': effects.choose(result,seat,payload['option'],rng)
            elif action == 'leader': effects.leader(result,seat,rng)
            if action == 'pass':
                effects.start_action(result,seat)
                player['passed'] = True
                for spell in result['players'][1-seat]['spells']:
                    if spell['card']=='c114':spell['targets']=[]
            elif action == 'play':
                card = next((c for c in player['hand'] if c['id']==payload['card']),None)
                if card is None: raise ValueError('手牌不存在')
                played=definition(card)
                effects.play_card(result,seat,card,payload['row'],rng)
            if action in ('play','leader','pass','choose'):
                cid=card['card'] if action=='play' else player['leader'] if action=='leader' else None
                text=(f"使用 {played['name']}" if action=='play' else
                      f"发动 {definition(dict(card=cid))['name']}" if action=='leader' else
                      '本局停手' if action=='pass' else '完成效果选择')
                if action=='play' and payload['row']>=0:
                    text+=' · '+('对方' if 'spy' in played['abilities'] else '己方')+('近战','远程','攻城')[payload['row']]
                _log(result,action,text,seat,cid,result['events'][previous_events:])
            if not result['pending']: _end_action(result,result['actor'],now_ms,rng)
    result['version'] += 1
    result['server_time_ms'] = now_ms
    _remember_frame(result,state,action,payload,seat)
    return result


def advance(state, now_ms, rng=None):
    rng=rng or random.SystemRandom()
    if state['deadline_ms'] is None or now_ms < state['deadline_ms']: return deepcopy(state)
    result=deepcopy(state)
    if result['phase']=='round_result': _begin_round(result,now_ms,rng)
    elif result['phase']=='choose_first': return apply_action(result,result['chooser'],'first',{'seat':result['chooser']},now_ms,rng)
    elif result['phase']=='mulligan':
        for seat,p in enumerate(result['players']):
            if not p['mulligan_done']: result=apply_action(result,seat,'mulligan',{'cards':[]},now_ms,rng)
        return result
    elif result['phase']=='playing':
        if result['pending']:
            while result['pending']:
                pending=result['pending']
                result=apply_action(result,pending['actor'],'choose',{'option':pending['options'][0]['token']},now_ms,rng)
            return result
        return apply_action(result,result['turn'],'pass',{},now_ms,rng)
    elif result['phase']=='waiting': result.update(phase='closed',deadline_ms=None)
    result['version'] += 1
    result['server_time_ms']=now_ms
    _remember_frame(result,state)
    return result


def project(state, seat):
    if type(seat) is not int or seat not in (0,1) or not state['players'][seat]: raise ValueError('无效座位')
    view={k:deepcopy(state[k]) for k in ('rules_version','version','phase','lives','round','turn','first','chooser','winner','weather','deadline_ms','server_time_ms','history')}
    view['balance_revision']=state.get('balance_revision',1)
    view['events']=deepcopy(state['events'])
    view['action_log']=deepcopy(state.get('action_log',[]))
    view['action_frames']=[{**{k:v for k,v in f.items() if k!='board_json'},'state':json.loads(f['board_json'])}
                           for f in state.get('action_frames',[])]
    view['row_capacity']=4
    view['spell_capacity']=3
    view['you']=seat
    view['seat']=seat
    view['players']=[]
    for index,p in enumerate(state['players']):
        if p is None: view['players'].append(None);continue
        item=dict(uid=p['uid'],locked=p['locked'])
        if 'faction' not in p:
            if index==seat: item['selection']=deepcopy(p['selection'])
        else:
            item.update({k:deepcopy(p[k]) for k in ('faction','leader','leader_used','leader_disabled','rows','supports','leader_horns','passed','mulligan_done','discard','rematch','spells')})
            item.update(hand_count=len(p['hand']),deck_count=len(p['deck']),row_scores=score_rows(state,index))
            item['score']=sum(item['row_scores'])
            for row,cards in enumerate(item['rows']):
                for card,detail in zip(cards,row_power_details(state,index,row)):
                    card['power']=detail['power'];card['power_detail']=detail
                    card['ui_status']=card_status(state,index,card,'rows',detail)
            for card in item['spells']:card['ui_status']=card_status(state,index,card,'spells')
            for card in item['discard']:card['ui_status']=card_status(state,index,card,'discard')
            if index==seat:
                item['hand']=deepcopy(p['hand'])
                for card in item['hand']:
                    card['ui_status']=card_status(state,index,card,'hand')
                    card['unavailable_reason']=unavailable_reason(state,index,card)
        view['players'].append(item)
    pending=state['pending']
    view['pending']=deepcopy(pending) if pending and pending['actor']==seat else ({'actor':pending['actor']} if pending else None)
    if view['pending'] and 'options' in view['pending']:
        choice_guidance(state,seat,view['pending'])
        for option in view['pending']['options']:option.pop('ops',None)
    view['legal_moves']=legal_moves(state,seat)
    return view


def legal_moves(state, seat):
    """Public action hints from the authoritative rules, without hidden card data."""
    player=state['players'][seat];phase=state['phase'];moves=[]
    def add(action,**payload): moves.append(dict(action=action,payload=payload))
    if phase=='waiting':
        add('unlock' if player['locked'] else 'lock');add('leave')
    elif phase=='finished':
        if not player['rematch']: add('rematch')
        add('leave')
    elif phase=='choose_first' and state['chooser']==seat:
        add('first',seat=0);add('first',seat=1)
    elif phase=='mulligan' and not player['mulligan_done']:
        add('mulligan',cards=[])
    elif phase=='playing':
        pending=state['pending']
        if pending:
            if pending['actor']==seat:
                for option in pending['options']:add('choose',option=option['token'])
        elif state['turn']==seat and not player['passed']:
            add('pass')
            if effects.can_lead(state,seat): add('leader')
            for card in player['hand']:
                data=definition(card)
                rows=data['rows'] if data['type']=='unit' else [-1]
                for row in rows:
                    if effects.can_play(state,seat,card,row):add('play',card=card['id'],row=row)
    if phase not in ('waiting','closed','finished'):add('concede')
    return moves

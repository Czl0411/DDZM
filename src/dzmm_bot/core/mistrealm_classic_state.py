"""Isolated, JSON-serializable Classic game state; v1 remains untouched."""
from copy import deepcopy
import random
from .mistrealm_classic_cards import CLASSIC_CARDS, validate_deck
from .mistrealm_classic_scoring import definition, row_power_details, score_rows
from . import mistrealm_classic_effects as effects

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
                passed=False, rematch=False, leader_used=False, leader_disabled=False, mulligan_done=False)


def new_state(host, deck_snapshot, now_ms):
    return dict(rules_version=2, version=0, phase='waiting', players=[_player(host, deck_snapshot), None],
                lives=[2, 2], round=0, turn=None, first=None, chooser=None, winner=None,
                weather=[], pending=None, deadline_ms=now_ms+WAIT_MS, server_time_ms=now_ms,
                history=[])


def _draw(player, count):
    for _ in range(min(count, len(player['deck']))): player['hand'].append(player['deck'].pop())


def _deal(state, now_ms, rng):
    for seat, player in enumerate(state['players']):
        selection = player['selection']
        player.update(faction=selection['faction'], leader=selection['leader'])
        player['deck'] = [dict(id=f'{seat}:{cid}:{i}', card=cid)
                          for cid, count in selection['counts'].items() for i in range(count)]
        rng.shuffle(player['deck'])
        _draw(player, 10)
    effects.leader_setup(state)
    choosers = [i for i, p in enumerate(state['players']) if p['faction'] == 'frost']
    state['first'] = rng.randrange(2)
    state['phase'] = 'mulligan'
    if len(choosers)==1:
        state['chooser'] = choosers[0]
        state['phase'] = 'choose_first'
    state['deadline_ms'] = now_ms + TURN_MS


def _opening(state, rng):
    while state['opening'] and not state['pending']:
        entry=state['opening'].pop(0)
        effects.deploy(state,entry['seat'],entry['card'],entry['row'],rng)
        if state['pending']: state['pending']['continuation']='opening'


def _begin_round(state, now_ms, rng):
    state['round'] += 1
    for player in state['players']:
        candidates=[c for row in player['rows'] for c in row if effects.eligible(c)]
        carry=rng.choice(candidates) if candidates and player['faction']=='beast' else None
        for row in player['rows']:
            for card in list(row):
                if card is not carry:
                    row.remove(card)
                    effects.discard(player,card)
        for row in player['supports']:
            for card in row: effects.discard(player,card)
            row.clear()
        player['passed'] = False
        player['leader_horns'] = [False]*3
    effects.clear_weather(state)
    state.update(phase='playing', turn=state['first'], deadline_ms=now_ms+TURN_MS, opening=[])
    if state['round']==3:
        for seat,player in enumerate(state['players']):
            if player['faction']!='mirror': continue
            candidates=[c for c in player['discard'] if effects.eligible(c)]
            for card in rng.sample(candidates,min(2,len(candidates))):
                player['discard'].remove(card)
                state['opening'].append(dict(seat=seat,card=card,row=definition(card)['rows'][0]))
        _opening(state,rng)


def _end_round(state, now_ms, rng):
    scores = [sum(score_rows(state, i)) for i in range(2)]
    winner = None
    if scores[0] != scores[1]: winner = int(scores[1] > scores[0])
    else:
        ravens = [i for i,p in enumerate(state['players']) if p['faction'] == 'raven']
        if len(ravens) == 1: winner = ravens[0]
    for i in range(2):
        if winner != i: state['lives'][i] -= 1
    state['history'].append(dict(round=state['round'], scores=scores, winner=winner))
    if min(state['lives']) == 0:
        state.update(phase='finished', turn=None, winner=None if state['lives']==[0,0] else int(state['lives'][1]>0), deadline_ms=None)
        return
    if winner is not None and state['players'][winner]['faction'] == 'crown':
        _draw(state['players'][winner], 1)
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
            pending=result['pending']
            if pending and pending.get('source'):
                effects.discard(result['players'][pending['actor']],pending['source'])
            result.update(phase='finished',winner=1-seat,turn=None,deadline_ms=None,pending=None)
        else:
            actor=result['pending']['actor'] if result['pending'] else result['turn']
            if phase != 'playing' or actor != seat or player['passed']: raise ValueError('当前不可行动')
            opening=bool(result['pending'] and result['pending']['continuation']=='opening')
            if result['pending'] and action != 'choose': raise ValueError('请先完成卡牌选择')
            if action == 'choose': effects.choose(result,seat,payload['option'],rng)
            elif action == 'leader': effects.leader(result,seat,rng)
            if action == 'pass': player['passed'] = True
            elif action == 'play':
                card = next((c for c in player['hand'] if c['id']==payload['card']),None)
                if card is None: raise ValueError('手牌不存在')
                effects.play_card(result,seat,card,payload['row'],rng)
            if opening:
                if result['pending']: result['pending']['continuation']='opening'
                _opening(result,rng)
                if not result['pending']: result['deadline_ms']=now_ms+TURN_MS
            elif not result['pending']: _end_action(result,seat,now_ms,rng)
    result['version'] += 1
    result['server_time_ms'] = now_ms
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
    return result


def project(state, seat):
    if type(seat) is not int or seat not in (0,1) or not state['players'][seat]: raise ValueError('无效座位')
    view={k:deepcopy(state[k]) for k in ('rules_version','version','phase','lives','round','turn','first','chooser','winner','weather','deadline_ms','server_time_ms','history')}
    view['you']=seat
    view['seat']=seat
    view['players']=[]
    for index,p in enumerate(state['players']):
        if p is None: view['players'].append(None);continue
        item=dict(uid=p['uid'],locked=p['locked'])
        if 'faction' not in p:
            if index==seat: item['selection']=deepcopy(p['selection'])
        else:
            item.update({k:deepcopy(p[k]) for k in ('faction','leader','leader_used','leader_disabled','rows','supports','leader_horns','passed','mulligan_done','discard','rematch')})
            item.update(hand_count=len(p['hand']),deck_count=len(p['deck']),row_scores=score_rows(state,index))
            item['score']=sum(item['row_scores'])
            for row,cards in enumerate(item['rows']):
                for card,detail in zip(cards,row_power_details(state,index,row)):
                    card['power']=detail['power'];card['power_detail']=detail
            if index==seat:item['hand']=deepcopy(p['hand'])
        view['players'].append(item)
    pending=state['pending']
    view['pending']=deepcopy(pending) if pending and pending['actor']==seat else ({'actor':pending['actor']} if pending else None)
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
            ability=CLASSIC_CARDS[player['leader']]['abilities'][0]
            if not player['leader_used'] and not player['leader_disabled'] and ability not in ('cancel_leader','extra_hand','half_weather'):
                add('leader')
            for card in player['hand']:
                data=definition(card)
                if data['type']=='unit':rows=data['rows']
                elif set(data['abilities'])&{'horn','ritual'}:rows=[r for r in range(3) if not player['supports'][r]]
                elif 'decoy' in data['abilities'] and not any(effects.eligible(c) for r in player['rows'] for c in r):continue
                else:rows=[-1]
                for row in rows:add('play',card=card['id'],row=row)
    if phase not in ('waiting','closed','finished'):add('concede')
    return moves

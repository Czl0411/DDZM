"""Classic effects and persisted choices. Mutates only the action's private copy."""
from .mistrealm_classic_cards import CLASSIC_CARDS
from .mistrealm_classic_scoring import definition, row_powers


def draw(player, count):
    for _ in range(min(count, len(player['deck']))): player['hand'].append(player['deck'].pop())


def eligible(card):
    data=definition(card)
    return data['type']=='unit' and not data['hero']


def discard(player, card):
    card.pop('form', None)
    player['discard'].append(card)


def clear_weather(state):
    for card in state['weather']:
        owner=card.pop('owner');card.pop('row')
        discard(state['players'][owner],card)
    state['weather']=[]


def transform_rows(state):
    for player in state['players']:
        for row in range(3):
            cards=player['rows'][row]
            if not any('ritual' in definition(c)['abilities'] for c in cards+player['supports'][row]): continue
            for card in cards:
                data=definition(card)
                if 'transform' in data['abilities']: card['form']=data['transform']


def _scorch(state, seats, rows, threshold=0):
    candidates=[]
    for seat in seats:
        player=state['players'][seat]
        for row in rows:
            targets=[(seat,row,c,power) for c,power in zip(player['rows'][row],row_powers(state,seat,row)) if eligible(c)]
            if sum(t[3] for t in targets)>=threshold: candidates.extend(targets)
    highest=max((t[3] for t in candidates),default=0)
    for seat,row,card,power in candidates:
        if power==highest:
            player=state['players'][seat]
            player['rows'][row].remove(card)
            discard(player,card)


def _options(cards, rows=False):
    return [dict(token=f"{c['id']}@{row}",card=dict(c),row=row)
            for c in cards if eligible(c) for row in (definition(c)['rows'] if rows else [-1])]


def _choice(state,seat,kind,options,source=None,grave_seat=None):
    if not options:
        if source: discard(state['players'][seat],source)
        return
    state['pending']=dict(actor=seat,kind=kind,options=options,source=source,grave_seat=grave_seat,
                          continuation='finish_action')


def deploy(state,seat,card,row,rng):
    data=definition(card)
    destination=1-seat if 'spy' in data['abilities'] else seat
    state['players'][destination]['rows'][row].append(card)
    transform_rows(state)
    resolve_effects(state,seat,card,rng=rng)


def resolve_effects(state,seat,card,now_ms=None,rng=None):
    player=state['players'][seat]
    data=definition(card)
    abilities=data['abilities']
    if 'spy' in abilities: draw(player,2)
    if 'muster' in abilities:
        group=data['group']
        summoned=[]
        for zone in (player['hand'],player['deck']):
            for member in list(zone):
                if definition(member).get('group')==group:
                    zone.remove(member);summoned.append(member)
        # All group members leave their source zones before deployment: no double pulls.
        for member in summoned:
            player['rows'][definition(member)['rows'][0]].append(member)
        transform_rows(state)
    if 'scorch_melee' in abilities: _scorch(state,[1-seat],[0],10)
    if 'scorch_siege' in abilities: _scorch(state,[1-seat],[2],10)
    if 'medic' in abilities:
        _choice(state,seat,'medic',_options(player['discard'],True),grave_seat=seat)


def play_card(state,seat,card,row,rng):
    player=state['players'][seat];data=definition(card);abilities=data['abilities']
    if type(row) is not int: raise ValueError('无效战列')
    if data['type']=='unit':
        if row not in data['rows']: raise ValueError('不可放入此战列')
        player['hand'].remove(card)
        deploy(state,seat,card,row,rng)
        return
    if data['type']!='special': raise ValueError('不可打出此牌')
    is_support=bool(set(abilities)&{'horn','ritual'})
    if row not in (range(3) if is_support else [-1]): raise ValueError('无效战列')
    if is_support and player['supports'][row]: raise ValueError('此战列已有支援牌')
    if 'decoy' in abilities and not any(eligible(c) for r in player['rows'] for c in r):
        raise ValueError('没有可替换的单位')
    player['hand'].remove(card)
    if is_support:
        player['supports'][row].append(card)
        transform_rows(state)
    elif abilities[0].startswith('weather_'):
        lane=['weather_melee','weather_ranged','weather_siege'].index(abilities[0])
        state['weather'].append(dict(card,row=lane,owner=seat))
    elif 'decoy' in abilities:
        options=[]
        for lane,cards in enumerate(player['rows']):
            for option in _options(cards):
                option['row']=lane;option['token']=f"{option['card']['id']}@{lane}"
                options.append(option)
        _choice(state,seat,'decoy',options,source=card)
    else:
        discard(player,card)
        if 'clear' in abilities: clear_weather(state)
        elif 'scorch' in abilities: _scorch(state,[0,1],[0,1,2])


def choose(state,seat,token,rng):
    pending=state['pending']
    if not pending or pending['actor']!=seat: raise ValueError('当前无需选择')
    option=next((o for o in pending['options'] if o['token']==token),None)
    if option is None: raise ValueError('选择已失效')
    state['pending']=None
    player=state['players'][seat]
    if pending['kind']=='decoy':
        row=player['rows'][option['row']]
        card=next(c for c in row if c['id']==option['card']['id'])
        row[row.index(card)]=pending['source']
        card.pop('form',None)
        player['hand'].append(card)
    else:
        grave=state['players'][pending['grave_seat']]['discard']
        card=next(c for c in grave if c['id']==option['card']['id'])
        grave.remove(card)
        if pending['kind']=='medic': deploy(state,seat,card,option['row'],rng)
        else: player['hand'].append(card)


def leader(state,seat,rng):
    player=state['players'][seat]
    ability=CLASSIC_CARDS[player['leader']]['abilities'][0]
    if player['leader_used'] or player['leader_disabled'] or ability in ('cancel_leader','extra_hand','half_weather'):
        raise ValueError('领袖能力不可用')
    player['leader_used']=True
    if ability=='clear':clear_weather(state)
    elif ability.startswith('horn_'):
        player['leader_horns'][['horn_melee','horn_ranged','horn_siege'].index(ability)]=True
    elif ability in ('steal_grave','recover_grave'):
        grave_seat=1-seat if ability=='steal_grave' else seat
        _choice(state,seat,'recover',_options(state['players'][grave_seat]['discard']),grave_seat=grave_seat)
    elif ability=='shuffle_graves':
        for p in state['players']:
            p['deck'].extend(p['discard']);p['discard']=[]
            rng.shuffle(p['deck'])


def leader_setup(state):
    for seat,player in enumerate(state['players']):
        opposing=state['players'][1-seat]
        player['leader_disabled']='cancel_leader' in CLASSIC_CARDS[opposing['leader']]['abilities']
    for player in state['players']:
        if not player['leader_disabled'] and 'extra_hand' in CLASSIC_CARDS[player['leader']]['abilities']:
            draw(player,1)

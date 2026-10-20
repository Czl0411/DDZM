"""Public, presentation-only changes; never include hand or deck identities."""
from .mistrealm_v3_scoring import row_power_details


def board_snapshot(state):
    cards={}
    for seat,p in enumerate(state['players']):
        if not p:continue
        for row,lane in enumerate(p['rows']):
            for slot,(c,d) in enumerate(zip(lane,row_power_details(state,seat,row))):
                cards[c['id']]=dict(unit=c['id'],card=c['card'],seat=seat,row=row,slot=slot,power=d['power'])
    return cards


def record_changes(state,before,kind,seat,source=None,hand_before=0,targets=()):
    if 'effect_cues' not in state:return
    after=board_snapshot(state);events=[]
    for uid,old in before.items():
        new=after.get(uid)
        if new:
            if old['row']!=new['row'] or old['seat']!=new['seat']:
                events.append(dict(new,kind='move',from_row=old['row']))
            delta=new['power']-old['power']
            if delta:events.append(dict(new,kind='power',amount=delta,before=old['power']))
        else:
            # Only an already public unit can be identified as leaving the field.
            dead=any(c['id']==uid for p in state['players'] for c in p['discard'])
            returned=next((i for i,p in enumerate(state['players']) if any(c['id']==uid for c in p['hand'])),None)
            event=dict(old,kind='death' if dead else 'return' if returned is not None else 'leave')
            if dead and kind in ('sacrifice','devour') and uid in targets:event['reason']='sacrifice'
            if returned is not None:event['destination']=returned
            events.append(event)
            if dead and old['power']:events.append(dict(old,kind='power',amount=-old['power'],before=old['power'],power=0))
    for uid,c in after.items():
        if uid not in before and kind in ('summon','revive'):events.append(dict(c,kind=kind))
    if kind in ('recover','exchange','bounce_spell'):
        for i,p in enumerate(state['players']):
            for c in p['hand']:
                if c['id'] in targets and c['id'] not in before:
                    events.append(dict(kind='recover' if kind!='bounce_spell' else 'return',card=c['card'],unit=c['id'],seat=i,destination=i))
    if kind in ('draw','cycle','recycle_choice'):

        count=len(state['players'][seat]['hand'])-hand_before
        if count>0:events.insert(0,dict(kind='draw',seat=seat,amount=count))
    if events:state['effect_cues'].append(dict(source=source,seat=seat,events=events))

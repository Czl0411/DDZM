"""Opt-in transport deltas; stored history and legacy clients stay unchanged."""
import hashlib
import json


def history_cursor(value):
    state = value['state']
    return {'sync_match': value.get('match_id') or '',
            'sync_log': (state.get('action_log') or [{'id': 0}])[-1]['id'],
            'sync_frame': (state.get('action_frames') or [{'version': 0}])[-1]['version']}


def history_delta(value, cursor):
    state = value['state']
    if state.get('rules_version') != 3 or 'sync_match' not in cursor:
        return value
    current = history_cursor(value)
    try:
        log, frame = int(cursor['sync_log']), int(cursor['sync_frame'])
    except (ValueError, KeyError, TypeError):
        return value
    if not value.get('match_id') or cursor['sync_match'] != current['sync_match'] or not (
            0 <= log <= current['sync_log'] and 0 <= frame <= current['sync_frame']):
        return value
    return {**value, 'history_delta': {'log': log, 'frame': frame}, 'state': {
        **state, 'action_log': [x for x in state.get('action_log', []) if x['id'] > log],
        'action_frames': [x for x in state.get('action_frames', []) if x['version'] > frame],
    }}


def channel_delta(value, after, revision=None):
    current = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()[:24]
    if revision == current:
        return {'unchanged': True, 'revision': current}
    items = value['items']
    ids = [x['id'] for x in items]
    if not after or after not in ids:
        return {**value, 'revision': current}
    return {'delta': True, 'revision': current, 'ids': ids, 'items': items[ids.index(after)+1:],
            'players': {x['player']['uid']: x['player'] for x in items},
            'challenges': {x['id']: x['challenge'] for x in items if 'challenge' in x}}

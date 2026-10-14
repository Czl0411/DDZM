from copy import deepcopy
import importlib
import importlib.util
import pytest


def engine():
    name='dzmm_bot.core.mistrealm_classic_scoring'
    assert importlib.util.find_spec(name), 'Classic derived scoring must exist'
    return importlib.import_module(name)


def board(ids, weather=False, horn=False):
    return {'players': [{'rows': [[{'id':str(i),'card':c} for i,c in enumerate(ids)],[],[]],
                         'supports': [[],[],[]], 'leader_horns': [horn,False,False]},
                        {'rows':[[],[],[]], 'supports':[[],[],[]], 'leader_horns':[False]*3}],
            'weather': [{'row':0}] if weather else []}

@pytest.mark.parametrize('ids,weather,horn,want', [
    (['c001','c001'],False,False,16),
    (['c001','c001','c001'],False,False,36),
    (['c001','c001','c001','c004'],True,True,26),
    (['c001','c001','c001','c004'],False,True,88),
    (['c004','c005'],False,False,9),
    (['c015','c004'],True,True,12),
    (['c106','c003'],False,False,14),
    (['c106','c003'],False,True,16),
    (['c106','c106','c003'],False,False,20),
    (['c108'],True,True,0),
    (['c117'],False,True,0),
])
def test_layered_scoring(ids,weather,horn,want):
    s=board(ids,weather,horn); original=deepcopy(s)
    assert engine().score_rows(s,0)==[want,0,0]
    assert s==original


def test_weather_is_symmetric_and_removal_restores_power_without_accumulation():
    s=board(['c003'],True)
    s['players'][1]['rows'][0]=[{'id':'enemy','card':'c021'}]
    score=engine().score_rows
    assert score(s,0)==score(s,1)==[1,0,0]
    s['weather']=[]
    assert score(s,0)==[6,0,0]
    assert score(s,1)==[7,0,0]
    assert score(s,0)==[6,0,0]


def test_duplicate_horn_sources_never_quadruple():
    s=board(['c003'],False,True)
    s['players'][0]['supports'][0]=[{'id':'horn','card':'c118'}]
    assert engine().score_rows(s,0)==[12,0,0]


def test_power_breakdown_explains_order_and_hero_immunity():
    s=board(['c001','c001','c004','c015'],True,True)
    details=engine().row_power_details(s,0,0)
    assert details[0]==dict(base=4,weather=1,bond=2,morale=1,horn=2,power=6,hero=False)
    assert details[3]==dict(base=10,weather=None,bond=1,morale=0,horn=1,power=10,hero=True)
    assert [d['power'] for d in details]==engine().row_powers(s,0,0)

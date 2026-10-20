from types import SimpleNamespace
from uuid import uuid4
from sqlalchemy import select
from dzmm_bot.core.mistrealm_balance import record_match,summarize
from dzmm_bot.core.schema import MistrealmBalanceMatchRecord as Match
from tests.core.test_mistrealm_api import game,NOW
from tests.core.test_mistrealm_v3 import started
from tests.core.test_mistrealm_bots import start,pulse,act


def test_completed_match_is_durable_idempotent_and_has_no_player_identity(game):
    _,_,factory=game;s=started();s.update(phase='finished',round=3,winner=0,balance_first=1)
    room=SimpleNamespace(id=uuid4(),match_id=uuid4(),state=s)
    with factory() as db:
        record_match(db,room,NOW);db.commit()
        s['players'][0]['selection']['counts']={'c001':20}
        record_match(db,room,NOW);db.commit()
        matches=db.scalars(select(Match)).all()
        assert len(matches)==1 and matches[0].first_seat==1 and matches[0].rounds==3
        assert matches[0].participants[0]['counts']!={'c001':20}
        assert all(set(p)=={'seat','kind','faction','leader','deck','counts'} for p in matches[0].participants)
        room.match_id=uuid4();s['phase']='playing';record_match(db,room,NOW);db.commit()
        assert len(db.scalars(select(Match)).all())==1


def test_bot_concession_is_recorded_once_through_repository(game):
    _,repo,factory=game
    q=start(repo);r=pulse(repo,q['ticket'])['room'];r=act(repo,r,'concede')
    repo.mistrealm_view(__import__('uuid').UUID(r['room_id']),'a',NOW)
    with factory() as db:
        matches=db.scalars(select(Match)).all()
        assert len(matches)==1 and matches[0].population=='pve' and matches[0].end_reason=='concede'
        assert [p['kind'] for p in matches[0].participants]==['human','bot']


def test_reports_separate_modes_versions_opponents_initiative_and_small_samples():
    def match(mode='casual',population='pvp',revision='r2',winner=0):
        return SimpleNamespace(rules_revision=revision,mode=mode,population=population,first_seat=0,winner=winner,end_reason='normal',
          participants=[dict(seat=i,kind='bot' if population=='pve' and i==1 else 'human',faction='same',leader='leader',deck='deck') for i in (0,1)])
    report=summarize([match(),match(winner=None),match(population='pve'),match(mode='ranked'),match(revision='r3')])
    faction=next(r for r in report['rows'] if r['population']=='pvp' and r['mode']=='casual' and r['revision']=='r2' and r['dimension']=='faction')
    assert report['matches']==5
    assert (faction['entries'],faction['wins'],faction['losses'],faction['draws'])==(4,1,1,2)
    assert faction['win_rate']==25 and faction['usage']==100 and faction['sample']=='样本不足'
    assert faction['win_interval'][0]<25<faction['win_interval'][1]
    assert len({r['player_kind'] for r in report['rows'] if r['population']=='pve'})==2
    assert {r['key'] for r in report['rows'] if r['dimension']=='initiative'}=={'first','second'}
    assert summarize([])['rows']==[]


def test_balance_migration_upgrade_and_downgrade():
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine,inspect
    path=Path('migrations/versions/20261018_121_mistrealm_balance.py')
    spec=importlib.util.spec_from_file_location('balance_migration',path)
    migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    engine=create_engine('sqlite://')
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            assert set(c['name'] for c in inspect(connection).get_columns('mistrealm_balance_matches'))==set(Match.__table__.columns.keys())
            migration.downgrade()
            assert 'mistrealm_balance_matches' not in inspect(connection).get_table_names()
    engine.dispose()

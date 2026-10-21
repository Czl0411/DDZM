from tests.core.test_mistrealm_v3_api import client,req


def test_saved_draft_survives_reload_and_rejects_replay_and_wrong_uid(client):
    assert req(client,'a','/expedition').json() is None
    r=req(client,'a','/expedition/start',{});assert r.status_code==200
    run=r.json();body=dict(run_id=run['id'],version=run['version'],action='choose',payload={'index':0})
    saved=req(client,'a','/expedition/actions',body)
    assert saved.status_code==200 and len(saved.json()['deck'])==1
    assert req(client,'a','/expedition').json()==saved.json()
    assert req(client,'a','/expedition/start',{}).json()==saved.json()
    assert req(client,'a','/expedition/actions',body).status_code==409
    assert req(client,'b','/expedition/actions',body).status_code==404
    assert req(client,'b','/expedition').json() is None
    assert req(client,'a','/expedition').json()==saved.json()


def test_explicit_restart_rejects_requests_from_the_old_run(client):
    r=req(client,'a','/expedition/start',{}).json()
    body=dict(run_id=r['id'],version=r['version'],action='restart',payload={})
    fresh=req(client,'a','/expedition/actions',body).json()
    assert fresh['id']!=r['id'] and fresh['version']==r['version']+1
    body.update(version=fresh['version'],action='choose',payload={'index':0})
    assert req(client,'a','/expedition/actions',body).status_code==409
    assert req(client,'a','/expedition').json()==fresh


def test_invalid_draft_does_not_spend_gold_or_change_version(client):
    r=req(client,'a','/expedition/start',{}).json()
    for payload in ({'index':-1},{'index':3},{'index':True},{'index':0,'card':'xv13'}):
        response=req(client,'a','/expedition/actions',dict(run_id=r['id'],version=0,action='choose',payload=payload))
        assert response.status_code==409
    assert req(client,'a','/expedition').json()==r
    assert client.get('/api/mistrealm/v3/expedition').status_code==401

"""Published tutorial remains reproducible under the current server rules."""
import json
from pathlib import Path
from scripts.export_mistrealm_tutorial import build_tutorial


def test_tutorial_matches_engine_and_two_round_finish():
    scenes=build_tutorial()
    exported=json.loads((Path(__file__).resolve().parents[2]/'gamefy/mistrealm/publish/v3/tutorial.json').read_text())
    assert scenes==exported
    assert scenes[-1]['state']['winner']==0
    assert scenes[-1]['state']['lives']==[2,0]
    assert all(scene['state']['deadline_ms'] is None for scene in scenes)
    assert all(not scene['state']['action_frames'] for scene in scenes)

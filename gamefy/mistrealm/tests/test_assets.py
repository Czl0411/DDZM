import json
from pathlib import Path
from dzmm_bot.core.mistrealm_cards import CARDS

ROOT=Path(__file__).resolve().parents[1]/'publish'

def test_catalogue_matches_server_and_assets_exist():
    assert json.loads((ROOT/'cards.json').read_text())==CARDS
    for c in CARDS.values():
        assert (ROOT/c['art']).is_file()
    assert (ROOT/'assets/backgrounds/royal-hall.webp').is_file()
    assert (ROOT/'assets/backgrounds/battle-table.webp').is_file()

def test_no_browser_storage_or_native_form_dependency():
    source=(ROOT/'game.js').read_text()+(ROOT/'client.js').read_text()
    for name in ['localStorage','sessionStorage','indexedDB','document.cookie','location.hash']:
        assert name not in source
    assert '<form ' not in source

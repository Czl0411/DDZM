"""Export v3 cards without replacing the v2 client catalogue."""
import json
from pathlib import Path
from dzmm_bot.core.mistrealm_v3_cards import CARDS, STARTER_DECKS, FACTIONS

path=Path(__file__).resolve().parents[1]/'gamefy/mistrealm/publish/v3/cards.json'
path.parent.mkdir(parents=True,exist_ok=True)
path.write_text(json.dumps(dict(cards=CARDS,transforms={},starters=STARTER_DECKS,factions=FACTIONS,rules_version=3),ensure_ascii=False,indent=2)+'\n')
print(path)

"""Export the authoritative Classic catalogue for the browser."""
import json
from pathlib import Path
from dzmm_bot.core.mistrealm_classic_cards import CLASSIC_CARDS, TRANSFORMS, STARTER_DECKS, FACTIONS

if __name__ == '__main__':
    path = Path(__file__).resolve().parents[1] / 'gamefy/mistrealm/publish/classic/cards.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(cards=CLASSIC_CARDS, transforms=TRANSFORMS,
                                   starters=STARTER_DECKS, factions=FACTIONS),
                               ensure_ascii=False, indent=2) + '\n')
    print(path)

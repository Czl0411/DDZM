"""Release gate: all Classic art must exist, decode and carry a reviewed receipt."""
import hashlib
import json
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

BASE=Path(__file__).resolve().parents[1]


class ClassicAssets(unittest.TestCase):
    def test_complete_unique_reviewed_art_and_resource_budget(self):
        from PIL import Image
        manifest=json.loads((BASE/'art-updates/classic-120-manifest.json').read_text())
        catalogue=json.loads((BASE/'publish/classic/cards.json').read_text())
        cards=catalogue['cards']|catalogue['transforms']
        self.assertEqual(len(cards),122)
        self.assertEqual(set(manifest['cards']),set(cards))
        pending=[cid for cid,e in manifest['cards'].items() if not e['status'].startswith('reviewed')]
        self.assertEqual(pending,[],f'Unreviewed artwork: {pending}')
        hashes=[]
        for cid,card in cards.items():
            receipt=manifest['cards'][cid]
            original=BASE/receipt['original'];art=BASE/receipt['webp']
            self.assertEqual(art.resolve(),(BASE/'publish/classic'/card['art']).resolve())
            self.assertTrue(receipt['prompt'] or receipt.get('reference'),cid)
            for path,kind in [(original,'PNG'),(art,'WEBP')]:
                with Image.open(path) as img:
                    self.assertEqual(img.format,kind);img.load()
                    self.assertGreaterEqual(img.width,512);self.assertGreaterEqual(img.height,768)
            self.assertLess(art.stat().st_size,800*1024)
            hashes.append(hashlib.sha256(art.read_bytes()).hexdigest())
        self.assertEqual(len(set(hashes)),122,'Duplicate illustrations need explicit review, not placeholders')
        size=sum(p.stat().st_size for p in (BASE/'publish').rglob('*') if p.is_file())
        self.assertLess(size,40*1024*1024)
        print(f'Classic package: {size/1024/1024:.2f} MiB, 122 unique decoded artworks')

    def test_original_faction_row_and_effect_icons(self):
        for name in ['crown','raven','frost','beast','mirror','row-melee','row-ranged','row-siege','weather','medic','spy','bond','horn','muster','ritual','scorch']:
            root=ET.parse(BASE/f'publish/assets/classic/ui/{name}.svg').getroot()
            self.assertTrue(root.tag.endswith('svg'))
            self.assertEqual(root.get('viewBox'),'0 0 32 32')


if __name__=='__main__':unittest.main()

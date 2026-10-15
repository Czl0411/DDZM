"""Platform build preserves legacy assets and installs the SDK-safe version selector."""
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT=Path(__file__).resolve().parents[3]

class PlatformBuild(unittest.TestCase):
    def test_isolated_publish_build(self):
        with TemporaryDirectory() as directory:
            subprocess.run([sys.executable,str(ROOT/'scripts/build_mistrealm_platform.py'),directory],check=True)
            out=Path(directory)/'publish';source=ROOT/'gamefy/mistrealm/publish'
            self.assertEqual((out/'legacy.html').read_bytes(),(source/'index.html').read_bytes())
            self.assertIn('./entry.js',(out/'index.html').read_text())
            self.assertTrue((out/'entry.js').exists())
            for name in ['config.js','classic/config.js']:
                self.assertIn('https://49.234.20.159',(out/name).read_text())
            self.assertEqual(len(list((out/'assets/classic').glob('*.webp'))),122)
            self.assertIn("apiBase:''",(source/'classic/config.js').read_text())

if __name__=='__main__':unittest.main()

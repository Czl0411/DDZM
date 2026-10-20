"""Build the versioned platform entry without changing local preview configuration."""
import argparse
import json
from pathlib import Path
import shutil
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path)
    parser.add_argument('--api-base',default='https://49.234.20.159');args=parser.parse_args()
    api_base=args.api_base.rstrip('/');url=urlsplit(api_base)
    if url.scheme!='https' or not url.hostname or url.username or url.password or url.path or url.query or url.fragment:
        parser.error('--api-base must be an HTTPS origin without credentials or path')
    source=ROOT/'gamefy/mistrealm';out=args.output.resolve()
    if out==source or source/'publish' in out.parents:raise ValueError('Use a separate output directory')
    shutil.copytree(source/'publish',out/'publish',dirs_exist_ok=True)
    shutil.copy2(source/'publish/index.html',out/'publish/legacy.html')
    shutil.copy2(source/'platform/index.html',out/'publish/index.html')
    shutil.copy2(source/'platform/entry.js',out/'publish/entry.js')
    for name in ['config.js','classic/config.js','v3/config.js','v3-original/config.js','v3-r1/config.js']:
        (out/'publish'/name).write_text('export const CONFIG={apiBase:'+json.dumps(api_base)+'};\n')
    shutil.copy2(source/'dzmm.json',out/'dzmm.json')
    if (source/'.dzmm').exists():shutil.copytree(source/'.dzmm',out/'.dzmm',dirs_exist_ok=True)
    print(out)

if __name__=='__main__':main()

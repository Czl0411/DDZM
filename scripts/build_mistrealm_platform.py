"""Build the Classic platform entry without changing the local preview or legacy files."""
import argparse
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path);args=parser.parse_args()
    source=ROOT/'gamefy/mistrealm';out=args.output.resolve()
    if out==source or source/'publish' in out.parents:raise ValueError('Use a separate output directory')
    shutil.copytree(source/'publish',out/'publish',dirs_exist_ok=True)
    shutil.copy2(source/'publish/index.html',out/'publish/legacy.html')
    shutil.copy2(source/'platform/index.html',out/'publish/index.html')
    shutil.copy2(source/'platform/entry.js',out/'publish/entry.js')
    for name in ['config.js','classic/config.js']:
        (out/'publish'/name).write_text("export const CONFIG={apiBase:'https://49.234.20.159'};\n")
    shutil.copy2(source/'dzmm.json',out/'dzmm.json')
    if (source/'.dzmm').exists():shutil.copytree(source/'.dzmm',out/'.dzmm',dirs_exist_ok=True)
    print(out)

if __name__=='__main__':main()

import argparse
import json
import re
import shutil
from pathlib import Path
from urllib.parse import urlsplit
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "gamefy-workstation"
PUBLISH = PROJECT / "publish"
STATIC = ROOT / "src" / "dzmm_bot" / "admin" / "static"


def build():
    assets = PUBLISH / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    (PROJECT / "functions").mkdir(exist_ok=True)
    for asset in (STATIC / "workstation").glob("*.png"):
        shutil.copyfile(asset, assets / asset.name)
    shutil.copyfile(STATIC / "workstation.css", PUBLISH / "style.css")
    shutil.copyfile(STATIC / "workstation.js", PUBLISH / "workstation.js")


def check(*, release=False):
    config = json.loads((PROJECT / "dzmm.json").read_text(encoding="utf-8"))
    if not isinstance(config.get("cardId"), int) or config["cardId"] <= 0:
        raise ValueError("dzmm.json cardId must be a positive integer")
    if config.get("publishDir") != "publish" or config.get("functionsDir") != "functions":
        raise ValueError("Unexpected project directories")
    if not (PUBLISH / "index.html").is_file():
        raise ValueError("publish/index.html is required")
    files = sorted(path for path in PUBLISH.rglob("*") if path.is_file())
    allowed = {
        "index.html", "config.js", "game.js", "game.css", "style.css", "workstation.js",
        *(f"assets/{path.name}" for path in (STATIC / "workstation").glob("*.png")),
    }
    if len(files) > 3000 or sum(path.stat().st_size for path in files) > 100 * 1024 * 1024:
        raise ValueError("Project exceeds platform file count or size limit")
    for path in files:
        relative = path.relative_to(PROJECT)
        if path.relative_to(PUBLISH).as_posix() not in allowed:
            raise ValueError(f"Unexpected file in publish directory: {relative}")
        if path.is_symlink() or not all(re.fullmatch(r"[A-Za-z0-9._-]+", part) for part in relative.parts):
            raise ValueError(f"Invalid published path: {relative}")
        if path.stat().st_size > 25 * 1024 * 1024:
            raise ValueError(f"File exceeds 25 MiB: {relative}")
        if path.suffix in {".html", ".js", ".css", ".json"}:
            content = path.read_text(encoding="utf-8")
            if re.search(r"sk-[A-Za-z0-9]{20,}|Bearer\s+[A-Za-z0-9_-]{20,}|-----BEGIN.*PRIVATE KEY", content):
                raise ValueError(f"Possible credential in {relative}")
            if re.search(r"(?:localStorage|sessionStorage|document\.cookie)", content):
                raise ValueError(f"Sandbox-incompatible storage in {relative}")
            for resource in re.findall(r'(?:src|href)="([^"]+)"', content):
                if not resource.startswith("./") or not (path.parent / resource).is_file():
                    raise ValueError(f"Missing or non-relative resource in {relative}: {resource}")
    api_config = (PUBLISH / "config.js").read_text(encoding="utf-8")
    match = re.search(r'apiBaseUrl:\s*"([^"\s]*)"', api_config)
    if match is None:
        raise ValueError("config.js must contain a literal apiBaseUrl string")
    if match[1]:
        endpoint = urlsplit(match[1])
        if endpoint.scheme != "https" or not endpoint.hostname or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment:
            raise ValueError("apiBaseUrl must be an HTTPS base URL without credentials, query or fragment")
    elif release:
        raise ValueError("Release requires a configured HTTPS workstation API base URL")
    return files


def main():
    parser = argparse.ArgumentParser(description="Build and validate the Gamefy workstation project")
    parser.add_argument("--release", action="store_true", help="Require a configured HTTPS data backend")
    args = parser.parse_args()
    build()
    files = check(release=args.release)
    output = ROOT / "output" / "gamefy-workstation-preview.zip"
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.write(PROJECT / "dzmm.json", "dzmm.json")
        for path in files:
            archive.write(path, path.relative_to(PROJECT).as_posix())
    print(f"Validated {len(files)} static files, {sum(path.stat().st_size for path in files):,} bytes")
    print(f"Package: {output}")
    print("Mode: " + ("connected release candidate" if args.release else "preview; verify backend before release"))


if __name__ == "__main__":
    main()

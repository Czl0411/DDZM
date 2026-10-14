from pathlib import Path
import re


def test_only_game_routes_are_streamed_to_core():
    config = (Path(__file__).resolve().parents[2] / "deploy/caddy/dzmm-chess-ip.Caddyfile").read_text()
    handlers = re.findall(
        r"handle (/[^\s]+) \{\s*reverse_proxy ([^\s]+) \{\s*flush_interval (-?\d+)\s*\}\s*\}",
        config,
    )
    assert set(handlers) == {
        ("/api/chess/*", "127.0.0.1:18120", "-1"),
        ("/api/doudizhu/*", "127.0.0.1:18120", "-1"),
        ("/api/drawguess/*", "127.0.0.1:18120", "-1"),
    }
    assert re.search(r"handle \{\s*respond 404\s*\}", config)

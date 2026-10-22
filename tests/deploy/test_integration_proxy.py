from pathlib import Path
import re


def test_integration_route_is_proxied_only_to_admin_service():
    config = (
        Path(__file__).resolve().parents[2]
        / "deploy/caddy/dzmm-chess-ip.Caddyfile"
    ).read_text()

    assert re.search(
        r"handle /api/integration/\* \{\s*"
        r"reverse_proxy 127\.0\.0\.1:18080\s*\}",
        config,
    )
    assert not re.search(
        r"handle /api/integration/\* \{\s*"
        r"reverse_proxy 127\.0\.0\.1:18120",
        config,
    )

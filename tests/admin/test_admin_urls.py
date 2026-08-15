import json
from pathlib import Path
import subprocess


def test_random_event_submission_url_omits_an_empty_status_filter():
    """Fails if selecting '全部' sends status= and Core rejects the request."""
    module = Path("src/dzmm_bot/admin/static/admin_urls.js").resolve()
    script = f"""
const {{ buildRandomEventSubmissionsPath }} = require({json.dumps(str(module))});
console.log(JSON.stringify([
  buildRandomEventSubmissionsPath(2, 20, ""),
  buildRandomEventSubmissionsPath(2, 20, "pending"),
]));
"""

    completed = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout) == [
        "/api/game/random-events/submissions?page=2&page_size=20",
        "/api/game/random-events/submissions?page=2&page_size=20&status=pending",
    ]

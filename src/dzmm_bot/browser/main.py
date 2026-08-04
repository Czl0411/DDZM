import os
from datetime import UTC, datetime
from time import sleep

from dzmm_bot.runtime.settings import Settings

from .core_client import CoreClient
from .session import BrowserSession
from .worker import BrowserWorker


class _UnavailableDesktop:
    def start(self) -> None:
        raise RuntimeError("manual desktop controller is not installed")

    def stop(self) -> None:
        raise RuntimeError("manual desktop controller is not installed")


def main() -> None:
    settings = Settings.from_environment()
    session = BrowserSession(
        settings.browser_profile,
        settings.login_url,
        cdp_port=settings.browser_cdp_port,
    )
    worker = BrowserWorker(
        worker_id=os.environ.get("DZMM_WORKER_ID", "browser-worker-1"),
        core=CoreClient(
            f"http://127.0.0.1:{settings.core_api_port}", settings.core_token
        ),
        session=session,
        desktop=_UnavailableDesktop(),
        clock=lambda: datetime.now(UTC),
    )
    while True:
        worker.run_once()
        sleep(1)


if __name__ == "__main__":
    main()

import os
from time import sleep

from dzmm_bot.runtime.settings import Settings

from .client import DeepSeekChatClient
from .core_client import AICoreClient
from .worker import AIWorker


def main() -> None:
    settings = Settings.from_environment()
    if not settings.deepseek_api_key:
        raise ValueError("DP_API_KEY must be set and nonempty")
    worker = AIWorker(
        os.environ.get("DZMM_AI_WORKER_ID", "ai-worker-1"),
        AICoreClient(f"http://127.0.0.1:{settings.core_api_port}", settings.core_token),
        DeepSeekChatClient(
            settings.deepseek_api_key,
            settings.deepseek_model,
            base_url=settings.deepseek_base_url,
        ),
    )
    while True:
        worker.run_once()
        sleep(1)


if __name__ == "__main__":
    main()

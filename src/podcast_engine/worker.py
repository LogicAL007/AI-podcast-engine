"""Worker entrypoint: ``python -m podcast_engine.worker <stage>``.

Starts a Celery worker that consumes only that stage's queue and imports only that stage's
task module, so a container loads nothing it does not need. ``--healthcheck`` pings the worker
running in the same container (used by the compose healthcheck).
"""

import argparse
import socket
import sys
from collections.abc import Sequence

from podcast_engine.common.config import get_settings
from podcast_engine.common.metrics import start_metrics_server
from podcast_engine.common.queue import Stage, celery_app


def worker_args(
    stage: Stage, *, concurrency: int, log_level: str, pool: str = "prefork"
) -> list[str]:
    """Celery argv for a worker bound to ``stage``.

    ``solo`` runs tasks in the worker process itself: use it for a host worker on Python 3.14
    (where the prefork pool crashes) or one holding a large model such as Chatterbox.
    """
    return [
        "worker",
        "--queues",
        stage.value,
        "--include",
        f"podcast_engine.stages.{stage.value}.tasks",
        "--concurrency",
        str(concurrency),
        "--loglevel",
        log_level.upper(),
        "--pool",
        pool,
    ]


def is_healthy() -> bool:
    """True if this container's worker answers a ping within five seconds."""
    node = f"celery@{socket.gethostname()}"
    replies = celery_app.control.ping(destination=[node], timeout=5)
    return bool(replies)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", nargs="?", type=Stage, choices=list(Stage))
    parser.add_argument("--healthcheck", action="store_true")
    args = parser.parse_args(argv)

    if args.healthcheck:
        return 0 if is_healthy() else 1
    if args.stage is None:
        parser.error("a stage is required unless --healthcheck is given")

    settings = get_settings()
    start_metrics_server(settings.metrics_port)
    celery_app.worker_main(
        worker_args(
            args.stage,
            concurrency=settings.worker_concurrency,
            log_level=settings.log_level,
            pool=settings.worker_pool,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Worker entrypoint: ``python -m podcast_engine.worker <stage> [<stage> ...]``.

Starts a Celery worker that consumes only those stages' queues and imports only their task
modules, so a container loads nothing it does not need. Each stage keeps its own queue (and its
own retries and metrics), so stages can be regrouped across containers without changing anything
else. ``--healthcheck`` pings the worker
running in the same container (used by the compose healthcheck).
"""

import argparse
import socket
import sys
from collections.abc import Sequence

from podcast_engine.common.config import get_settings
from podcast_engine.common.logging import configure_logging, get_logger
from podcast_engine.common.metrics import start_metrics_server
from podcast_engine.common.queue import Stage, celery_app

log = get_logger("worker")


def worker_args(
    stages: Sequence[Stage], *, concurrency: int, log_level: str, pool: str = "prefork"
) -> list[str]:
    """Celery argv for a worker bound to ``stages``.

    ``solo`` runs tasks in the worker process itself: use it for a host worker on Python 3.14
    (where the prefork pool crashes) or one holding a large model such as Chatterbox.
    """
    return [
        "worker",
        "--queues",
        ",".join(stage.value for stage in stages),
        "--include",
        ",".join(f"podcast_engine.stages.{stage.value}.tasks" for stage in stages),
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
    parser.add_argument("stages", nargs="*", type=Stage, choices=list(Stage), metavar="stage")
    parser.add_argument("--healthcheck", action="store_true")
    args = parser.parse_args(argv)

    if args.healthcheck:
        return 0 if is_healthy() else 1
    if not args.stages:
        parser.error("at least one stage is required unless --healthcheck is given")

    settings = get_settings()
    if Stage.VOICE in args.stages:
        from podcast_engine.stages.voice.backends import backend_unavailable

        if problem := backend_unavailable(settings):
            # Stand down without taking a job: voicing waits in the queue for a worker that can
            # do it. Exit 0, so a restart policy of on-failure leaves this worker stopped.
            configure_logging(settings.log_level)
            log.warning("voice_worker_standing_down", backend=settings.tts_backend, reason=problem)
            return 0
    start_metrics_server(settings.metrics_port)
    # Wait out a broker outage however long it lasts (Docker Desktop quit, the laptop slept),
    # instead of exiting after Celery's default 100 tries. A container would be restarted, but
    # the Mac voice worker (`make voice-host`) has nothing to restart it.
    celery_app.conf.broker_connection_retry_on_startup = True
    celery_app.conf.broker_connection_max_retries = None
    celery_app.worker_main(
        worker_args(
            list(dict.fromkeys(args.stages)),
            concurrency=settings.worker_concurrency,
            log_level=settings.log_level,
            pool=settings.worker_pool,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

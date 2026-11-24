import argparse
import socket
import sys
from collections.abc import Sequence

from podcast_engine.common.config import get_settings
from podcast_engine.common.logging import configure_logging, get_logger
from podcast_engine.common.metrics import start_metrics_server
from podcast_engine.common.queue import Stage, celery_app

log = get_logger("worker")

DESCRIPTION = """Start a Celery worker for the given stages (python -m podcast_engine.worker).

It consumes only those stages' queues and imports only their task modules, so a container loads
nothing it does not need. --healthcheck pings the worker running in the same container.
"""


def worker_args(
    stages: Sequence[Stage], *, concurrency: int, log_level: str, pool: str = "prefork"
) -> list[str]:
    """Build the Celery command line for a worker bound to some stages.

    Each stage keeps its own queue (and its own retries and metrics), so stages can be regrouped
    across containers without changing anything else. ``solo`` runs tasks in the worker process
    itself: use it for a host worker on Python 3.14 (where the prefork pool crashes) or one holding
    a large model such as Chatterbox.

    Args:
        stages: The stages whose queues to consume and whose task modules to import.
        concurrency: How many tasks to run at once.
        log_level: Celery's log level.
        pool: Celery's pool: ``prefork``, ``threads`` or ``solo``.

    Returns:
        The arguments for ``celery_app.worker_main``.
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
    """Tell whether this container's worker answers a ping within five seconds.

    Returns:
        True when the worker answered; the compose healthcheck uses it.
    """
    node = f"celery@{socket.gethostname()}"
    replies = celery_app.control.ping(destination=[node], timeout=5)
    return bool(replies)


def main(argv: Sequence[str] | None = None) -> int:
    """Run a worker: ``python -m podcast_engine.worker <stage> [<stage> ...]``.

    Workers never import each other's code, so a container loads only what its stages need.

    A voice worker whose TTS backend cannot run here stands down without taking a job: voicing waits
    in the queue for a worker that can do it. It exits 0, so a restart policy of on-failure leaves
    it stopped.

    A worker waits out a broker outage however long it lasts (Docker Desktop quit, the laptop
    slept), instead of exiting after Celery's default 100 tries. A container would be restarted, but
    the Mac voice worker (``make voice-host``) has nothing to restart it.

    Args:
        argv: The stages, or ``--healthcheck``; the process's own arguments when None.

    Returns:
        0 on a clean exit or a healthy ping, 1 when the healthcheck fails.
    """
    parser = argparse.ArgumentParser(description=DESCRIPTION)
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
            configure_logging(settings.log_level)
            log.warning("voice_worker_standing_down", backend=settings.tts_backend, reason=problem)
            return 0
    start_metrics_server(settings.metrics_port)
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

import os
from pathlib import Path

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
    multiprocess,
    start_http_server,
)

MULTIPROC_ENV = "PROMETHEUS_MULTIPROC_DIR"
METRICS_CONTENT_TYPE = CONTENT_TYPE_LATEST

# Stages run seconds to minutes (TTS, LLM calls), far beyond the default buckets.
_STAGE_BUCKETS = (0.5, 1, 5, 15, 30, 60, 120, 300, 600)


def _ensure_multiprocess_dir() -> None:
    """Create the shared metrics folder when multiprocess mode is on.

    It must exist before the first labelled metric is created, so this runs on import.
    """
    directory = os.environ.get(MULTIPROC_ENV)
    if directory:
        Path(directory).mkdir(parents=True, exist_ok=True)


_ensure_multiprocess_dir()

HTTP_REQUESTS = Counter(
    "podcast_http_requests_total",
    "HTTP requests handled by the API.",
    ["method", "route", "status"],
)
HTTP_DURATION = Histogram(
    "podcast_http_request_duration_seconds",
    "API request latency.",
    ["method", "route"],
)
STAGE_RUNS = Counter(
    "podcast_stage_runs_total",
    "Pipeline stage attempts. A retried stage counts once per attempt.",
    ["stage", "outcome"],
)
STAGE_DURATION = Histogram(
    "podcast_stage_duration_seconds",
    "Wall-clock time of one pipeline stage attempt.",
    ["stage"],
    buckets=_STAGE_BUCKETS,
)


def _registry() -> CollectorRegistry:
    """Return the registry to read metrics from.

    Containers run several processes (uvicorn workers, Celery's prefork pool), and each would
    otherwise report only its own counters. When ``PROMETHEUS_MULTIPROC_DIR`` is set (compose does
    this) the processes write to shared files, and a fresh registry merges them.

    Returns:
        A merging registry in multiprocess mode, else the default one.
    """
    if os.environ.get(MULTIPROC_ENV):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)  # type: ignore[no-untyped-call]
        return registry
    return REGISTRY


def render_metrics() -> bytes:
    """Render every metric in Prometheus's text format.

    In multiprocess mode the counts of every process in the container are merged, so each scrape
    sees the whole container.

    Returns:
        The metrics document.
    """
    return generate_latest(_registry())


def start_metrics_server(port: int) -> None:
    """Serve ``/metrics`` from a background thread (used by the pipeline workers).

    Args:
        port: The port to listen on.
    """
    start_http_server(port, registry=_registry())

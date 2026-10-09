"""Prometheus metrics shared by the API and the pipeline workers.

Containers run several processes (uvicorn workers, Celery's prefork pool), and each process
would otherwise report only its own counters. When ``PROMETHEUS_MULTIPROC_DIR`` is set (compose
does this) the processes write to shared files and ``render_metrics`` merges them, so every
scrape sees the whole container.
"""

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
    directory = os.environ.get(MULTIPROC_ENV)
    if directory:
        Path(directory).mkdir(parents=True, exist_ok=True)


_ensure_multiprocess_dir()  # must exist before the first labelled metric is created

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
    if os.environ.get(MULTIPROC_ENV):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)  # type: ignore[no-untyped-call]
        return registry
    return REGISTRY


def render_metrics() -> bytes:
    """The current metrics in Prometheus text format."""
    return generate_latest(_registry())


def start_metrics_server(port: int) -> None:
    """Serve ``/metrics`` on ``port`` from a background thread (used by workers)."""
    start_http_server(port, registry=_registry())

"""API metrics: a request-timing middleware and the ``/metrics`` endpoint Prometheus scrapes."""

import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

from podcast_engine.common.metrics import (
    HTTP_DURATION,
    HTTP_REQUESTS,
    METRICS_CONTENT_TYPE,
    render_metrics,
)

METRICS_PATH = "/metrics"
UNMATCHED_ROUTE = "unmatched"


def add_metrics(app: FastAPI) -> None:
    """Record request count and latency per route template, and expose ``/metrics``."""

    @app.middleware("http")
    async def record_request(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path == METRICS_PATH:
            return await call_next(request)
        started = time.perf_counter()
        status_code = 500  # what we report if the handler raises
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            # The route template ("/shows/{show_id}"), never the raw path: raw ids would create
            # one time series per show. Requests that match no route share one label.
            # Routes in an included router know only their own path; FastAPI records the full
            # template, with the router's prefix (/v1), as the effective route.
            effective = request.scope.get("fastapi", {}).get("effective_route_context")
            route = request.scope.get("route")
            path = getattr(effective, "path", None) or getattr(route, "path", UNMATCHED_ROUTE)
            HTTP_REQUESTS.labels(request.method, path, str(status_code)).inc()
            HTTP_DURATION.labels(request.method, path).observe(time.perf_counter() - started)

    @app.get(METRICS_PATH, include_in_schema=False)
    def metrics() -> Response:
        return Response(render_metrics(), media_type=METRICS_CONTENT_TYPE)

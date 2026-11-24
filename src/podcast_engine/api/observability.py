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
    """Record request count and latency per route, and expose ``/metrics`` for Prometheus.

    Args:
        app: The FastAPI app to instrument.
    """

    @app.middleware("http")
    async def record_request(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Time one request and count it by method, route and status.

        The label is the route template (``/v1/shows/{show_id}``), never the raw path: raw ids would
        create one time series per show. Routes in an included router know only their own path, so
        the full template with the router's prefix is read from FastAPI's effective route. Requests
        that match no route share one label, and a handler that raises is counted as 500.
        ``/metrics`` itself is not counted.

        Args:
            request: The incoming request.
            call_next: The rest of the app, which produces the response.

        Returns:
            The app's response, unchanged.
        """
        if request.url.path == METRICS_PATH:
            return await call_next(request)
        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            effective = request.scope.get("fastapi", {}).get("effective_route_context")
            route = request.scope.get("route")
            path = getattr(effective, "path", None) or getattr(route, "path", UNMATCHED_ROUTE)
            HTTP_REQUESTS.labels(request.method, path, str(status_code)).inc()
            HTTP_DURATION.labels(request.method, path).observe(time.perf_counter() - started)

    @app.get(METRICS_PATH, include_in_schema=False)
    def metrics() -> Response:
        """Serve the metrics in Prometheus's text format.

        Returns:
            Every metric this process has recorded.
        """
        return Response(render_metrics(), media_type=METRICS_CONTENT_TYPE)

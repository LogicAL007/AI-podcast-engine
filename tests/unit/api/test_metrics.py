from uuid import uuid4

from prometheus_client import REGISTRY

from tests.unit.api.conftest import Harness


def _count(method: str, route: str, status: str) -> float:
    value = REGISTRY.get_sample_value(
        "podcast_http_requests_total", {"method": method, "route": route, "status": status}
    )
    return value or 0.0


def test_requests_are_counted_by_route_template_not_raw_path(harness: Harness) -> None:
    before = _count("GET", "/v1/shows/{show_id}", "404")
    harness.client.get(f"/v1/shows/{uuid4()}")
    harness.client.get(f"/v1/shows/{uuid4()}")
    assert _count("GET", "/v1/shows/{show_id}", "404") == before + 2


def test_unmatched_paths_share_one_label(harness: Harness) -> None:
    before = _count("GET", "unmatched", "404")
    harness.client.get("/no/such/path")
    harness.client.get("/another/one")
    assert _count("GET", "unmatched", "404") == before + 2


def test_metrics_endpoint_exposes_prometheus_text(harness: Harness) -> None:
    harness.client.get("/health")
    response = harness.client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "podcast_http_requests_total" in response.text
    assert "podcast_http_request_duration_seconds_bucket" in response.text


def test_metrics_endpoint_is_not_in_the_openapi_schema(harness: Harness) -> None:
    assert "/metrics" not in harness.client.get("/openapi.json").json()["paths"]


def test_scraping_does_not_count_itself(harness: Harness) -> None:
    harness.client.get("/metrics")
    harness.client.get("/metrics")
    assert _count("GET", "/metrics", "200") == 0.0

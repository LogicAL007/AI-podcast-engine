import pytest
from fastapi.testclient import TestClient

from podcast_engine.api.main import app

pytestmark = pytest.mark.integration


def test_health_and_unimplemented_routes() -> None:
    client = TestClient(app)
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/shows").status_code == 501

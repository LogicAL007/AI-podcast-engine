from uuid import uuid4

from tests.unit.api.conftest import Harness

VALID = {"topic": "Open-source AI research", "sources": ["https://example.org/feed.xml"]}


def test_create_applies_defaults_and_returns_201(harness: Harness) -> None:
    response = harness.client.post("/shows", json=VALID)
    assert response.status_code == 201
    body = response.json()
    assert body["target_minutes"] == 7
    assert body["host_count"] == 2
    assert body["sources"] == ["https://example.org/feed.xml"]


def test_create_rejects_invalid_input(harness: Harness) -> None:
    for bad in (
        {"topic": "ab"},
        {**VALID, "host_count": 9},
        {**VALID, "target_minutes": 0},
        {**VALID, "language": "english"},
        {**VALID, "sources": ["not a url"]},
    ):
        assert harness.client.post("/shows", json=bad).status_code == 422, bad


def test_get_list_update_delete_round_trip(harness: Harness) -> None:
    show_id = harness.client.post("/shows", json=VALID).json()["show_id"]

    assert harness.client.get(f"/shows/{show_id}").json()["topic"] == VALID["topic"]
    assert [s["show_id"] for s in harness.client.get("/shows").json()] == [show_id]

    patched = harness.client.patch(f"/shows/{show_id}", json={"host_count": 3})
    assert patched.json()["host_count"] == 3
    assert patched.json()["topic"] == VALID["topic"]

    assert harness.client.delete(f"/shows/{show_id}").status_code == 204
    assert harness.client.get(f"/shows/{show_id}").status_code == 404


def test_empty_patch_changes_nothing(harness: Harness) -> None:
    show_id = harness.client.post("/shows", json=VALID).json()["show_id"]
    response = harness.client.patch(f"/shows/{show_id}", json={})
    assert response.status_code == 200
    assert response.json()["topic"] == VALID["topic"]


def test_unknown_show_is_404_everywhere(harness: Harness) -> None:
    missing = uuid4()
    assert harness.client.get(f"/shows/{missing}").status_code == 404
    assert harness.client.patch(f"/shows/{missing}", json={"topic": "New topic"}).status_code == 404
    assert harness.client.delete(f"/shows/{missing}").status_code == 404


def test_list_pagination_bounds(harness: Harness) -> None:
    for _ in range(3):
        harness.client.post("/shows", json=VALID)
    assert len(harness.client.get("/shows", params={"limit": 2}).json()) == 2
    assert len(harness.client.get("/shows", params={"offset": 2}).json()) == 1
    assert harness.client.get("/shows", params={"limit": 0}).status_code == 422
    assert harness.client.get("/shows", params={"limit": 101}).status_code == 422

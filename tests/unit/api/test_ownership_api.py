"""Per-creator ownership: a user sees and changes only their own shows and what hangs off them.

Two real accounts, through real login. Another user's show, episode or upload must look exactly
like one that does not exist (404), so ids cannot be probed.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from podcast_engine.api.models.episodes_model import EpisodeFiles
from podcast_engine.api.models.shows_model import ShowCreate
from podcast_engine.api.models.sources_model import SourceRead
from podcast_engine.common.models import EpisodeStatus, ReliabilityTier
from tests.unit.api.conftest import Harness

PASSWORD = "an ownership test passphrase"
PDF = b"%PDF-1.7\n% owned by alice\n"


@pytest.fixture
def harness() -> Harness:
    return Harness(signed_in=False)


def _account(harness: Harness, email: str, admin_token: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {admin_token}"} if admin_token else {}
    created = harness.client.post(
        "/v1/auth/register", json={"email": email, "password": PASSWORD}, headers=headers
    )
    assert created.status_code == 201, created.text
    token = harness.client.post("/v1/auth/login", json={"email": email, "password": PASSWORD})
    return {"Authorization": f"Bearer {token.json()['access_token']}"}


@pytest.fixture
def two_users(harness: Harness) -> tuple[dict[str, str], dict[str, str]]:
    alice = _account(harness, "alice@example.org")  # the first account: admin
    bob = _account(harness, "bob@example.org", alice["Authorization"].split()[1])
    return alice, bob


def _alices_things(harness: Harness, alice: dict[str, str]) -> dict[str, Any]:
    show = harness.client.post("/v1/shows", json={"topic": "Alice's show"}, headers=alice).json()
    episode = harness.client.post(f"/v1/shows/{show['show_id']}/episodes", headers=alice).json()
    upload = harness.client.post(
        f"/v1/shows/{show['show_id']}/uploads",
        files={"file": ("a.pdf", PDF, "application/pdf")},
        headers=alice,
    ).json()
    return {
        "show": show["show_id"],
        "episode": episode["episode_id"],
        "upload": upload["upload_id"],
    }


def test_lists_contain_only_your_own(
    harness: Harness, two_users: tuple[dict[str, str], dict[str, str]]
) -> None:
    alice, bob = two_users
    _alices_things(harness, alice)
    harness.client.post("/v1/shows", json={"topic": "Bob's show"}, headers=bob)

    alice_shows = harness.client.get("/v1/shows", headers=alice).json()
    bob_shows = harness.client.get("/v1/shows", headers=bob).json()
    assert [s["topic"] for s in alice_shows["items"]] == ["Alice's show"]
    assert [s["topic"] for s in bob_shows["items"]] == ["Bob's show"]
    assert bob_shows["total"] == 1
    assert harness.client.get("/v1/episodes", headers=bob).json()["total"] == 0
    assert harness.client.get("/v1/episodes", headers=alice).json()["total"] == 1


def test_another_users_things_do_not_exist_for_you(
    harness: Harness, two_users: tuple[dict[str, str], dict[str, str]]
) -> None:
    alice, bob = two_users
    ids = _alices_things(harness, alice)
    show, episode, upload = ids["show"], ids["episode"], ids["upload"]
    edit = {"segments": [{"position": 1, "lines": [{"speaker": "Alex", "text": "Hijacked."}]}]}
    attempts = [
        ("GET", f"/v1/shows/{show}", None),
        ("PATCH", f"/v1/shows/{show}", {"topic": "Taken over"}),
        ("DELETE", f"/v1/shows/{show}", None),
        ("POST", f"/v1/shows/{show}/episodes", None),
        ("GET", f"/v1/shows/{show}/episodes", None),
        ("GET", f"/v1/shows/{show}/sources", None),
        ("GET", f"/v1/shows/{show}/uploads", None),
        ("GET", f"/v1/shows/{show}/uploads/{upload}", None),
        ("DELETE", f"/v1/shows/{show}/uploads/{upload}", None),
        ("GET", f"/v1/episodes/{episode}", None),
        ("GET", f"/v1/episodes/{episode}/script", None),
        ("PATCH", f"/v1/episodes/{episode}/script", edit),
        ("GET", f"/v1/episodes/{episode}/runs", None),
        ("GET", f"/v1/episodes/{episode}/claims", None),
        ("POST", f"/v1/episodes/{episode}/approve", None),
        ("POST", f"/v1/episodes/{episode}/retry", None),
        ("POST", f"/v1/episodes/{episode}/cancel", None),
        ("DELETE", f"/v1/episodes/{episode}", None),
    ]
    for method, path, body in attempts:
        response = harness.client.request(method, path, json=body, headers=bob)
        never_existed = harness.client.request(
            method, path.replace(show, str(uuid4())).replace(episode, str(uuid4())),
            json=body, headers=bob,
        )  # fmt: skip
        assert response.status_code == 404, (method, path, response.status_code)
        assert response.status_code == never_existed.status_code, (method, path)
    # Bob's upload attempt to Alice's show is refused too.
    upload_attempt = harness.client.post(
        f"/v1/shows/{show}/uploads", files={"file": ("b.pdf", PDF, "application/pdf")}, headers=bob
    )
    assert upload_attempt.status_code == 404

    # Nothing changed for Alice.
    assert harness.client.get(f"/v1/shows/{show}", headers=alice).json()["topic"] == "Alice's show"
    assert harness.client.get(f"/v1/episodes/{episode}", headers=alice).status_code == 200
    assert harness.client.get(f"/v1/shows/{show}/uploads", headers=alice).json()["total"] == 1


def test_episode_filter_cannot_reach_another_users_show(
    harness: Harness, two_users: tuple[dict[str, str], dict[str, str]]
) -> None:
    alice, bob = two_users
    ids = _alices_things(harness, alice)
    body = harness.client.get("/v1/episodes", params={"show_id": ids["show"]}, headers=bob).json()
    assert body["total"] == 0


def test_sources_are_only_your_own(
    harness: Harness, two_users: tuple[dict[str, str], dict[str, str]]
) -> None:
    alice, bob = two_users
    show = UUID(_alices_things(harness, alice)["show"])
    harness.sources.rows[show] = [
        SourceRead(
            item_id=uuid4(), url="https://x.test/", title="Alice's source", position=0,
            reliability=ReliabilityTier.PRIMARY, content_hash="h", words=10, chunks=1,
            published_at=None, fetched_at=datetime.now(UTC),
        )
    ]  # fmt: skip
    assert harness.client.get(f"/v1/shows/{show}/sources", headers=alice).json()["total"] == 1
    assert harness.client.get(f"/v1/shows/{show}/sources", headers=bob).status_code == 404


def test_what_podcast_apps_fetch_stays_public(
    harness: Harness, two_users: tuple[dict[str, str], dict[str, str]]
) -> None:
    alice, _ = two_users
    ids = _alices_things(harness, alice)
    episode = UUID(ids["episode"])
    harness.episodes.files[episode] = EpisodeFiles(audio_key="a.wav", notes_key=None)
    harness.store.objects["a.wav"] = b"RIFF....WAVE"
    harness.episodes.update(episode, status=EpisodeStatus.PUBLISHED)
    assert harness.client.get(f"/v1/episodes/{episode}/audio.wav").status_code == 200  # no token
    upload_file = f"/v1/shows/{ids['show']}/uploads/{ids['upload']}/file"
    assert harness.client.get(upload_file).status_code == 200


def test_the_first_admin_takes_over_shows_made_before_login(harness: Harness) -> None:
    legacy = harness.shows.add(ShowCreate(topic="Made before login"), owner_id=uuid4())
    harness.shows.owners[legacy.show_id] = None  # as the migration leaves existing shows
    admin = _account(harness, "first@example.org")
    shows = harness.client.get("/v1/shows", headers=admin).json()
    assert [s["show_id"] for s in shows["items"]] == [str(legacy.show_id)]
    later = _account(harness, "second@example.org", admin["Authorization"].split()[1])
    assert harness.client.get("/v1/shows", headers=later).json()["total"] == 0

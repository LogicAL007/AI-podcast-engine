"""Account management (admins and your own account), sign-ins, and the security log."""

from typing import Any

import pytest

from tests.unit.api.conftest import Harness

PASSWORD = "the admin passphrase"
ADMIN_EMAIL = "root@example.org"
CREATOR_EMAIL = "cleo@example.org"
SHOW = {"title": "Cleo's show", "topic": "tides", "sources": ["https://example.org/a"]}


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _login(harness: Harness, email: str, password: str = PASSWORD) -> dict[str, str]:
    response = harness.client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return _bearer(response.json()["access_token"])


@pytest.fixture
def harness() -> Harness:
    h = Harness(signed_in=False)
    h.client.post("/auth/register", json={"email": ADMIN_EMAIL, "password": PASSWORD})
    return h


@pytest.fixture
def admin(harness: Harness) -> dict[str, str]:
    return _login(harness, ADMIN_EMAIL)


@pytest.fixture
def creator(harness: Harness, admin: dict[str, str]) -> dict[str, Any]:
    made = harness.client.post(
        "/auth/register", json={"email": CREATOR_EMAIL, "password": PASSWORD}, headers=admin
    )
    assert made.status_code == 201
    return {"id": made.json()["user_id"], "headers": _login(harness, CREATOR_EMAIL)}


# ---- admins managing accounts --------------------------------------------------------------


def test_disabling_an_account_ends_its_sign_ins_and_logins(
    harness: Harness, admin: dict[str, str], creator: dict[str, Any]
) -> None:
    key = harness.client.post("/auth/api-keys", json={"name": "job"}, headers=creator["headers"])
    response = harness.client.patch(
        f"/auth/users/{creator['id']}", json={"disabled": True}, headers=admin
    )
    assert response.status_code == 200
    assert response.json()["disabled"] is True
    for headers in (creator["headers"], _bearer(key.json()["key"])):
        assert harness.client.get("/auth/me", headers=headers).status_code == 401
    failed = harness.client.post("/auth/login", json={"email": CREATOR_EMAIL, "password": PASSWORD})
    assert failed.status_code == 401
    harness.client.patch(f"/auth/users/{creator['id']}", json={"disabled": False}, headers=admin)
    assert _login(harness, CREATOR_EMAIL)  # re-enabled; old tokens stay revoked
    assert harness.client.get("/auth/me", headers=creator["headers"]).status_code == 401


def test_an_admin_can_promote_but_not_change_themselves(
    harness: Harness, admin: dict[str, str], creator: dict[str, Any]
) -> None:
    promoted = harness.client.patch(
        f"/auth/users/{creator['id']}", json={"role": "admin"}, headers=admin
    )
    assert promoted.json()["role"] == "admin"
    me = harness.client.get("/auth/me", headers=admin).json()["user_id"]
    selfish = harness.client.patch(f"/auth/users/{me}", json={"disabled": True}, headers=admin)
    assert selfish.status_code == 409


def test_creators_cannot_manage_accounts(
    harness: Harness, admin: dict[str, str], creator: dict[str, Any]
) -> None:
    me = harness.client.get("/auth/me", headers=admin).json()["user_id"]
    headers = creator["headers"]
    assert harness.client.patch(f"/auth/users/{me}", json={}, headers=headers).status_code == 403
    assert harness.client.delete(f"/auth/users/{me}", headers=headers).status_code == 403


def test_deleting_an_account_removes_its_shows_and_files(
    harness: Harness, admin: dict[str, str], creator: dict[str, Any]
) -> None:
    show = harness.client.post("/shows", json=SHOW, headers=creator["headers"]).json()
    harness.store.objects[f"feeds/{show['show_id']}.xml"] = b"<rss/>"
    gone = harness.client.delete(f"/auth/users/{creator['id']}", headers=admin)
    assert gone.status_code == 204
    assert harness.shows.rows == {}
    assert harness.store.objects == {}
    assert harness.client.delete(f"/auth/users/{creator['id']}", headers=admin).status_code == 404


# ---- your own account ------------------------------------------------------------------------


def test_you_can_delete_your_own_account_with_your_password(
    harness: Harness, creator: dict[str, Any]
) -> None:
    harness.client.post("/shows", json=SHOW, headers=creator["headers"])
    wrong = harness.client.request(
        "DELETE", "/auth/me", json={"password": "nope"}, headers=creator["headers"]
    )
    assert wrong.status_code == 403
    deleted = harness.client.request(
        "DELETE", "/auth/me", json={"password": PASSWORD}, headers=creator["headers"]
    )
    assert deleted.status_code == 204
    assert harness.shows.rows == {}
    assert harness.client.get("/auth/me", headers=creator["headers"]).status_code == 401


def test_the_last_admin_cannot_leave_others_behind(
    harness: Harness, admin: dict[str, str], creator: dict[str, Any]
) -> None:
    refused = harness.client.request(
        "DELETE", "/auth/me", json={"password": PASSWORD}, headers=admin
    )
    assert refused.status_code == 409


def test_changing_email_needs_the_password_and_notifies_the_old_address(
    harness: Harness, admin: dict[str, str], creator: dict[str, Any]
) -> None:
    headers = creator["headers"]
    taken = harness.client.post(
        "/auth/email", json={"password": PASSWORD, "new_email": ADMIN_EMAIL}, headers=headers
    )
    assert taken.status_code == 409
    wrong = harness.client.post(
        "/auth/email", json={"password": "nope", "new_email": "new@example.org"}, headers=headers
    )
    assert wrong.status_code == 403
    changed = harness.client.post(
        "/auth/email", json={"password": PASSWORD, "new_email": "new@example.org"}, headers=headers
    )
    assert changed.status_code == 204
    notice = harness.mailer.sent[-1]
    assert notice.to == CREATOR_EMAIL
    assert "new@example.org" in notice.body
    assert harness.client.get("/auth/me", headers=headers).status_code == 200  # still signed in
    assert _login(harness, "new@example.org")


def test_you_can_list_and_end_your_sign_ins(harness: Harness, admin: dict[str, str]) -> None:
    other = _login(harness, ADMIN_EMAIL)
    listed = harness.client.get("/auth/sessions", headers=admin).json()
    assert listed["total"] == 2
    current = [s for s in listed["items"] if s["current"]]
    assert len(current) == 1
    (other_id,) = [s["token_id"] for s in listed["items"] if not s["current"]]
    assert "access_token" not in str(listed)
    assert harness.client.delete(f"/auth/sessions/{other_id}", headers=admin).status_code == 204
    assert harness.client.get("/auth/me", headers=other).status_code == 401
    assert harness.client.delete(f"/auth/sessions/{other_id}", headers=admin).status_code == 404


def test_another_accounts_sign_in_is_not_found(
    harness: Harness, admin: dict[str, str], creator: dict[str, Any]
) -> None:
    items = harness.client.get("/auth/sessions", headers=admin).json()["items"]
    response = harness.client.delete(
        f"/auth/sessions/{items[0]['token_id']}", headers=creator["headers"]
    )
    assert response.status_code == 404


# ---- the security log ----------------------------------------------------------------------


def test_security_events_are_recorded(harness: Harness, admin: dict[str, str]) -> None:
    harness.client.post("/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong"})
    harness.client.post("/auth/login", json={"email": "ghost@example.org", "password": "x"})
    key = harness.client.post("/auth/api-keys", json={"name": "job"}, headers=admin).json()
    harness.client.delete(f"/auth/api-keys/{key['token_id']}", headers=admin)
    harness.client.post("/auth/logout", headers=admin)
    assert harness.events.names() == [
        "user_registered",
        "login_succeeded",
        "login_failed",
        "login_failed",
        "api_key_created",
        "api_key_revoked",
        "logout",
    ]
    ghost = harness.events.rows[3]
    assert ghost.user_id is None
    assert "ghost" not in str(ghost.detail)  # only a hash of the unknown email
    assert key["key"] not in str([row.detail for row in harness.events.rows])


def test_locks_and_throttling_are_recorded(harness: Harness) -> None:
    for _ in range(5):
        harness.client.post("/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong"})
    assert "account_locked" in harness.events.names()
    for n in range(20):
        harness.client.post("/auth/login", json={"email": f"u{n}@example.org", "password": "x"})
    assert "login_throttled" in harness.events.names()


def test_you_read_your_own_events_and_an_admin_reads_anyones(
    harness: Harness, admin: dict[str, str], creator: dict[str, Any]
) -> None:
    mine = harness.client.get("/auth/events", headers=creator["headers"]).json()
    assert mine["total"] >= 1
    assert {row["user_id"] for row in mine["items"]} == {creator["id"]}
    me = harness.client.get("/auth/me", headers=admin).json()["user_id"]
    peeking = harness.client.get("/auth/events", params={"user_id": me}, headers=creator["headers"])
    assert peeking.status_code == 403
    theirs = harness.client.get(
        "/auth/events", params={"user_id": creator["id"], "event": "login_succeeded"},
        headers=admin,
    ).json()  # fmt: skip
    assert [row["event"] for row in theirs["items"]] == ["login_succeeded"]
    everyone = harness.client.get("/auth/events", headers=admin).json()
    assert everyone["total"] > theirs["total"]


def test_deleted_accounts_leave_their_events(
    harness: Harness, admin: dict[str, str], creator: dict[str, Any]
) -> None:
    harness.client.delete(f"/auth/users/{creator['id']}", headers=admin)
    entry = harness.events.rows[0]
    assert entry.event == "user_deleted"
    assert entry.user_id is None  # the account is gone; the entry names it instead
    assert entry.detail["account"] == creator["id"]

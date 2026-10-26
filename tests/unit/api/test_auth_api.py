"""Login, accounts and API keys, through the real AuthService (in-memory repository)."""

from datetime import timedelta
from typing import Any

import pytest

from tests.unit.api.conftest import Harness

PASSWORD = "correct horse battery staple"


@pytest.fixture
def harness() -> Harness:
    return Harness(signed_in=False)


def _register(harness: Harness, email: str = "ada@example.org", **extra: Any) -> Any:
    return harness.client.post(
        "/v1/auth/register", json={"email": email, "password": PASSWORD, **extra}
    )


def _login(harness: Harness, email: str = "ada@example.org", password: str = PASSWORD) -> Any:
    return harness.client.post("/v1/auth/login", json={"email": email, "password": password})


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_protected_routes_need_a_token(harness: Harness) -> None:
    response = harness.client.get("/v1/shows")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert (
        harness.client.get("/v1/shows", headers=_bearer("pes_not-a-real-token")).status_code == 401
    )


def test_public_routes_stay_open(harness: Harness) -> None:
    for path in ("/health", "/home", "/.well-known/api-catalog"):
        assert harness.client.get(path).status_code == 200, path
    assert (
        harness.client.get("/v1/feeds/00000000-0000-0000-0000-000000000000/rss.xml").status_code
        == 404
    )


def test_first_account_is_admin_and_can_log_in(harness: Harness) -> None:
    created = _register(harness, role="creator")
    assert created.status_code == 201
    assert created.json()["role"] == "admin"
    assert "password" not in created.text

    login = _login(harness, email="ADA@example.org")  # emails are case-insensitive
    assert login.status_code == 200
    assert login.headers["cache-control"] == "no-store"
    body = login.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"].startswith("pes_")
    me = harness.client.get("/v1/auth/me", headers=_bearer(body["access_token"])).json()
    assert me["email"] == "ada@example.org"
    assert me["token_kind"] == "session"
    assert harness.client.get("/v1/shows", headers=_bearer(body["access_token"])).status_code == 200


def test_tokens_last_six_months(harness: Harness) -> None:
    _register(harness)
    token = _login(harness).json()
    assert token["expires_at"].startswith(str((harness.now + timedelta(days=180)).date()))
    harness.now += timedelta(days=179)  # still valid the day before
    assert (
        harness.client.get("/v1/auth/me", headers=_bearer(token["access_token"])).status_code == 200
    )
    harness.now += timedelta(days=1)  # six months (180 days) after issue: expired
    assert (
        harness.client.get("/v1/auth/me", headers=_bearer(token["access_token"])).status_code == 401
    )


def test_wrong_password_and_unknown_email_look_the_same(harness: Harness) -> None:
    _register(harness)
    wrong = _login(harness, password="not the password at all")
    unknown = _login(harness, email="nobody@example.org")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "wrong email or password"}


def test_after_the_first_account_only_an_admin_can_add_accounts(harness: Harness) -> None:
    _register(harness)
    assert _register(harness, "bob@example.org").status_code == 401
    admin = _login(harness).json()["access_token"]
    bob = harness.client.post(
        "/v1/auth/register",
        json={"email": "bob@example.org", "password": PASSWORD},
        headers=_bearer(admin),
    )
    assert bob.status_code == 201
    assert bob.json()["role"] == "creator"
    creator = _login(harness, "bob@example.org").json()["access_token"]
    carol = harness.client.post(
        "/v1/auth/register",
        json={"email": "carol@example.org", "password": PASSWORD},
        headers=_bearer(creator),
    )
    assert carol.status_code == 403
    duplicate = harness.client.post(
        "/v1/auth/register",
        json={"email": "BOB@example.org", "password": PASSWORD},
        headers=_bearer(admin),
    )
    assert duplicate.status_code == 409
    assert harness.client.get("/v1/auth/users", headers=_bearer(creator)).status_code == 403
    assert harness.client.get("/v1/auth/users", headers=_bearer(admin)).json()["total"] == 2


def test_short_passwords_are_refused(harness: Harness) -> None:
    response = harness.client.post(
        "/v1/auth/register", json={"email": "ada@example.org", "password": "short"}
    )
    assert response.status_code == 422


def test_logout_revokes_the_token(harness: Harness) -> None:
    _register(harness)
    token = _login(harness).json()["access_token"]
    assert harness.client.post("/v1/auth/logout", headers=_bearer(token)).status_code == 204
    assert harness.client.get("/v1/auth/me", headers=_bearer(token)).status_code == 401


def test_api_keys_are_shown_once_listed_without_the_key_and_revocable(harness: Harness) -> None:
    _register(harness)
    session = _login(harness).json()["access_token"]
    created = harness.client.post(
        "/v1/auth/api-keys", json={"name": "CI pipeline"}, headers=_bearer(session)
    )
    assert created.status_code == 201
    assert created.headers["cache-control"] == "no-store"
    key = created.json()
    assert key["key"].startswith("pek_")
    assert key["prefix"] == key["key"][:8]

    me = harness.client.get("/v1/auth/me", headers=_bearer(key["key"])).json()
    assert me["token_kind"] == "api_key"
    listed = harness.client.get("/v1/auth/api-keys", headers=_bearer(session)).json()
    assert listed["total"] == 1
    assert "key" not in listed["items"][0]
    assert listed["items"][0]["last_used_at"] is not None  # it was just used

    revoke = harness.client.delete(f"/v1/auth/api-keys/{key['token_id']}", headers=_bearer(session))
    assert revoke.status_code == 204
    assert harness.client.get("/v1/auth/me", headers=_bearer(key["key"])).status_code == 401
    again = harness.client.delete(f"/v1/auth/api-keys/{key['token_id']}", headers=_bearer(session))
    assert again.status_code == 404


def test_tokens_are_stored_only_as_hashes(harness: Harness) -> None:
    _register(harness)
    token = _login(harness).json()["access_token"]
    stored = " ".join(str(row) for row in harness.auth.tokens.values())
    assert token not in stored
    assert all(len(row["token_hash"]) == 64 for row in harness.auth.tokens.values())
    user = next(iter(harness.auth.users.values()))
    assert user.password_hash.startswith("$argon2id$")


# ---- self-service sign-up --------------------------------------------------------------------


def test_setup_status_reports_whether_sign_up_is_open() -> None:
    assert Harness(signed_in=False).client.get("/v1/auth/setup").json()["signup_open"] is False
    assert (
        Harness(signed_in=False, signup_open=True)
        .client.get("/v1/auth/setup")
        .json()["signup_open"]
        is True
    )


def test_with_sign_up_open_anyone_gets_a_creator_account_and_can_sign_in() -> None:
    harness = Harness(signed_in=False, signup_open=True)
    _register(harness)  # the first account: the admin
    created = _register(harness, "bob@example.org", role="admin")  # asks for admin
    assert created.status_code == 201
    assert created.json()["role"] == "creator"  # but self-service is always a creator
    assert _login(harness, "bob@example.org").status_code == 200
    assert harness.events.names().count("user_registered") == 2


def test_sign_ups_from_one_address_are_throttled() -> None:
    harness = Harness(signed_in=False, signup_open=True)
    _register(harness)
    codes = [_register(harness, f"user{n}@example.org").status_code for n in range(30)]
    assert 201 in codes
    assert codes[-1] == 429


def test_with_sign_up_closed_a_second_account_still_needs_an_admin() -> None:
    harness = Harness(signed_in=False)
    _register(harness)
    assert _register(harness, "bob@example.org").status_code == 401


# ---- assistant bot (avatar) --------------------------------------------------------------------


def test_people_choose_their_assistant_bot_and_it_comes_back_with_them(harness: Harness) -> None:
    _register(harness)
    token = _login(harness).json()["access_token"]
    assert harness.client.get("/v1/auth/me", headers=_bearer(token)).json()["avatar"] is None
    choice = {"character": "rex", "name": "  Rex   the  Robot ", "color": "mint", "glow": "cyan"}
    saved = harness.client.put("/v1/auth/me/avatar", json=choice, headers=_bearer(token))
    assert saved.status_code == 200
    expected = {
        "character": "rex",
        "name": "Rex the Robot",
        "color": "mint",
        "glow": "cyan",
        "accessory": "antenna",
    }
    assert saved.json()["avatar"] == expected
    assert harness.client.get("/v1/auth/me", headers=_bearer(token)).json()["avatar"] == expected


def test_only_the_offered_bot_choices_are_accepted(harness: Harness) -> None:
    _register(harness)
    token = _login(harness).json()["access_token"]
    for bad in ({"character": "dragon"}, {"color": "#ff0000"}, {"name": "   "}, {"name": "x" * 25}):
        response = harness.client.put("/v1/auth/me/avatar", json=bad, headers=_bearer(token))
        assert response.status_code == 422, bad


def test_choosing_a_bot_needs_sign_in(harness: Harness) -> None:
    assert harness.client.put("/v1/auth/me/avatar", json={"name": "Pip"}).status_code == 401

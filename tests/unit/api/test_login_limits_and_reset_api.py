"""Login attempt limits, password reset and password change, through the real AuthService."""

import re
from datetime import timedelta
from typing import Any

import pytest

from podcast_engine.api.repositories.login_attempts_repository import account_key
from tests.unit.api.conftest import Harness

PASSWORD = "the original passphrase"
NEW_PASSWORD = "a brand new passphrase"
EMAIL = "ada@example.org"


@pytest.fixture
def harness() -> Harness:
    h = Harness(signed_in=False)
    created = h.client.post("/v1/auth/register", json={"email": EMAIL, "password": PASSWORD})
    assert created.status_code == 201
    return h


def _login(harness: Harness, password: str = PASSWORD, email: str = EMAIL, **kw: Any) -> Any:
    return harness.client.post("/v1/auth/login", json={"email": email, "password": password}, **kw)


def _reset_token(harness: Harness) -> str:
    (email,) = harness.mailer.sent[-1:]
    match = re.search(r"https://podcasts\.example/reset-password#token=(\S+)", email.body)
    assert match, email.body
    return match.group(1)


# ---- attempt limits ------------------------------------------------------------------------


def test_five_failures_lock_the_account_with_the_same_answer(harness: Harness) -> None:
    for _ in range(5):
        assert _login(harness, "wrong guess").status_code == 401
    locked = _login(harness)  # the right password, during the lock
    assert locked.status_code == 401
    assert locked.json() == {"detail": "wrong email or password"}  # reveals nothing
    harness.seconds += 15 * 60  # the lock is temporary
    assert _login(harness).status_code == 200


def test_unknown_emails_are_counted_like_real_ones(harness: Harness) -> None:
    for _ in range(5):
        _login(harness, "x", email="nobody@example.org")
    # Locked too, so locking cannot be used to tell real accounts from unknown ones.
    assert harness.attempts.account_locked(account_key("nobody@example.org"))


def test_a_successful_login_clears_the_count(harness: Harness) -> None:
    for _ in range(4):
        _login(harness, "wrong guess")
    assert _login(harness).status_code == 200
    for _ in range(4):
        _login(harness, "wrong guess")
    assert _login(harness).status_code == 200  # the earlier four were forgotten


def test_many_failures_from_one_address_are_slowed_down(harness: Harness) -> None:
    for n in range(20):  # spread over many accounts, so no single account locks
        _login(harness, "guess", email=f"user{n}@example.org")
    response = _login(harness)
    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0


# ---- password reset ------------------------------------------------------------------------


def test_reset_answers_the_same_for_known_and_unknown_emails(harness: Harness) -> None:
    known = harness.client.post("/v1/auth/password-reset", json={"email": EMAIL})
    unknown = harness.client.post("/v1/auth/password-reset", json={"email": "nobody@example.org"})
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert [email.to for email in harness.mailer.sent] == [EMAIL]  # only the real one gets mail


def test_reset_sets_a_new_password_once_and_ends_every_sign_in(harness: Harness) -> None:
    session = _login(harness).json()["access_token"]
    me = {"Authorization": f"Bearer {session}"}
    key = harness.client.post("/v1/auth/api-keys", json={"name": "job"}, headers=me).json()["key"]
    harness.client.post("/v1/auth/password-reset", json={"email": EMAIL})
    token = _reset_token(harness)
    assert token.startswith("prt_")
    assert token not in str(harness.auth.resets)  # stored only as a hash

    confirm = harness.client.post(
        "/v1/auth/password-reset/confirm", json={"token": token, "new_password": NEW_PASSWORD}
    )
    assert confirm.status_code == 204
    assert confirm.headers["referrer-policy"] == "no-referrer"
    assert "password was changed" in harness.mailer.sent[-1].subject
    for old in (session, key):  # every sign-in ended
        assert (
            harness.client.get(
                "/v1/auth/me", headers={"Authorization": f"Bearer {old}"}
            ).status_code
            == 401
        )
    assert _login(harness).status_code == 401
    assert _login(harness, NEW_PASSWORD).status_code == 200
    again = harness.client.post(
        "/v1/auth/password-reset/confirm", json={"token": token, "new_password": NEW_PASSWORD}
    )
    assert again.status_code == 422  # single use


def test_reset_links_expire_and_only_the_newest_works(harness: Harness) -> None:
    harness.client.post("/v1/auth/password-reset", json={"email": EMAIL})
    first = _reset_token(harness)
    harness.client.post("/v1/auth/password-reset", json={"email": EMAIL})
    second = _reset_token(harness)
    body = {"new_password": NEW_PASSWORD}
    assert (
        harness.client.post(
            "/v1/auth/password-reset/confirm", json={**body, "token": first}
        ).status_code
        == 422
    )
    harness.now += timedelta(minutes=31)
    assert (
        harness.client.post(
            "/v1/auth/password-reset/confirm", json={**body, "token": second}
        ).status_code
        == 422
    )


def test_reset_unlocks_a_locked_account(harness: Harness) -> None:
    for _ in range(5):
        _login(harness, "wrong guess")
    harness.client.post("/v1/auth/password-reset", json={"email": EMAIL})
    harness.client.post(
        "/v1/auth/password-reset/confirm",
        json={"token": _reset_token(harness), "new_password": NEW_PASSWORD},
    )
    assert _login(harness, NEW_PASSWORD).status_code == 200


def test_reset_requests_are_capped_per_account(harness: Harness) -> None:
    for _ in range(5):
        assert (
            harness.client.post("/v1/auth/password-reset", json={"email": EMAIL}).status_code == 202
        )
    assert len(harness.mailer.sent) == 3  # the rest answered the same but sent nothing


# ---- changing the password -------------------------------------------------------------------


def test_change_password_keeps_this_sign_in_and_ends_the_others(harness: Harness) -> None:
    this = _login(harness).json()["access_token"]
    other = _login(harness).json()["access_token"]
    headers = {"Authorization": f"Bearer {this}"}
    wrong = harness.client.post(
        "/v1/auth/password",
        json={"current_password": "not it", "new_password": NEW_PASSWORD},
        headers=headers,
    )
    assert wrong.status_code == 403
    changed = harness.client.post(
        "/v1/auth/password",
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        headers=headers,
    )
    assert changed.status_code == 204
    assert harness.client.get("/v1/auth/me", headers=headers).status_code == 200
    other_headers = {"Authorization": f"Bearer {other}"}
    assert harness.client.get("/v1/auth/me", headers=other_headers).status_code == 401
    assert _login(harness, NEW_PASSWORD).status_code == 200

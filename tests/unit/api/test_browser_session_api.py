"""Browser sign-in: the HttpOnly session cookie, its CSRF token, and first-run setup."""

import pytest

from tests.unit.api.conftest import Harness

EMAIL = "ada@example.org"
PASSWORD = "a long enough passphrase"
SHOW = {"topic": "tides", "sources": ["https://example.org/a"]}


@pytest.fixture
def harness() -> Harness:
    h = Harness(signed_in=False)
    assert h.client.get("/v1/auth/setup").json() == {
        "first_account_open": True,
        "signup_open": False,
        "google_sign_in": False,
    }
    h.client.post("/v1/auth/register", json={"email": EMAIL, "password": PASSWORD})
    return h


def _sign_in(harness: Harness) -> str:
    """Sign in with the cookie and return the CSRF token the page would read."""
    response = harness.client.post(
        "/v1/auth/browser-session", json={"email": EMAIL, "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    return harness.client.cookies["pe_csrf"]


def test_setup_closes_once_the_first_account_exists(harness: Harness) -> None:
    assert harness.client.get("/v1/auth/setup").json() == {
        "first_account_open": False,
        "signup_open": False,
        "google_sign_in": False,
    }


def test_sign_in_sets_an_httponly_session_cookie_and_returns_no_token(harness: Harness) -> None:
    response = harness.client.post(
        "/v1/auth/browser-session", json={"email": EMAIL, "password": PASSWORD}
    )
    assert response.json()["email"] == EMAIL
    assert "access_token" not in response.text
    assert response.headers["cache-control"] == "no-store"
    cookies = {c.split("=", 1)[0]: c for c in response.headers.get_list("set-cookie")}
    session = cookies["pe_session"].lower()
    for attribute in ("httponly", "samesite=strict", "path=/"):
        assert attribute in session
    assert "max-age=15552000" in session  # 180 days
    assert "httponly" not in cookies["pe_csrf"].lower()  # the page has to read this one
    assert harness.client.get("/v1/auth/me").json()["token_kind"] == "session"


def test_changes_need_the_csrf_token_and_reads_do_not(harness: Harness) -> None:
    csrf = _sign_in(harness)
    assert harness.client.get("/v1/shows").status_code == 200
    assert harness.client.post("/v1/shows", json=SHOW).status_code == 403
    wrong = harness.client.post("/v1/shows", json=SHOW, headers={"X-CSRF-Token": "0" * 64})
    assert wrong.status_code == 403
    made = harness.client.post("/v1/shows", json=SHOW, headers={"X-CSRF-Token": csrf})
    assert made.status_code == 201


def test_bearer_tokens_need_no_csrf_token(harness: Harness) -> None:
    token = harness.client.post(
        "/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}
    ).json()["access_token"]
    harness.client.cookies.clear()
    made = harness.client.post("/v1/shows", json=SHOW, headers={"Authorization": f"Bearer {token}"})
    assert made.status_code == 201


def test_an_api_key_is_not_accepted_as_the_session_cookie(harness: Harness) -> None:
    csrf = _sign_in(harness)
    key = harness.client.post(
        "/v1/auth/api-keys", json={"name": "job"}, headers={"X-CSRF-Token": csrf}
    ).json()["key"]
    harness.client.cookies.clear()
    harness.client.cookies.set("pe_session", key)
    assert harness.client.get("/v1/auth/me").status_code == 401


def test_sign_out_revokes_the_token_and_clears_the_cookies(harness: Harness) -> None:
    csrf = _sign_in(harness)
    session = harness.client.cookies["pe_session"]
    assert harness.client.delete("/v1/auth/browser-session").status_code == 403  # no CSRF token
    out = harness.client.delete("/v1/auth/browser-session", headers={"X-CSRF-Token": csrf})
    assert out.status_code == 204
    assert all("max-age=0" in c.lower() for c in out.headers.get_list("set-cookie"))
    assert "pe_session" not in harness.client.cookies
    harness.client.cookies.set("pe_session", session)  # the old cookie no longer works
    assert harness.client.get("/v1/auth/me").status_code == 401
    # a stale sign-in can still be ended
    assert harness.client.delete("/v1/auth/browser-session").status_code == 204


def test_wrong_password_sets_no_cookie(harness: Harness) -> None:
    response = harness.client.post(
        "/v1/auth/browser-session", json={"email": EMAIL, "password": "not it at all"}
    )
    assert response.status_code == 401
    assert "set-cookie" not in response.headers

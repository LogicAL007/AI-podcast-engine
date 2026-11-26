"""Sign in with Google: the redirect out, the checks on the way back, and the accounts it opens."""

import base64
import hashlib
import json
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

from podcast_engine.api import dependencies
from podcast_engine.api.controllers.auth_controller import AuthController
from podcast_engine.api.google_sign_in import GoogleSignIn, safe_next
from tests.unit.api.conftest import TOKEN_KEY, Harness

CLIENT_ID = "app.apps.googleusercontent.com"
REDIRECT = "https://podcasts.example/api/v1/auth/google/callback"
EMAIL = "ada@example.org"
PASSWORD = "a long enough passphrase"


def _b64(data: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


class FakeGoogle:
    """Google's token endpoint: checks the PKCE verifier and answers with an ID token."""

    def __init__(self) -> None:
        self.challenge = ""
        self.nonce = ""
        self.claims: dict[str, Any] = {}

    def post(self, url: str, form: dict[str, str]) -> dict[str, Any]:
        verifier = form["code_verifier"].encode()
        digest = base64.urlsafe_b64encode(hashlib.sha256(verifier).digest()).rstrip(b"=")
        if form["code"] != "good-code" or digest.decode() != self.challenge:
            return {"error": "invalid_grant"}
        claims = {
            "iss": "https://accounts.google.com",
            "aud": CLIENT_ID,
            "sub": "1234567890",
            "email": EMAIL,
            "email_verified": True,
            "nonce": self.nonce,
            "exp": time.time() + 3600,
        } | self.claims
        return {"id_token": f"{_b64({'alg': 'RS256'})}.{_b64(claims)}.signature"}


def _harness(*, signup_open: bool = False, google: bool = True) -> tuple[Harness, FakeGoogle]:
    h = Harness(signed_in=False, signup_open=signup_open)
    fake = FakeGoogle()
    sign_in = GoogleSignIn(CLIENT_ID, "secret", REDIRECT, TOKEN_KEY, post=fake.post)
    h.client.app.dependency_overrides[dependencies.get_auth_controller] = (  # type: ignore[attr-defined]
        lambda: AuthController(h.auth_service, h.mailer, google=sign_in if google else None)
    )
    # The first account (the admin) exists, so the page is past first-run setup.
    h.client.post("/v1/auth/register", json={"email": "admin@example.org", "password": PASSWORD})
    return h, fake


def _start(h: Harness, fake: FakeGoogle, next_path: str = "/shows/1") -> dict[str, str]:
    response = h.client.get(
        "/v1/auth/google/start", params={"next": next_path}, follow_redirects=False
    )
    assert response.status_code == 302
    query = {k: v[0] for k, v in parse_qs(urlparse(response.headers["location"]).query).items()}
    fake.challenge, fake.nonce = query["code_challenge"], query["nonce"]
    return query


def _back(h: Harness, **params: str) -> Any:
    return h.client.get("/v1/auth/google/callback", params=params, follow_redirects=False)


def test_setup_says_whether_google_is_offered() -> None:
    assert _harness()[0].client.get("/v1/auth/setup").json()["google_sign_in"] is True
    off = _harness(google=False)[0]
    assert off.client.get("/v1/auth/setup").json()["google_sign_in"] is False
    assert off.client.get("/v1/auth/google/start", follow_redirects=False).status_code == 404


def test_start_sends_the_browser_to_google_with_pkce_and_a_lax_cookie() -> None:
    h, _ = _harness()
    response = h.client.get("/v1/auth/google/start", follow_redirects=False)
    target = urlparse(response.headers["location"])
    query = parse_qs(target.query)
    assert target.netloc == "accounts.google.com"
    assert query["client_id"] == [CLIENT_ID]
    assert query["redirect_uri"] == [REDIRECT]
    assert query["code_challenge_method"] == ["S256"]
    assert query["scope"] == ["openid email"]
    cookie = response.headers["set-cookie"].lower()
    for attribute in ("pe_google=", "httponly", "samesite=lax", "max-age=600"):
        assert attribute in cookie


def test_an_existing_account_signs_in_and_goes_where_it_was_headed() -> None:
    h, fake = _harness()
    h.auth.add_user(EMAIL, "unusable", "creator")
    state = _start(h, fake)["state"]
    response = _back(h, code="good-code", state=state)
    assert response.status_code == 303
    assert response.headers["location"] == "/shows/1"
    assert response.headers["cache-control"] == "no-store"
    assert "pe_session" in h.client.cookies
    assert "pe_google" not in h.client.cookies
    me = h.client.get("/v1/auth/me").json()
    assert (me["email"], me["token_kind"]) == (EMAIL, "session")
    events = [(e.event, e.detail.get("method")) for e in h.events.rows]
    assert ("login_succeeded", "google") in events


def test_a_new_address_gets_a_creator_account_only_while_sign_up_is_open() -> None:
    closed, fake = _harness()
    state = _start(closed, fake)["state"]
    response = _back(closed, code="good-code", state=state)
    assert response.headers["location"] == "/login?google=no_account"
    assert "pe_session" not in closed.client.cookies
    assert closed.auth.find_user(EMAIL) is None

    opened, fake = _harness(signup_open=True)
    state = _start(opened, fake)["state"]
    response = _back(opened, code="good-code", state=state)
    assert response.headers["location"] == "/welcome"
    assert opened.client.get("/v1/auth/me").json()["role"] == "creator"


def test_a_disabled_account_cannot_sign_in_with_google() -> None:
    h, fake = _harness()
    user = h.auth.add_user(EMAIL, "unusable", "creator")
    h.auth.update_user(user.user_id, role=None, disabled=True)
    state = _start(h, fake)["state"]
    assert _back(h, code="good-code", state=state).headers["location"] == (
        "/login?google=no_account"
    )


@pytest.mark.parametrize(
    ("claims", "reason"),
    [
        ({"email_verified": False}, "unverified"),
        ({"aud": "another-app"}, "failed"),
        ({"iss": "https://evil.example"}, "failed"),
        ({"exp": 0}, "failed"),
        ({"nonce": "replayed"}, "failed"),
    ],
)
def test_the_id_token_claims_are_checked(claims: dict[str, Any], reason: str) -> None:
    h, fake = _harness()
    h.auth.add_user(EMAIL, "unusable", "creator")
    fake.claims = claims
    state = _start(h, fake)["state"]
    assert _back(h, code="good-code", state=state).headers["location"] == (
        f"/login?google={reason}"
    )
    assert "pe_session" not in h.client.cookies


def test_the_way_back_must_match_this_browsers_sign_in() -> None:
    h, fake = _harness()
    h.auth.add_user(EMAIL, "unusable", "creator")
    _start(h, fake)
    assert _back(h, code="good-code", state="forged").headers["location"] == (
        "/login?google=failed"
    )
    state = _start(h, fake)["state"]
    h.client.cookies.delete("pe_google")
    assert _back(h, code="good-code", state=state).headers["location"] == ("/login?google=expired")
    state = _start(h, fake)["state"]
    h.client.cookies.set("pe_google", h.client.cookies["pe_google"][:-2] + "xx")
    assert _back(h, code="good-code", state=state).headers["location"] == ("/login?google=expired")
    h.client.cookies.clear()  # drop the tampered copy set above
    state = _start(h, fake)["state"]
    assert _back(h, code="stolen-code", state=state).headers["location"] == ("/login?google=failed")
    assert _back(h, error="access_denied").headers["location"] == "/login?google=cancelled"


def test_only_paths_on_this_site_are_followed_after_sign_in() -> None:
    assert safe_next("/shows/7") == "/shows/7"
    for outside in ("https://evil.example", "//evil.example", "/\\evil.example", "", None):
        assert safe_next(outside) == "/"

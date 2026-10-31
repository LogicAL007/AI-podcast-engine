"""Sign in with Google: OpenID Connect's authorization-code flow, run entirely on the server.

``start`` sends the browser to Google with a random ``state``, a ``nonce`` and a PKCE challenge,
and returns them in a signed, short-lived cookie (``pe_google``) for the way back. ``finish``
checks that cookie against what Google returns, swaps the code for an ID token at Google's token
endpoint, and checks the token's claims (issuer, audience, expiry, nonce, verified email).

The ID token comes straight from Google's token endpoint over TLS, so its signature need not be
checked again (OpenID Connect Core 3.1.3.7, step 6); its claims still are. The cookie is
SameSite=Lax, not Strict like the session cookie: the browser must send it on the redirect back
from Google, which is a cross-site navigation.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import Response

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 - an endpoint, not a secret
ISSUERS = frozenset({"accounts.google.com", "https://accounts.google.com"})
PENDING_COOKIE = "pe_google"
PENDING_SECONDS = 600  # the time allowed to choose an account at Google
CALLBACK_PATH = "/api/v1/auth/google/callback"  # as the browser sees it, through the web server

PostForm = Callable[[str, dict[str, str]], dict[str, Any]]


class GoogleSignInError(Exception):
    """Google sign-in did not complete. ``reason`` is a short code the sign-in page explains."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(detail or reason)
        self.reason = reason


@dataclass(frozen=True)
class GoogleIdentity:
    email: str
    subject: str  # Google's stable id for the account


def safe_next(path: str | None) -> str:
    """Where to go after signing in: a path on this site only, never another site."""
    if not path or not path.startswith("/") or path.startswith(("//", "/\\")):
        return "/"
    return path


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def post_form(url: str, form: dict[str, str]) -> dict[str, Any]:
    """POST a form and read the JSON answer (Google answers errors with JSON too)."""
    request = urllib.request.Request(  # noqa: S310 - the URL is the fixed https token endpoint
        url,
        data=urllib.parse.urlencode(form).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as reply:  # noqa: S310
            answer: dict[str, Any] = json.load(reply)
    except urllib.error.HTTPError as error:
        answer = json.load(error)
    return answer


class GoogleSignIn:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        key: bytes,
        *,
        post: PostForm = post_form,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        # Its own key, derived from the token key, so a signature here is useless anywhere else.
        self._key = hmac.new(key, b"google-sign-in", hashlib.sha256).digest()
        self._post = post
        self._clock = clock

    def _sign(self, payload: dict[str, Any]) -> str:
        body = _b64(json.dumps(payload, separators=(",", ":")).encode())
        mac = _b64(hmac.new(self._key, body.encode(), hashlib.sha256).digest())
        return f"{body}.{mac}"

    def _unsign(self, cookie: str | None) -> dict[str, Any]:
        body, _, mac = (cookie or "").partition(".")
        expected = _b64(hmac.new(self._key, body.encode(), hashlib.sha256).digest())
        if not body or not hmac.compare_digest(mac, expected):
            raise GoogleSignInError("expired", "the sign-in cookie is missing or not ours")
        pending: dict[str, Any] = json.loads(_unb64(body))
        if pending["exp"] < self._clock():
            raise GoogleSignInError("expired", "the sign-in took longer than allowed")
        return pending

    def start(self, next_path: str | None) -> tuple[str, str]:
        """Google's sign-in address, and the cookie value to set for the way back."""
        state, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(3))
        challenge = _b64(hashlib.sha256(verifier.encode()).digest())
        query = urllib.parse.urlencode(
            {
                "client_id": self._client_id,
                "redirect_uri": self._redirect_uri,
                "response_type": "code",
                "scope": "openid email",
                "state": state,
                "nonce": nonce,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "prompt": "select_account",
            }
        )
        cookie = self._sign(
            {
                "state": state,
                "nonce": nonce,
                "verifier": verifier,
                "next": safe_next(next_path),
                "exp": self._clock() + PENDING_SECONDS,
            }
        )
        return f"{AUTHORIZE_URL}?{query}", cookie

    def finish(
        self, code: str | None, state: str | None, error: str | None, cookie: str | None
    ) -> tuple[GoogleIdentity, str]:
        """The Google account that signed in, and where to send the browser next."""
        if error:
            raise GoogleSignInError("cancelled" if error == "access_denied" else "failed", error)
        pending = self._unsign(cookie)
        if not code or not state or not hmac.compare_digest(state, pending["state"]):
            raise GoogleSignInError("failed", "the state does not match this browser's sign-in")
        answer = self._post(
            TOKEN_URL,
            {
                "code": code,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "redirect_uri": self._redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": pending["verifier"],
            },
        )
        if "id_token" not in answer:
            raise GoogleSignInError("failed", f"token exchange refused: {answer.get('error')}")
        claims = self._claims(answer["id_token"])
        if claims.get("nonce") != pending["nonce"]:
            raise GoogleSignInError("failed", "the ID token's nonce does not match")
        if not claims.get("email") or claims.get("email_verified") is not True:
            raise GoogleSignInError("unverified", "the Google account has no verified email")
        return GoogleIdentity(email=claims["email"], subject=claims["sub"]), pending["next"]

    def _claims(self, id_token: str) -> dict[str, Any]:
        try:
            claims: dict[str, Any] = json.loads(_unb64(id_token.split(".")[1]))
        except (IndexError, ValueError) as caught:
            raise GoogleSignInError("failed", "the ID token is malformed") from caught
        audience = claims.get("aud")
        audiences = audience if isinstance(audience, list) else [audience]
        if claims.get("iss") not in ISSUERS or self._client_id not in audiences:
            raise GoogleSignInError("failed", "the ID token is not for this app")
        if claims.get("exp", 0) < self._clock():
            raise GoogleSignInError("failed", "the ID token has expired")
        return claims


def set_pending_cookie(response: Response, value: str, *, secure: bool) -> None:
    response.set_cookie(
        PENDING_COOKIE, value, max_age=PENDING_SECONDS, path="/", secure=secure, httponly=True,
        samesite="lax",
    )  # fmt: skip


def clear_pending_cookie(response: Response, *, secure: bool) -> None:
    response.delete_cookie(PENDING_COOKIE, path="/", secure=secure, httponly=True, samesite="lax")

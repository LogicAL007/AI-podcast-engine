"""Browser sign-in: the session cookie and its CSRF companion.

The web app signs in with ``POST /v1/auth/browser-session``. The login token then lives in an
HttpOnly cookie that page scripts cannot read, so a script injected into the page cannot steal it.
``SameSite=Strict`` keeps other sites' pages from sending it.

The second cookie, readable by scripts, holds a CSRF token derived from the session (an HMAC of
its id). Requests that change something must echo it in the ``X-CSRF-Token`` header. Another site
cannot read the cookie, so it cannot forge the header (OWASP's signed double-submit pattern).
Bearer tokens are sent deliberately, never automatically, so they need no CSRF token.
"""

from fastapi import Response

SESSION_COOKIE = "pe_session"
CSRF_COOKIE = "pe_csrf"
CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def set_session_cookies(
    response: Response, *, token: str, csrf: str, max_age: int, secure: bool
) -> None:
    response.set_cookie(
        SESSION_COOKIE, token, max_age=max_age, path="/", secure=secure, httponly=True,
        samesite="strict",
    )  # fmt: skip
    response.set_cookie(
        CSRF_COOKIE, csrf, max_age=max_age, path="/", secure=secure, httponly=False,
        samesite="strict",
    )  # fmt: skip


def clear_session_cookies(response: Response, *, secure: bool) -> None:
    for name, httponly in ((SESSION_COOKIE, True), (CSRF_COOKIE, False)):
        response.delete_cookie(name, path="/", secure=secure, httponly=httponly, samesite="strict")

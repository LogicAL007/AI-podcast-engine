"""Routes for login, users and API keys: paths, status codes and OpenAPI metadata only."""

from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Cookie,
    Depends,
    Header,
    Path,
    Query,
    Request,
    Response,
    status,
)
from fastapi.responses import RedirectResponse

from podcast_engine.api.controllers.auth_controller import AuthController
from podcast_engine.api.cookies import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE
from podcast_engine.api.dependencies import (
    get_auth_controller,
    get_current_user,
    get_optional_user,
)
from podcast_engine.api.google_sign_in import PENDING_COOKIE
from podcast_engine.api.models.auth_model import (
    Accepted,
    AccountDelete,
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyRead,
    Avatar,
    CurrentUser,
    EmailChange,
    LoginRequest,
    PasswordChange,
    PasswordResetConfirm,
    PasswordResetRequest,
    RegisterRequest,
    SecurityEventName,
    SecurityEventRead,
    SessionRead,
    SetupStatus,
    TokenResponse,
    UserRead,
    UserUpdate,
)
from podcast_engine.api.models.pagination_model import Page
from podcast_engine.api.openapi import errors
from podcast_engine.api.pagination import Paging, to_page

router = APIRouter(prefix="/auth", tags=["auth"])

Controller = Annotated[AuthController, Depends(get_auth_controller)]
Me = Annotated[CurrentUser, Depends(get_current_user)]
Optional = Annotated[CurrentUser | None, Depends(get_optional_user)]
NO_STORE = "no-store"  # responses that contain a token must not be cached (RFC 6749, 5.1)
UNAUTHENTICATED = errors(
    e401="Missing, invalid, expired or revoked token", e503="Login is not configured"
)


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account",
    response_description="The new account",
    responses=errors(
        e401="Accounts exist, sign-up is closed and no admin token was sent",
        e429="Too many sign-ups from this address; wait and try again",
        e403="The token is not an admin's",
        e409="An account with this email already exists",
        e503="Login is not configured",
    ),
)
def register(
    data: RegisterRequest, controller: Controller, by: Optional, request: Request
) -> UserRead:
    """Create an account. The very first account needs no token and becomes the admin. After that
    an admin (sending their token) can create accounts as `creator` or `admin`; and when sign-up
    is open (`SIGNUP_OPEN`), anyone can create their own account, always as a `creator`."""
    return controller.register(data, by, _address(request))


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Log in",
    response_description="A login token, valid for six months",
    responses=errors(
        e401="Wrong email or password (also while the account is temporarily locked)",
        e429="Too many failed attempts from this address; see `Retry-After`",
        e503="Login is not configured",
    ),
)
def login(
    data: LoginRequest, controller: Controller, request: Request, response: Response
) -> TokenResponse:
    """Exchange an email and password for a login token. Send it as `Authorization: Bearer
    <token>` on every other request. It lasts six months, until `POST /auth/logout`, or until the
    account is disabled. Each login creates a new token; earlier ones keep working.

    After five failed attempts within 15 minutes, the account is locked for 15 minutes (a password
    reset unlocks it). The answer stays "wrong email or password" during the lock, so it does not
    reveal which accounts exist. Many failures from one address get 429 with `Retry-After`."""
    response.headers["Cache-Control"] = NO_STORE
    return controller.login(data, _address(request))


@router.post(
    "/browser-session",
    response_model=CurrentUser,
    summary="Sign in (web app)",
    response_description="The account; the login token is set as a cookie, not returned",
    responses=errors(
        e401="Wrong email or password (also while the account is temporarily locked)",
        e429="Too many failed attempts from this address; see `Retry-After`",
        e503="Login is not configured",
    ),
)
def start_session(
    data: LoginRequest, controller: Controller, request: Request, response: Response
) -> CurrentUser:
    """Sign in from a browser. The login token goes into the `pe_session` cookie (HttpOnly,
    SameSite=Strict, six months), which page scripts cannot read, and the `pe_csrf` cookie holds
    a CSRF token. Requests that change something must send it back in the `X-CSRF-Token` header.
    The same limits as `POST /auth/login` apply. Scripts should use that endpoint or an API key."""
    response.headers["Cache-Control"] = NO_STORE
    return controller.start_session(data, _address(request), response)


@router.delete(
    "/browser-session",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Sign out (web app)",
    response_description="Signed out; both cookies are cleared",
    responses=errors(e403="The CSRF token is missing or wrong"),
)
def end_session(
    controller: Controller,
    request: Request,
    response: Response,
    session: Annotated[
        str | None, Cookie(alias=SESSION_COOKIE, description="The session cookie")
    ] = None,
    csrf: Annotated[
        str | None,
        Header(alias=CSRF_HEADER, description=f"The value of the `{CSRF_COOKIE}` cookie"),
    ] = None,
) -> None:
    """Revoke the browser's login token and clear its cookies. If the token no longer works,
    the cookies are still cleared, so a stale sign-in can always be ended."""
    controller.end_session(session, csrf, _address(request), response)


@router.get(
    "/google/start",
    response_class=RedirectResponse,
    status_code=status.HTTP_302_FOUND,
    summary="Sign in with Google (web app)",
    response_description="A redirect to Google's account chooser",
    responses=errors(e404="Google sign-in is not configured on this server"),
)
def google_start(
    controller: Controller,
    next_path: Annotated[
        str | None,
        Query(alias="next", description="Where to go after signing in: a path on this site"),
    ] = None,
) -> RedirectResponse:
    """Start signing in with Google: the browser is sent to Google with a random `state`, a
    `nonce` and a PKCE challenge, which a short-lived signed cookie (`pe_google`) keeps for the
    way back. Open this as a page, not with `fetch`."""
    return controller.google_start(next_path)


@router.get(
    "/google/callback",
    response_class=RedirectResponse,
    status_code=status.HTTP_303_SEE_OTHER,
    summary="Finish signing in with Google",
    response_description="A redirect into the app, or to `/login?google=<reason>` on failure",
    responses=errors(e404="Google sign-in is not configured on this server"),
)
def google_callback(
    controller: Controller,
    request: Request,
    code: Annotated[str | None, Query(description="The authorization code from Google")] = None,
    state: Annotated[str | None, Query(description="The `state` sent to Google")] = None,
    error: Annotated[
        str | None, Query(description="Set by Google when sign-in was cancelled or failed")
    ] = None,
    pending: Annotated[
        str | None, Cookie(alias=PENDING_COOKIE, description="The signed sign-in cookie")
    ] = None,
) -> RedirectResponse:
    """Where Google sends the browser back. The code is exchanged for an ID token whose issuer,
    audience, expiry, nonce and verified email are checked. An account with that email signs in;
    with none, one is created only while sign-up is open. The session cookies are then set as
    for `POST /auth/browser-session`. Failures go back to the sign-in page with a reason:
    `cancelled`, `expired`, `unverified`, `no_account`, `busy` or `failed`."""
    return controller.google_callback(code, state, error, pending, _address(request))


@router.get(
    "/setup",
    response_model=SetupStatus,
    summary="Check first-run setup",
    response_description="Whether the first account can still be created",
    responses=errors(e503="Login is not configured"),
)
def setup_status(controller: Controller) -> SetupStatus:
    """True until the first account exists. That account is created without signing in, with
    `POST /auth/register`, and becomes the admin."""
    return controller.setup()


@router.post(
    "/password-reset",
    response_model=Accepted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ask for a password reset",
    response_description="The same answer whether or not the account exists",
    responses=errors(e429="Too many attempts from this address; see `Retry-After`"),
)
def request_password_reset(
    data: PasswordResetRequest, controller: Controller, request: Request, tasks: BackgroundTasks
) -> Accepted:
    """Email a single-use reset link, valid for 30 minutes, if an account has this address. The
    answer is the same either way, and the email is sent after the response, so neither reveals
    whether the account exists. At most three links per account per hour."""
    return controller.request_reset(data.email, _address(request), tasks)


@router.post(
    "/password-reset/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Set a new password with a reset link",
    response_description="The password is changed; sign in with it",
    responses=errors(
        e422="The link is invalid, used or expired, or the password is too short",
        e429="Too many attempts from this address; see `Retry-After`",
    ),
)
def confirm_password_reset(
    data: PasswordResetConfirm,
    controller: Controller,
    request: Request,
    response: Response,
    tasks: BackgroundTasks,
) -> None:
    """Choose a new password with the token from the reset link. The link works once. Every login
    token and API key of the account stops working, any lock on it is lifted, and a notice is
    emailed. You are not signed in: log in with the new password."""
    response.headers["Referrer-Policy"] = "no-referrer"
    controller.confirm_reset(data, _address(request), tasks)


@router.put(
    "/me/avatar",
    response_model=CurrentUser,
    summary="Choose your assistant bot",
    response_description="You, with the bot you chose",
    responses={**UNAUTHENTICATED, **errors(e422="A choice outside the allowed options")},
)
def set_avatar(avatar: Avatar, me: Me, controller: Controller) -> CurrentUser:
    """Choose the assistant bot the web app shows you: the character, its name, its colours and
    what it wears. Only these choices are stored; the bot is drawn by the web app."""
    return controller.set_avatar(me, avatar)


@router.post(
    "/password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Change your password",
    response_description="Changed",
    responses={**UNAUTHENTICATED, **errors(e403="The current password is wrong")},
)
def change_password(
    data: PasswordChange, me: Me, controller: Controller, request: Request, tasks: BackgroundTasks
) -> None:
    """Change the password of the account you are signed in to. Your other login tokens stop
    working; this one and your API keys keep working. A notice is emailed."""
    controller.change_password(me, data, _address(request), tasks)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Log out",
    response_description="The token used for this request no longer works",
    responses=UNAUTHENTICATED,
)
def logout(me: Me, controller: Controller, request: Request) -> None:
    """Revoke the token this request was sent with (a login token or an API key)."""
    controller.logout(me, _address(request))


@router.get(
    "/me",
    response_model=CurrentUser,
    summary="Who am I",
    response_description="The account and the token this request used",
    responses=UNAUTHENTICATED,
)
def whoami(me: Me) -> CurrentUser:
    """The account behind the token, its role, and when the token expires."""
    return me


@router.get(
    "/users",
    response_model=Page[UserRead],
    summary="List accounts",
    response_description="A page of accounts, oldest first",
    responses={**UNAUTHENTICATED, **errors(e403="Only an admin can list accounts")},
)
def list_users(me: Me, controller: Controller, paging: Paging, request: Request) -> Page[UserRead]:
    """Every account (admins only)."""
    result = controller.list_users(me, limit=paging.limit, offset=paging.offset)
    return to_page(result, paging, request)


@router.post(
    "/api-keys",
    response_model=ApiKeyCreated,
    status_code=status.HTTP_201_CREATED,
    summary="Create an API key",
    response_description="The new key, shown only in this response",
    responses=UNAUTHENTICATED,
)
def create_api_key(
    data: ApiKeyCreate, me: Me, controller: Controller, request: Request, response: Response
) -> ApiKeyCreated:
    """A key for scripts and other programs, acting as your account. Send it like a login token
    (`Authorization: Bearer <key>`). It lasts six months unless revoked. Store it now: only its
    first characters are kept, so it cannot be shown again."""
    response.headers["Cache-Control"] = NO_STORE
    return controller.create_api_key(me, data.name, _address(request))


@router.get(
    "/api-keys",
    response_model=Page[ApiKeyRead],
    summary="List your API keys",
    response_description="A page of keys, newest first, without the keys themselves",
    responses=UNAUTHENTICATED,
)
def list_api_keys(
    me: Me, controller: Controller, paging: Paging, request: Request
) -> Page[ApiKeyRead]:
    """Your API keys with their names, first characters, expiry, last use and whether they are
    revoked."""
    result = controller.list_api_keys(me, limit=paging.limit, offset=paging.offset)
    return to_page(result, paging, request)


@router.delete(
    "/api-keys/{token_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke an API key",
    response_description="Revoked",
    responses={**UNAUTHENTICATED, **errors(e404="No active key of yours with this id")},
)
def revoke_api_key(
    token_id: Annotated[UUID, Path(description="The key's id")],
    me: Me,
    controller: Controller,
    request: Request,
) -> None:
    """Stop one of your API keys working, at once."""
    controller.revoke_api_key(me, token_id, _address(request))


@router.post(
    "/email",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Change your email",
    response_description="Changed; sign in with the new email from now on",
    responses={
        **UNAUTHENTICATED,
        **errors(e403="The password is wrong", e409="Another account uses this email"),
    },
)
def change_email(
    data: EmailChange, me: Me, controller: Controller, request: Request, tasks: BackgroundTasks
) -> None:
    """Move your account to a new email address, confirmed with your password. Your sign-ins keep
    working. A notice goes to the old address, so an unexpected change is noticed."""
    controller.change_email(me, data, _address(request), tasks)


@router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete your account",
    response_description="The account and everything in it are gone",
    responses={
        **UNAUTHENTICATED,
        **errors(
            e403="The password is wrong",
            e409="You are the last admin and other accounts exist; make another admin first",
        ),
    },
)
def delete_account(data: AccountDelete, me: Me, controller: Controller, request: Request) -> None:
    """Delete your account for good, confirmed with your password: your shows, episodes, sources,
    uploads, their stored audio, notes and feeds, your sign-ins and your API keys. This cannot be
    undone. The security log keeps its entries about you, without the link to the account."""
    controller.delete_account(me, data, _address(request))


@router.get(
    "/sessions",
    response_model=Page[SessionRead],
    summary="List your sign-ins",
    response_description="A page of active sign-ins, newest first",
    responses=UNAUTHENTICATED,
)
def list_sessions(
    me: Me, controller: Controller, paging: Paging, request: Request
) -> Page[SessionRead]:
    """The login tokens of your account that still work (browsers and devices you signed in on),
    with when each was created and last used. `current` marks the one making this request. API
    keys are listed separately, at `GET /auth/api-keys`."""
    result = controller.list_sessions(me, limit=paging.limit, offset=paging.offset)
    return to_page(result, paging, request)


@router.delete(
    "/sessions/{token_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Sign out a device",
    response_description="That sign-in no longer works",
    responses={**UNAUTHENTICATED, **errors(e404="No active sign-in of yours with this id")},
)
def revoke_session(
    token_id: Annotated[UUID, Path(description="The sign-in's id")],
    me: Me,
    controller: Controller,
    request: Request,
) -> None:
    """End one of your sign-ins, for example on a lost device. Use `POST /auth/logout` for this
    one."""
    controller.revoke_session(me, token_id, _address(request))


@router.patch(
    "/users/{user_id}",
    response_model=UserRead,
    summary="Change an account",
    response_description="The account as it is now",
    responses={
        **UNAUTHENTICATED,
        **errors(
            e403="Only an admin can change accounts",
            e404="No account with this id",
            e409="Admins cannot change their own account this way",
        ),
    },
)
def update_user(
    user_id: Annotated[UUID, Path(description="The account's id")],
    data: UserUpdate,
    me: Me,
    controller: Controller,
    request: Request,
) -> UserRead:
    """Make another account an admin or a creator, or disable or re-enable it (admins only).
    Disabling ends all of its sign-ins and API keys at once; re-enabling does not bring them
    back. Its shows stay, and are unreachable while it is disabled."""
    return controller.update_user(me, user_id, data, _address(request))


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an account",
    response_description="The account and everything in it are gone",
    responses={
        **UNAUTHENTICATED,
        **errors(
            e403="Only an admin can delete accounts",
            e404="No account with this id",
            e409="Use `DELETE /auth/me` for your own account",
        ),
    },
)
def delete_user(
    user_id: Annotated[UUID, Path(description="The account's id")],
    me: Me,
    controller: Controller,
    request: Request,
) -> None:
    """Delete another account for good, with its shows, episodes, uploads and stored files
    (admins only). This cannot be undone; disable the account instead to keep its data."""
    controller.delete_user(me, user_id, _address(request))


@router.get(
    "/events",
    response_model=Page[SecurityEventRead],
    summary="Read the security log",
    response_description="A page of security events, newest first",
    responses={**UNAUTHENTICATED, **errors(e403="Only an admin can read other accounts' events")},
)
def list_security_events(
    me: Me,
    controller: Controller,
    paging: Paging,
    request: Request,
    user_id: Annotated[
        UUID | None,
        Query(description="Only this account's events (admins; others always see their own)"),
    ] = None,
    event: Annotated[SecurityEventName | None, Query(description="Only this kind of event")] = None,
) -> Page[SecurityEventRead]:
    """Sign-ins, failed and throttled logins, locks, password resets and changes, email changes,
    API keys created and revoked, and account changes, with the address each came from. You see
    your own; an admin sees everyone's, or one account's with `user_id`. Failed logins for emails
    with no account are kept with no account (admins see them in the unfiltered log)."""
    result = controller.list_events(
        me, user_id=user_id, event=event, limit=paging.limit, offset=paging.offset
    )
    return to_page(result, paging, request)


def _address(request: Request) -> str:
    """The client's address. Behind nginx, uvicorn takes it from X-Forwarded-For."""
    return request.client.host if request.client else ""

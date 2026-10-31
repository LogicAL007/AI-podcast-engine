"""HTTP-facing orchestration for login, users and API keys."""

from uuid import UUID

from fastapi import BackgroundTasks, Response
from fastapi.responses import RedirectResponse

from podcast_engine.api.cookies import clear_session_cookies, set_session_cookies
from podcast_engine.api.errors import (
    NotFoundError,
    TooManyRequestsError,
    UnauthenticatedError,
    http_errors,
    to_http,
)
from podcast_engine.api.google_sign_in import (
    GoogleSignIn,
    GoogleSignInError,
    clear_pending_cookie,
    set_pending_cookie,
)
from podcast_engine.api.models.auth_model import (
    Accepted,
    AccountDelete,
    ApiKeyCreated,
    ApiKeyRead,
    Avatar,
    CurrentUser,
    EmailChange,
    LoginRequest,
    PasswordChange,
    PasswordResetConfirm,
    RegisterRequest,
    SecurityEventRead,
    SessionRead,
    SetupStatus,
    TokenResponse,
    UserRead,
    UserUpdate,
)
from podcast_engine.api.models.pagination_model import Paged
from podcast_engine.api.services.auth_service import AuthService
from podcast_engine.common.logging import get_logger
from podcast_engine.common.mailer import Email, Mailer

log = get_logger("api.auth")
GOOGLE_OFF = ("Google sign-in", "configuration")  # "... not found": not set up here
RESET_ACCEPTED = "If an account exists for this email, a reset link is on its way."


class AuthController:
    def __init__(
        self,
        service: AuthService,
        mailer: Mailer,
        *,
        cookie_secure: bool = False,
        token_days: int = 180,
        google: GoogleSignIn | None = None,
    ) -> None:
        self._service = service
        self._mailer = mailer
        self._google = google  # None: Google sign-in is not configured
        self._cookie_secure = cookie_secure  # Secure cookies need https, so not on plain localhost
        self._cookie_max_age = token_days * 24 * 3600

    # ---- browser sessions ----------------------------------------------------------------
    def start_session(self, data: LoginRequest, address: str, response: Response) -> CurrentUser:
        """Sign in for a browser: the login token goes into an HttpOnly cookie, never the body."""
        token = http_errors(lambda: self._service.login(data.email, data.password, address=address))
        current = http_errors(lambda: self._service.authenticate(token.access_token))
        self._set_session(response, token.access_token, token.token_id)
        return current

    def _set_session(self, response: Response, access_token: str, token_id: UUID) -> None:
        set_session_cookies(
            response,
            token=access_token,
            csrf=self._service.csrf_for(token_id),
            max_age=self._cookie_max_age,
            secure=self._cookie_secure,
        )

    def google_start(self, next_path: str | None) -> RedirectResponse:
        """Send the browser to Google, remembering (in a signed cookie) how to finish."""
        if self._google is None:
            raise to_http(NotFoundError(*GOOGLE_OFF))
        url, pending = self._google.start(next_path)
        response = RedirectResponse(url, status_code=302)
        set_pending_cookie(response, pending, secure=self._cookie_secure)
        return response

    def google_callback(
        self,
        code: str | None,
        state: str | None,
        error: str | None,
        pending: str | None,
        address: str,
    ) -> RedirectResponse:
        """Finish signing in with Google, then go on into the app, or back to the sign-in page
        with a reason it explains (``/login?google=<reason>``)."""
        if self._google is None:
            raise to_http(NotFoundError(*GOOGLE_OFF))
        try:
            identity, next_path = self._google.finish(code, state, error, pending)
            token, created = self._service.google_sign_in(identity.email, address=address)
        except GoogleSignInError as failure:
            log.info("google_sign_in_failed", reason=failure.reason, detail=str(failure))
            response = RedirectResponse(f"/login?google={failure.reason}", status_code=303)
        except UnauthenticatedError:
            response = RedirectResponse("/login?google=no_account", status_code=303)
        except TooManyRequestsError:
            response = RedirectResponse("/login?google=busy", status_code=303)
        else:
            response = RedirectResponse("/welcome" if created else next_path, status_code=303)
            self._set_session(response, token.access_token, token.token_id)
        clear_pending_cookie(response, secure=self._cookie_secure)
        response.headers["Cache-Control"] = "no-store"
        return response

    def end_session(
        self, cookie: str | None, csrf: str | None, address: str, response: Response
    ) -> None:
        """Sign the browser out: revoke its token if it still works, and clear both cookies."""
        if cookie:
            try:
                current = self._service.authenticate_session_cookie(cookie)
            except UnauthenticatedError:
                current = None  # already invalid: clearing the cookies is all that is left
            if current is not None:
                http_errors(lambda: self._service.check_csrf(current, csrf))
                http_errors(lambda: self._service.logout(current, address=address))
        clear_session_cookies(response, secure=self._cookie_secure)

    def set_avatar(self, user: CurrentUser, avatar: Avatar) -> CurrentUser:
        return self._service.set_avatar(user, avatar)

    def setup(self) -> SetupStatus:
        return SetupStatus(
            first_account_open=http_errors(self._service.setup_open),
            signup_open=self._service.signup_open(),
            google_sign_in=self._google is not None,
        )

    # TODO: Most segments per episode, remove entirely from the workflow
    def _send_later(self, tasks: BackgroundTasks, email: Email | None) -> None:
        """After the response: the reply never waits on (or reveals) whether mail was sent."""
        if email is not None:
            tasks.add_task(self._deliver, email)

    def _deliver(self, email: Email) -> None:
        try:
            self._mailer.send(email)
        except Exception:  # an unreachable mail server must not surface to the requester
            log.exception("email_failed", subject=email.subject)

    def request_reset(self, email: str, address: str, tasks: BackgroundTasks) -> Accepted:
        found = http_errors(lambda: self._service.request_reset(email, address=address))
        self._send_later(tasks, found)
        return Accepted(detail=RESET_ACCEPTED)

    def confirm_reset(
        self, data: PasswordResetConfirm, address: str, tasks: BackgroundTasks
    ) -> None:
        notice = http_errors(
            lambda: self._service.confirm_reset(data.token, data.new_password, address=address)
        )
        self._send_later(tasks, notice)

    def change_password(
        self, current: CurrentUser, data: PasswordChange, address: str, tasks: BackgroundTasks
    ) -> None:
        notice = http_errors(
            lambda: self._service.change_password(
                current, data.current_password, data.new_password, address=address
            )
        )
        self._send_later(tasks, notice)

    def change_email(
        self, current: CurrentUser, data: EmailChange, address: str, tasks: BackgroundTasks
    ) -> None:
        notice = http_errors(
            lambda: self._service.change_email(
                current, data.password, data.new_email, address=address
            )
        )
        self._send_later(tasks, notice)

    def delete_account(self, current: CurrentUser, data: AccountDelete, address: str) -> None:
        http_errors(lambda: self._service.delete_account(current, data.password, address=address))

    def register(self, data: RegisterRequest, by: CurrentUser | None, address: str) -> UserRead:
        return http_errors(
            lambda: self._service.register(
                data.email, data.password, data.role, by=by, address=address
            )
        )

    def login(self, data: LoginRequest, address: str) -> TokenResponse:
        return http_errors(lambda: self._service.login(data.email, data.password, address=address))

    def logout(self, current: CurrentUser, address: str) -> None:
        http_errors(lambda: self._service.logout(current, address=address))

    def list_sessions(self, current: CurrentUser, *, limit: int, offset: int) -> Paged[SessionRead]:
        return http_errors(lambda: self._service.list_sessions(current, limit=limit, offset=offset))

    def revoke_session(self, current: CurrentUser, token_id: UUID, address: str) -> None:
        http_errors(lambda: self._service.revoke_session(current, token_id, address=address))

    def list_users(self, current: CurrentUser, *, limit: int, offset: int) -> Paged[UserRead]:
        return http_errors(lambda: self._service.list_users(current, limit=limit, offset=offset))

    def update_user(
        self, current: CurrentUser, user_id: UUID, data: UserUpdate, address: str
    ) -> UserRead:
        return http_errors(
            lambda: self._service.update_user(
                current, user_id, role=data.role, disabled=data.disabled, address=address
            )
        )

    def delete_user(self, current: CurrentUser, user_id: UUID, address: str) -> None:
        http_errors(lambda: self._service.delete_user(current, user_id, address=address))

    def create_api_key(self, current: CurrentUser, name: str, address: str) -> ApiKeyCreated:
        return http_errors(lambda: self._service.create_api_key(current, name, address=address))

    def list_api_keys(self, current: CurrentUser, *, limit: int, offset: int) -> Paged[ApiKeyRead]:
        return http_errors(lambda: self._service.list_api_keys(current, limit=limit, offset=offset))

    def revoke_api_key(self, current: CurrentUser, token_id: UUID, address: str) -> None:
        http_errors(lambda: self._service.revoke_api_key(current, token_id, address=address))

    def list_events(
        self,
        current: CurrentUser,
        *,
        user_id: UUID | None,
        event: str | None,
        limit: int,
        offset: int,
    ) -> Paged[SecurityEventRead]:
        return http_errors(
            lambda: self._service.list_events(
                current, user_id=user_id, event=event, limit=limit, offset=offset
            )
        )

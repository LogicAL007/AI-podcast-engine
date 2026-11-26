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
    """HTTP-facing entry point for login, users and API keys."""

    def __init__(
        self,
        service: AuthService,
        mailer: Mailer,
        *,
        cookie_secure: bool = False,
        token_days: int = 180,
        google: GoogleSignIn | None = None,
    ) -> None:
        """Create the controller.

        Args:
            service: The auth service holding the rules.
            mailer: Sends password reset links and notices.
            cookie_secure: Whether cookies are HTTPS-only; off on plain localhost, where Secure
                cookies cannot work.
            token_days: How long a session lasts, for the cookies' lifetime.
            google: Google sign-in, or None when it is not configured.
        """
        self._service = service
        self._mailer = mailer
        self._google = google
        self._cookie_secure = cookie_secure
        self._cookie_max_age = token_days * 24 * 3600

    def start_session(self, data: LoginRequest, address: str, response: Response) -> CurrentUser:
        """Sign in for a browser: the login token goes into an HttpOnly cookie, never the body.

        Args:
            data: The email and password.
            address: The client's IP address, for limits and the security log.
            response: The response to set the session cookies on.

        Returns:
            The signed-in user.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        token = http_errors(lambda: self._service.login(data.email, data.password, address=address))
        current = http_errors(lambda: self._service.authenticate(token.access_token))
        self._set_session(response, token.access_token, token.token_id)
        return current

    def _set_session(self, response: Response, access_token: str, token_id: UUID) -> None:
        """Set the session cookie and its CSRF companion.

        Args:
            response: The response to set them on.
            access_token: The session's login token.
            token_id: The token's id, from which the CSRF token is derived.
        """
        set_session_cookies(
            response,
            token=access_token,
            csrf=self._service.csrf_for(token_id),
            max_age=self._cookie_max_age,
            secure=self._cookie_secure,
        )

    def google_start(self, next_path: str | None) -> RedirectResponse:
        """Send the browser to Google, remembering (in a signed cookie) how to finish.

        Args:
            next_path: Where to go after signing in.

        Returns:
            A redirect to Google's sign-in page.

        Raises:
            HTTPException: 404 when Google sign-in is not configured.
        """
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
        """Finish signing in with Google, then go on into the app.

        On failure the browser goes back to the sign-in page with a reason it explains
        (``/login?google=<reason>``).

        Args:
            code: The authorization code from Google.
            state: The state Google returned.
            error: Google's error, if any.
            pending: The pending-sign-in cookie.
            address: The client's IP address, for limits and the security log.

        Returns:
            A redirect into the app, or back to the sign-in page.
        """
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
        """Sign the browser out: revoke its token if it still works, and clear both cookies.

        A session that is already invalid needs no CSRF check; clearing the cookies is all that is
        left.

        Args:
            cookie: The session cookie, if sent.
            csrf: The ``X-CSRF-Token`` header, if sent.
            address: The client's IP address, for limits and the security log.
            response: The response to clear the cookies on.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        if cookie:
            try:
                current = self._service.authenticate_session_cookie(cookie)
            except UnauthenticatedError:
                current = None
            if current is not None:
                http_errors(lambda: self._service.check_csrf(current, csrf))
                http_errors(lambda: self._service.logout(current, address=address))
        clear_session_cookies(response, secure=self._cookie_secure)

    def set_avatar(self, user: CurrentUser, avatar: Avatar) -> CurrentUser:
        """Save the user's chosen companion avatar.

        Args:
            user: The signed-in user.
            avatar: The avatar's settings.

        Returns:
            The user with the new avatar.
        """
        return self._service.set_avatar(user, avatar)

    def setup(self) -> SetupStatus:
        """Report how accounts can be created here.

        Returns:
            Whether the first account is still open, whether sign-up is open, and whether Google
            sign-in is on.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        return SetupStatus(
            first_account_open=http_errors(self._service.setup_open),
            signup_open=self._service.signup_open(),
            google_sign_in=self._google is not None,
        )

    def _send_later(self, tasks: BackgroundTasks, email: Email | None) -> None:
        """Send an email after the response, so the reply never waits on or reveals the sending.

        Args:
            tasks: Background tasks; the email is sent after the response.
            email: The email, or None when there is nothing to send.
        """
        if email is not None:
            tasks.add_task(self._deliver, email)

    def _deliver(self, email: Email) -> None:
        """Send an email; an unreachable mail server is logged, never shown to the requester.

        Args:
            email: The email.
        """
        try:
            self._mailer.send(email)
        except Exception:
            log.exception("email_failed", subject=email.subject)

    def request_reset(self, email: str, address: str, tasks: BackgroundTasks) -> Accepted:
        """Accept a password reset request, sending the link when the account exists.

        The reply is the same either way, so it does not reveal whether an account exists.

        Args:
            email: The account's email.
            address: The client's IP address, for limits and the security log.
            tasks: Background tasks; the email is sent after the response.

        Returns:
            The same acceptance message every time.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        found = http_errors(lambda: self._service.request_reset(email, address=address))
        self._send_later(tasks, found)
        return Accepted(detail=RESET_ACCEPTED)

    def confirm_reset(
        self, data: PasswordResetConfirm, address: str, tasks: BackgroundTasks
    ) -> None:
        """Set a new password with a reset token, and send a notice.

        Args:
            data: The reset token and the new password.
            address: The client's IP address, for limits and the security log.
            tasks: Background tasks; the email is sent after the response.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        notice = http_errors(
            lambda: self._service.confirm_reset(data.token, data.new_password, address=address)
        )
        self._send_later(tasks, notice)

    def change_password(
        self, current: CurrentUser, data: PasswordChange, address: str, tasks: BackgroundTasks
    ) -> None:
        """Change the signed-in user's password, and send a notice.

        Args:
            current: The signed-in user.
            data: The current and new passwords.
            address: The client's IP address, for limits and the security log.
            tasks: Background tasks; the email is sent after the response.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        notice = http_errors(
            lambda: self._service.change_password(
                current, data.current_password, data.new_password, address=address
            )
        )
        self._send_later(tasks, notice)

    def change_email(
        self, current: CurrentUser, data: EmailChange, address: str, tasks: BackgroundTasks
    ) -> None:
        """Change the signed-in user's email, and send a notice.

        Args:
            current: The signed-in user.
            data: The password and the new email.
            address: The client's IP address, for limits and the security log.
            tasks: Background tasks; the email is sent after the response.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        notice = http_errors(
            lambda: self._service.change_email(
                current, data.password, data.new_email, address=address
            )
        )
        self._send_later(tasks, notice)

    def delete_account(self, current: CurrentUser, data: AccountDelete, address: str) -> None:
        """Delete the signed-in user's account and everything in it.

        Args:
            current: The signed-in user.
            data: The password, to confirm.
            address: The client's IP address, for limits and the security log.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        http_errors(lambda: self._service.delete_account(current, data.password, address=address))

    def register(self, data: RegisterRequest, by: CurrentUser | None, address: str) -> UserRead:
        """Create an account.

        Args:
            data: The email, password and role.
            by: The admin creating it, or None for sign-up or the first account.
            address: The client's IP address, for limits and the security log.

        Returns:
            The new account.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        return http_errors(
            lambda: self._service.register(
                data.email, data.password, data.role, by=by, address=address
            )
        )

    def login(self, data: LoginRequest, address: str) -> TokenResponse:
        """Sign in for an API client and return a login token.

        Args:
            data: The email and password.
            address: The client's IP address, for limits and the security log.

        Returns:
            The login token.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        return http_errors(lambda: self._service.login(data.email, data.password, address=address))

    def logout(self, current: CurrentUser, address: str) -> None:
        """Revoke the token this request was made with.

        Args:
            current: The signed-in user.
            address: The client's IP address, for limits and the security log.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        http_errors(lambda: self._service.logout(current, address=address))

    def list_sessions(self, current: CurrentUser, *, limit: int, offset: int) -> Paged[SessionRead]:
        """Return one page of the user's active sessions.

        Args:
            current: The signed-in user.
            limit: Most sessions to return.
            offset: Sessions to skip before this page.

        Returns:
            The page of sessions and the total.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        return http_errors(lambda: self._service.list_sessions(current, limit=limit, offset=offset))

    def revoke_session(self, current: CurrentUser, token_id: UUID, address: str) -> None:
        """Sign out one of the user's sessions.

        Args:
            current: The signed-in user.
            token_id: The session's token id.
            address: The client's IP address, for limits and the security log.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        http_errors(lambda: self._service.revoke_session(current, token_id, address=address))

    def list_users(self, current: CurrentUser, *, limit: int, offset: int) -> Paged[UserRead]:
        """Return one page of accounts (admins only).

        Args:
            current: The signed-in user.
            limit: Most accounts to return.
            offset: Accounts to skip before this page.

        Returns:
            The page of accounts and the total.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        return http_errors(lambda: self._service.list_users(current, limit=limit, offset=offset))

    def update_user(
        self, current: CurrentUser, user_id: UUID, data: UserUpdate, address: str
    ) -> UserRead:
        """Change another account's role or disable it (admins only).

        Disabling ends every sign-in and API key of that account at once.

        Args:
            current: The signed-in user.
            user_id: The account to change.
            data: The new role or disabled flag.
            address: The client's IP address, for limits and the security log.

        Returns:
            The account after the change.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        return http_errors(
            lambda: self._service.update_user(
                current, user_id, role=data.role, disabled=data.disabled, address=address
            )
        )

    def delete_user(self, current: CurrentUser, user_id: UUID, address: str) -> None:
        """Delete an account and everything in it (admins only).

        Args:
            current: The signed-in user.
            user_id: The account to delete.
            address: The client's IP address, for limits and the security log.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        http_errors(lambda: self._service.delete_user(current, user_id, address=address))

    def create_api_key(self, current: CurrentUser, name: str, address: str) -> ApiKeyCreated:
        """Create an API key for the user.

        Args:
            current: The signed-in user.
            name: A label for the key.
            address: The client's IP address, for limits and the security log.

        Returns:
            The key, shown only this once.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        return http_errors(lambda: self._service.create_api_key(current, name, address=address))

    def list_api_keys(self, current: CurrentUser, *, limit: int, offset: int) -> Paged[ApiKeyRead]:
        """Return one page of the user's API keys.

        Args:
            current: The signed-in user.
            limit: Most keys to return.
            offset: Keys to skip before this page.

        Returns:
            The page of keys (never the secrets) and the total.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        return http_errors(lambda: self._service.list_api_keys(current, limit=limit, offset=offset))

    def revoke_api_key(self, current: CurrentUser, token_id: UUID, address: str) -> None:
        """Revoke one of the user's API keys.

        Args:
            current: The signed-in user.
            token_id: The key's id.
            address: The client's IP address, for limits and the security log.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
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
        """Return one page of the security log.

        Your own events; an admin may read anyone's (user_id) or everyone's.

        Args:
            current: The signed-in user.
            user_id: One account's events; when None, everyone's for an admin, else the caller's
                own.
            event: Only events of this kind, or all when None.
            limit: Most events to return.
            offset: Events to skip before this page.

        Returns:
            The page of events, newest first, and the total.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        return http_errors(
            lambda: self._service.list_events(
                current, user_id=user_id, event=event, limit=limit, offset=offset
            )
        )

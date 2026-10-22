"""HTTP-facing orchestration for login, users and API keys."""

from uuid import UUID

from fastapi import BackgroundTasks

from podcast_engine.api.errors import http_errors
from podcast_engine.api.models.auth_model import (
    Accepted,
    AccountDelete,
    ApiKeyCreated,
    ApiKeyRead,
    CurrentUser,
    EmailChange,
    LoginRequest,
    PasswordChange,
    PasswordResetConfirm,
    RegisterRequest,
    SecurityEventRead,
    SessionRead,
    TokenResponse,
    UserRead,
    UserUpdate,
)
from podcast_engine.api.models.pagination_model import Paged
from podcast_engine.api.services.auth_service import AuthService
from podcast_engine.common.logging import get_logger
from podcast_engine.common.mailer import Email, Mailer

log = get_logger("api.auth")
RESET_ACCEPTED = "If an account exists for this email, a reset link is on its way."


class AuthController:
    def __init__(self, service: AuthService, mailer: Mailer) -> None:
        self._service = service
        self._mailer = mailer

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

"""Business rules for login, accounts and API keys. No HTTP and no SQL in here.

Passwords are hashed with Argon2id (argon2-cffi's defaults: RFC 9106's low-memory profile, above
OWASP's minimum). Login tokens and API keys are random, opaque strings. Only an HMAC-SHA256 of each
is stored, keyed with a secret held in Vault, so a copy of the database cannot be used to sign in
or to test guesses offline. Every token expires (by default 180 days, six months, after issue)
and can be revoked before that. Security-relevant actions are written to the security log.
"""

import hashlib
import hmac
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from pydantic import ValidationError

from podcast_engine.api.errors import (
    ConflictError,
    ForbiddenError,
    InvalidInputError,
    NotFoundError,
    TooManyRequestsError,
    UnauthenticatedError,
)
from podcast_engine.api.models.auth_model import (
    ApiKeyCreated,
    ApiKeyRead,
    Avatar,
    CurrentUser,
    Role,
    SecurityEventName,
    SecurityEventRead,
    SessionRead,
    StoredUser,
    TokenKind,
    TokenResponse,
    UserRead,
)
from podcast_engine.api.models.pagination_model import Paged
from podcast_engine.api.repositories.auth_repository import AuthRepository
from podcast_engine.api.repositories.login_attempts_repository import LoginAttempts, account_key
from podcast_engine.api.repositories.security_events_repository import SecurityEventRepository
from podcast_engine.common.mailer import Email

# Token prefixes: recognisable in logs and by secret scanners.
PREFIX = {"session": "pes_", "api_key": "pek_"}
RESET_PREFIX = "prt_"
SLOW_DOWN = "too many attempts from this address; try again later"
SHOWN_PREFIX = 8  # characters kept to recognise a key: "pek_" and four random ones
TOUCH_EVERY = timedelta(minutes=5)  # record last use at most this often
BAD_LOGIN = "wrong email or password"
BAD_TOKEN = "the token is missing, invalid, expired or revoked"  # noqa: S105
BAD_CSRF = "send the X-CSRF-Token header with the value of the pe_csrf cookie"
BAD_RESET = "the reset link is invalid or has expired; ask for a new one"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _avatar_or_none(stored: dict[str, Any] | None) -> Avatar | None:
    """The saved avatar, or None if there is none or it no longer fits the allowed choices."""
    if not stored:
        return None
    try:
        return Avatar.model_validate(stored)
    except ValidationError:
        return None


class AuthService:
    def __init__(
        self,
        repository: AuthRepository,
        *,
        token_key: bytes,
        token_days: int,
        now: Callable[[], datetime] = _utc_now,
        hasher: PasswordHasher | None = None,
        claim_unowned: Callable[[UUID], int] | None = None,
        attempts: LoginAttempts | None = None,
        events: SecurityEventRepository | None = None,
        purge_files: Callable[[UUID], int] | None = None,
        reset_minutes: int = 30,
        reset_max_requests: int = 3,
        web_url: str = "http://localhost:8080",
        signup_open: bool = False,
    ) -> None:
        if not token_key:
            raise ValueError("token_key must not be empty")
        self._repository = repository
        self._signup_open = signup_open
        self._key = token_key
        self._lifetime = timedelta(days=token_days)
        self._now = now
        self._hasher = hasher or PasswordHasher()
        self._claim_unowned = claim_unowned
        self._attempts = attempts
        self._events = events
        self._purge_files = purge_files  # deletes the stored files of a user's shows
        self._reset_lifetime = timedelta(minutes=reset_minutes)
        self._reset_max = reset_max_requests
        self._web_url = web_url.rstrip("/")
        # Checked against when the email is unknown, so a wrong email takes as long as a wrong
        # password and response times do not reveal which accounts exist.
        self._dummy_hash = self._hasher.hash(secrets.token_urlsafe(16))

    def _event(
        self, name: SecurityEventName, user_id: UUID | None, address: str = "", **detail: Any
    ) -> None:
        if self._events is not None:
            self._events.add(name, user_id=user_id, address=address, detail=detail)

    # ---- tokens ------------------------------------------------------------------------------
    def _digest(self, token: str) -> str:
        return hmac.new(self._key, token.encode(), hashlib.sha256).hexdigest()

    def _issue(self, user_id: UUID, kind: TokenKind, name: str = "") -> tuple[str, ApiKeyRead]:
        token = PREFIX[kind] + secrets.token_urlsafe(32)
        stored = self._repository.add_token(
            user_id=user_id,
            kind=kind,
            name=name,
            token_hash=self._digest(token),
            prefix=token[:SHOWN_PREFIX],
            expires_at=self._now() + self._lifetime,
        )
        return token, stored

    def authenticate(self, token: str) -> CurrentUser:
        """The user a bearer token belongs to. Every failure looks the same to the caller."""
        found = None
        if token.startswith(tuple(PREFIX.values())):
            found = self._repository.find_token(self._digest(token))
        now = self._now()
        if (
            found is None
            or found.revoked_at is not None
            or found.expires_at <= now
            or found.disabled
        ):
            raise UnauthenticatedError(BAD_TOKEN)
        if found.last_used_at is None or now - found.last_used_at >= TOUCH_EVERY:
            self._repository.touch(found.token_id, now)
        return CurrentUser(
            user_id=found.user_id,
            email=found.email,
            role=found.role,
            token_id=found.token_id,
            token_kind=found.kind,
            expires_at=found.expires_at,
            avatar=_avatar_or_none(found.avatar),
        )

    def authenticate_session_cookie(self, token: str) -> CurrentUser:
        """Like ``authenticate``, for the browser's cookie, which only a login token may be in."""
        current = self.authenticate(token)
        if current.token_kind != "session":  # noqa: S105 (a token kind, not a password)
            raise UnauthenticatedError(BAD_TOKEN)
        return current

    def csrf_for(self, token_id: UUID) -> str:
        """The CSRF token of a browser session: bound to it and unforgeable without the key."""
        return hmac.new(self._key, f"csrf:{token_id}".encode(), hashlib.sha256).hexdigest()

    def check_csrf(self, current: CurrentUser, presented: str | None) -> None:
        if not presented or not hmac.compare_digest(presented, self.csrf_for(current.token_id)):
            raise ForbiddenError(BAD_CSRF)

    def set_avatar(self, user: CurrentUser, avatar: Avatar) -> CurrentUser:
        """Keep the assistant bot this person chose; returns them with it."""
        self._repository.set_avatar(user.user_id, avatar.model_dump())
        return user.model_copy(update={"avatar": avatar})

    def setup_open(self) -> bool:
        """True until the first account exists (it is created without signing in)."""
        return self._repository.count_users() == 0

    def signup_open(self) -> bool:
        """True when anyone may create their own (creator) account, the SIGNUP_OPEN setting."""
        return self._signup_open

    def _verify(self, user: StoredUser | None, password: str) -> bool:
        try:
            self._hasher.verify(user.password_hash if user else self._dummy_hash, password)
        except (VerificationError, InvalidHashError):
            return False
        return user is not None

    def _slow_down(self, address: str) -> None:
        if self._attempts is not None and (wait := self._attempts.address_retry_after(address)):
            self._event("login_throttled", None, address, retry_after_s=wait)
            raise TooManyRequestsError(SLOW_DOWN, wait)

    # ---- sign-in -----------------------------------------------------------------------------
    def register(
        self, email: str, password: str, role: Role, *, by: CurrentUser | None, address: str = ""
    ) -> UserRead:
        """Create an account. The first account is the admin, and takes over any shows made
        before login existed. After that an admin can add accounts of either role, and, with
        sign-up open, anyone can create their own account, always as a creator."""
        if self._repository.count_users() == 0:
            admin = self._repository.add_user(email, self._hasher.hash(password), "admin")
            claimed = self._claim_unowned(admin.user_id) if self._claim_unowned else 0
            self._event(
                "user_registered",
                admin.user_id,
                address,
                role="admin",
                first=True,
                shows_claimed=claimed,
            )
            return admin
        if by is None and self._signup_open:
            # Each self-service sign-up counts against the address's attempt budget, so one
            # machine cannot create accounts in bulk.
            self._slow_down(address)
            user = self._repository.add_user(email, self._hasher.hash(password), "creator")
            if self._attempts is not None:
                self._attempts.record_failure(None, address)
            self._event("user_registered", user.user_id, address, role="creator", self_service=True)
            return user
        if by is None:
            raise UnauthenticatedError("log in as an admin to add accounts")
        if by.role != "admin":
            raise ForbiddenError("only an admin can add accounts")
        user = self._repository.add_user(email, self._hasher.hash(password), role)
        self._event("user_registered", user.user_id, address, role=role, by=str(by.user_id))
        return user

    def login(self, email: str, password: str, *, address: str = "") -> TokenResponse:
        """A new login token, valid for six months, for a correct email and password.

        Wrong credentials, an unknown email, a disabled account and a temporarily locked account
        all get the same answer, so none of them reveals that an account exists. Repeated
        failures lock the account for a while; repeated failures from one address slow that
        address down (429).
        """
        self._slow_down(address)
        key = account_key(email)
        user = self._repository.find_user(email)
        correct = self._verify(user, password)
        locked = self._attempts is not None and self._attempts.account_locked(key)
        if not correct or user is None or user.disabled or locked:
            reason = (
                "locked" if locked else ("disabled" if user and user.disabled else "credentials")
            )
            self._event(
                "login_failed",
                user.user_id if user else None,
                address,
                reason=reason,
                **({} if user else {"account_hash": key[:16]}),
            )
            just_locked = (
                self._attempts is not None
                and not locked
                and self._attempts.record_failure(key, address)
            )
            if just_locked:
                self._event("account_locked", user.user_id if user else None, address)
            raise UnauthenticatedError(BAD_LOGIN)
        if self._attempts is not None:
            self._attempts.clear(key)
        if self._hasher.check_needs_rehash(user.password_hash):  # stronger parameters since
            self._repository.set_password_hash(user.user_id, self._hasher.hash(password))
        token, stored = self._issue(user.user_id, "session")
        self._event("login_succeeded", user.user_id, address, token_id=str(stored.token_id))
        return TokenResponse(
            access_token=token, token_id=stored.token_id, expires_at=stored.expires_at
        )

    def logout(self, current: CurrentUser, *, address: str = "") -> None:
        self._repository.revoke(current.token_id, current.user_id, self._now())
        self._event("logout", current.user_id, address, token_id=str(current.token_id))

    def list_sessions(self, current: CurrentUser, *, limit: int, offset: int) -> Paged[SessionRead]:
        """The caller's active sign-ins, marking the one making this request."""
        page = self._repository.list_sessions(current.user_id, limit=limit, offset=offset)
        items = [
            s.model_copy(update={"current": s.token_id == current.token_id}) for s in page.items
        ]
        return Paged(items, page.total)

    def revoke_session(self, current: CurrentUser, token_id: UUID, *, address: str = "") -> None:
        """End one of the caller's sign-ins (another device, say)."""
        if token_id not in self._repository.session_ids(current.user_id):
            raise NotFoundError("active sign-in", token_id)
        self._repository.revoke(token_id, current.user_id, self._now())
        self._event("session_revoked", current.user_id, address, token_id=str(token_id))

    # ---- passwords --------------------------------------------------------------------------
    def request_reset(self, email: str, *, address: str = "") -> Email | None:
        """The reset email to send, or None (unknown email, disabled account, too many requests).

        The caller answers the same way whatever this returns, and sends the email in the
        background, so neither the reply nor its timing reveals whether the account exists.
        The link carries the token in its fragment (after ``#``), which browsers never send to a
        server, so it stays out of logs and Referer headers.
        """
        self._slow_down(address)
        key = account_key(email)
        if self._attempts is not None and self._attempts.reset_requests(key) > self._reset_max:
            return None  # mailbox flooding: say nothing, send nothing
        user = self._repository.find_user(email)
        token = RESET_PREFIX + secrets.token_urlsafe(32)
        if user is None or user.disabled:
            return None
        now = self._now()
        self._repository.void_resets(user.user_id, now)
        self._repository.add_reset(user.user_id, self._digest(token), now + self._reset_lifetime)
        self._event("password_reset_requested", user.user_id, address)
        minutes = int(self._reset_lifetime.total_seconds() // 60)
        return Email(
            to=user.email,
            subject="Reset your Podcast Engine password",
            body=(
                f"Someone asked to reset the password for {user.email}.\n\n"
                f"To choose a new one, open this link within {minutes} minutes:\n"
                f"{self._web_url}/reset-password#token={token}\n\n"
                "The link works once. If you did not ask for this, ignore this email: your "
                "password has not changed.\n"
            ),
        )

    def confirm_reset(self, token: str, new_password: str, *, address: str = "") -> Email:
        """Set a new password with a reset token. Every login token and API key of the account
        stops working (sign in again), and a notice is returned for sending."""
        self._slow_down(address)
        found = None
        if token.startswith(RESET_PREFIX):
            found = self._repository.find_reset(self._digest(token))
        now = self._now()
        if found is None or found.used_at is not None or found.expires_at <= now or found.disabled:
            if self._attempts is not None:
                self._attempts.record_failure(None, address)  # guessing tokens: per address
            raise InvalidInputError(BAD_RESET)
        if not self._repository.use_reset(found.reset_id, now):
            raise InvalidInputError(BAD_RESET)
        self._repository.set_password_hash(found.user_id, self._hasher.hash(new_password))
        revoked = self._repository.revoke_all(found.user_id, now)
        if self._attempts is not None:
            self._attempts.clear(account_key(found.email))
        self._event("password_reset_completed", found.user_id, address, tokens_revoked=revoked)
        return self._notice(
            found.email,
            "Your Podcast Engine password was changed",
            "The password for {email} was just changed, and every sign-in ended.",
        )

    def change_password(
        self, current: CurrentUser, current_password: str, new_password: str, *, address: str = ""
    ) -> Email:
        """Change the password of the signed-in account. Its other login tokens stop working;
        the one making this request, and the account's API keys, keep working."""
        user = self._require_password(current, current_password)
        self._repository.set_password_hash(user.user_id, self._hasher.hash(new_password))
        ended = 0
        for token_id in self._repository.session_ids(current.user_id):
            if token_id != current.token_id:
                self._repository.revoke(token_id, user.user_id, self._now())
                ended += 1
        self._event("password_changed", user.user_id, address, sessions_ended=ended)
        return self._notice(
            user.email,
            "Your Podcast Engine password was changed",
            "The password for {email} was just changed, and other sign-ins ended.",
        )

    def _require_password(self, current: CurrentUser, password: str) -> StoredUser:
        """The caller's account, if ``password`` is right. Wrong guesses count toward the lock,
        so a stolen token cannot be used to guess the password at full speed."""
        user = self._repository.get_user(current.user_id)
        if not self._verify(user, password) or user is None:
            if self._attempts is not None:
                self._attempts.record_failure(account_key(current.email), "")
            raise ForbiddenError("the password is wrong")
        return user

    @staticmethod
    def _notice(to: str, subject: str, line: str) -> Email:
        return Email(
            to=to,
            subject=subject,
            body=(
                f"{line.format(email=to)}\n\n"
                "If this was not you, reset your password now and tell your administrator.\n"
            ),
        )

    # ---- your account ------------------------------------------------------------------------
    def change_email(
        self, current: CurrentUser, password: str, new_email: str, *, address: str = ""
    ) -> Email:
        """Move the account to a new email (confirmed with the password). A notice goes to the
        old address, so an unexpected change is noticed."""
        user = self._require_password(current, password)
        self._repository.set_email(user.user_id, new_email)
        self._event("email_changed", user.user_id, address)
        return self._notice(
            user.email,
            "Your Podcast Engine email was changed",
            f"The account {{email}} now signs in with {new_email}.",
        )

    def delete_account(self, current: CurrentUser, password: str, *, address: str = "") -> int:
        """Delete the caller's account with all its shows, episodes, uploads and stored files.
        The last active admin cannot leave while other accounts depend on them. Returns how many
        stored files were removed."""
        user = self._require_password(current, password)
        if (
            user.role == "admin"
            and self._repository.count_admins() <= 1
            and self._repository.count_users() > 1
        ):
            raise ConflictError("make another account an admin before deleting the last admin")
        removed = self._purge_files(user.user_id) if self._purge_files else 0
        self._repository.delete_user(user.user_id)
        # The account row is gone, so the entry names it in its detail instead of linking to it.
        self._event(
            "account_deleted", None, address, account=str(user.user_id), files_removed=removed
        )
        return removed

    # ---- administration ----------------------------------------------------------------------
    def _admin(self, current: CurrentUser, action: str) -> None:
        if current.role != "admin":
            raise ForbiddenError(f"only an admin can {action}")

    def list_users(self, current: CurrentUser, *, limit: int, offset: int) -> Paged[UserRead]:
        self._admin(current, "list accounts")
        return self._repository.list_users(limit=limit, offset=offset)

    def update_user(
        self,
        current: CurrentUser,
        user_id: UUID,
        *,
        role: Role | None,
        disabled: bool | None,
        address: str = "",
    ) -> UserRead:
        """Change an account's role or disable it (an admin, on another account). Disabling
        ends every sign-in and API key of that account at once."""
        self._admin(current, "change accounts")
        if user_id == current.user_id:
            raise ConflictError("you cannot change your own role or disable yourself")
        user = self._repository.update_user(user_id, role=role, disabled=disabled)
        if user is None:
            raise NotFoundError("account", user_id)
        revoked = self._repository.revoke_all(user_id, self._now()) if disabled else 0
        self._event(
            "user_updated",
            user_id,
            address,
            by=str(current.user_id),
            role=role,
            disabled=disabled,
            tokens_revoked=revoked,
        )
        return user

    def delete_user(self, current: CurrentUser, user_id: UUID, *, address: str = "") -> int:
        """Delete another account with all its data and stored files (an admin)."""
        self._admin(current, "delete accounts")
        if user_id == current.user_id:
            raise ConflictError("delete your own account with DELETE /auth/me")
        if self._repository.get_user(user_id) is None:
            raise NotFoundError("account", user_id)
        removed = self._purge_files(user_id) if self._purge_files else 0
        self._repository.delete_user(user_id)
        self._event(
            "user_deleted",
            None,
            address,
            account=str(user_id),
            by=str(current.user_id),
            files_removed=removed,
        )
        return removed

    # ---- API keys ----------------------------------------------------------------------------
    def create_api_key(
        self, current: CurrentUser, name: str, *, address: str = ""
    ) -> ApiKeyCreated:
        """A new API key for the caller's account, valid for six months. It is shown only now."""
        key, stored = self._issue(current.user_id, "api_key", name)
        self._event("api_key_created", current.user_id, address, token_id=str(stored.token_id))
        return ApiKeyCreated(**stored.model_dump(), key=key)

    def list_api_keys(self, current: CurrentUser, *, limit: int, offset: int) -> Paged[ApiKeyRead]:
        return self._repository.list_api_keys(current.user_id, limit=limit, offset=offset)

    def revoke_api_key(self, current: CurrentUser, token_id: UUID, *, address: str = "") -> None:
        """Revoke one of the caller's own keys; another account's key is reported as not found."""
        if not self._repository.revoke(token_id, current.user_id, self._now()):
            raise NotFoundError("active API key", token_id)
        self._event("api_key_revoked", current.user_id, address, token_id=str(token_id))

    # ---- the security log --------------------------------------------------------------------
    def list_events(
        self,
        current: CurrentUser,
        *,
        user_id: UUID | None,
        event: str | None,
        limit: int,
        offset: int,
    ) -> Paged[SecurityEventRead]:
        """Your own security events; an admin may read anyone's (``user_id``) or everyone's."""
        if self._events is None:
            return Paged([], 0)
        if current.role != "admin":
            if user_id not in (None, current.user_id):
                raise ForbiddenError("you can read only your own security events")
            user_id = current.user_id
        return self._events.list_page(user_id=user_id, event=event, limit=limit, offset=offset)

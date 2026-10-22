"""Persistence for login: the only module that knows the ``users`` and ``auth_tokens`` tables."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from podcast_engine.api.errors import ConflictError
from podcast_engine.api.models.auth_model import (
    ApiKeyRead,
    Role,
    SessionRead,
    StoredReset,
    StoredToken,
    StoredUser,
    TokenKind,
    UserRead,
)
from podcast_engine.api.models.pagination_model import Paged

_USER = "user_id, email, role, disabled, created_at"
_KEY = "token_id, name, prefix, created_at, expires_at, last_used_at, revoked_at"


class AuthRepository(Protocol):
    def count_users(self) -> int: ...

    def add_user(self, email: str, password_hash: str, role: Role) -> UserRead: ...

    def find_user(self, email: str) -> StoredUser | None: ...

    def set_password_hash(self, user_id: UUID, password_hash: str) -> None: ...

    def list_users(self, *, limit: int, offset: int) -> Paged[UserRead]: ...

    def add_token(
        self,
        *,
        user_id: UUID,
        kind: TokenKind,
        name: str,
        token_hash: str,
        prefix: str,
        expires_at: datetime,
    ) -> ApiKeyRead: ...

    def find_token(self, token_hash: str) -> StoredToken | None: ...

    def touch(self, token_id: UUID, when: datetime) -> None: ...

    def revoke(self, token_id: UUID, user_id: UUID, when: datetime) -> bool: ...

    def list_api_keys(self, user_id: UUID, *, limit: int, offset: int) -> Paged[ApiKeyRead]: ...

    def get_user(self, user_id: UUID) -> StoredUser | None: ...

    def revoke_all(self, user_id: UUID, when: datetime, *, keep: UUID | None = None) -> int: ...

    def add_reset(self, user_id: UUID, token_hash: str, expires_at: datetime) -> None: ...

    def find_reset(self, token_hash: str) -> StoredReset | None: ...

    def use_reset(self, reset_id: UUID, when: datetime) -> bool: ...

    def void_resets(self, user_id: UUID, when: datetime) -> None: ...

    def session_ids(self, user_id: UUID) -> list[UUID]: ...

    def list_sessions(self, user_id: UUID, *, limit: int, offset: int) -> Paged[SessionRead]: ...

    def update_user(
        self, user_id: UUID, *, role: Role | None, disabled: bool | None
    ) -> UserRead | None: ...

    def set_email(self, user_id: UUID, email: str) -> None: ...

    def count_admins(self) -> int: ...

    def delete_user(self, user_id: UUID) -> bool: ...


class PostgresAuthRepository:
    """Each write commits on its own."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def count_users(self) -> int:
        return int(self._session.execute(text("SELECT count(*) FROM users")).scalar_one())

    def add_user(self, email: str, password_hash: str, role: Role) -> UserRead:
        try:
            row = (
                self._session.execute(
                    text(
                        "INSERT INTO users (email, password_hash, role)"  # noqa: S608
                        f" VALUES (:email, :hash, :role) RETURNING {_USER}"
                    ),
                    {"email": email, "hash": password_hash, "role": role},
                )
                .mappings()
                .one()
            )
        except IntegrityError as error:  # the unique index on lower(email)
            self._session.rollback()
            raise ConflictError(f"an account with the email {email} already exists") from error
        self._session.commit()
        return UserRead.model_validate(row)

    def find_user(self, email: str) -> StoredUser | None:
        row = (
            self._session.execute(
                text(
                    f"SELECT {_USER}, password_hash FROM users"  # noqa: S608 - constant columns
                    " WHERE lower(email) = lower(:email)"
                ),
                {"email": email},
            )
            .mappings()
            .one_or_none()
        )
        return StoredUser.model_validate(row) if row else None

    def set_password_hash(self, user_id: UUID, password_hash: str) -> None:
        self._session.execute(
            text("UPDATE users SET password_hash = :hash WHERE user_id = :id"),
            {"hash": password_hash, "id": user_id},
        )
        self._session.commit()

    def list_users(self, *, limit: int, offset: int) -> Paged[UserRead]:
        rows = self._session.execute(
            text(
                f"SELECT {_USER} FROM users"  # noqa: S608 - constant columns
                " ORDER BY created_at, user_id LIMIT :limit OFFSET :offset"
            ),
            {"limit": limit, "offset": offset},
        ).mappings()
        items = [UserRead.model_validate(row) for row in rows]
        return Paged(items, self.count_users())

    def add_token(
        self,
        *,
        user_id: UUID,
        kind: TokenKind,
        name: str,
        token_hash: str,
        prefix: str,
        expires_at: datetime,
    ) -> ApiKeyRead:
        row = (
            self._session.execute(
                text(
                    "INSERT INTO auth_tokens (user_id, kind, name, token_hash, prefix, expires_at)"  # noqa: S608
                    " VALUES (:user_id, :kind, :name, :hash, :prefix, :expires_at)"
                    f" RETURNING {_KEY}"
                ),
                {
                    "user_id": user_id,
                    "kind": kind,
                    "name": name,
                    "hash": token_hash,
                    "prefix": prefix,
                    "expires_at": expires_at,
                },
            )
            .mappings()
            .one()
        )
        self._session.commit()
        return ApiKeyRead.model_validate(row)

    def find_token(self, token_hash: str) -> StoredToken | None:
        row = (
            self._session.execute(
                text(
                    "SELECT t.token_id, t.user_id, t.kind, t.expires_at, t.revoked_at,"
                    " t.last_used_at, u.email, u.role, u.disabled"
                    " FROM auth_tokens t JOIN users u ON u.user_id = t.user_id"
                    " WHERE t.token_hash = :hash"
                ),
                {"hash": token_hash},
            )
            .mappings()
            .one_or_none()
        )
        return StoredToken.model_validate(row) if row else None

    def touch(self, token_id: UUID, when: datetime) -> None:
        self._session.execute(
            text("UPDATE auth_tokens SET last_used_at = :when WHERE token_id = :id"),
            {"when": when, "id": token_id},
        )
        self._session.commit()

    def revoke(self, token_id: UUID, user_id: UUID, when: datetime) -> bool:
        result = self._session.execute(
            text(
                "UPDATE auth_tokens SET revoked_at = :when"
                " WHERE token_id = :id AND user_id = :user_id AND revoked_at IS NULL"
            ),
            {"when": when, "id": token_id, "user_id": user_id},
        )
        self._session.commit()
        return bool(result.rowcount)  # type: ignore[attr-defined]

    def list_api_keys(self, user_id: UUID, *, limit: int, offset: int) -> Paged[ApiKeyRead]:
        params = {"user_id": user_id, "limit": limit, "offset": offset}
        rows = self._session.execute(
            text(
                f"SELECT {_KEY} FROM auth_tokens"  # noqa: S608 - constant columns
                " WHERE user_id = :user_id AND kind = 'api_key'"
                " ORDER BY created_at DESC, token_id LIMIT :limit OFFSET :offset"
            ),
            params,
        ).mappings()
        items = [ApiKeyRead.model_validate(row) for row in rows]
        total = self._session.execute(
            text("SELECT count(*) FROM auth_tokens WHERE user_id = :user_id AND kind = 'api_key'"),
            params,
        ).scalar_one()
        return Paged(items, int(total))

    def get_user(self, user_id: UUID) -> StoredUser | None:
        row = (
            self._session.execute(
                text(f"SELECT {_USER}, password_hash FROM users WHERE user_id = :id"),  # noqa: S608
                {"id": user_id},
            )
            .mappings()
            .one_or_none()
        )
        return StoredUser.model_validate(row) if row else None

    def revoke_all(self, user_id: UUID, when: datetime, *, keep: UUID | None = None) -> int:
        """Revoke every active token of the user (but ``keep``); returns how many."""
        result = self._session.execute(
            text(
                "UPDATE auth_tokens SET revoked_at = :when WHERE user_id = :user_id"
                " AND revoked_at IS NULL AND (CAST(:keep AS uuid) IS NULL OR token_id <> :keep)"
            ),
            {"when": when, "user_id": user_id, "keep": keep},
        )
        self._session.commit()
        return int(result.rowcount)  # type: ignore[attr-defined]

    def add_reset(self, user_id: UUID, token_hash: str, expires_at: datetime) -> None:
        self._session.execute(
            text(
                "INSERT INTO password_resets (user_id, token_hash, expires_at)"
                " VALUES (:user_id, :hash, :expires_at)"
            ),
            {"user_id": user_id, "hash": token_hash, "expires_at": expires_at},
        )
        self._session.commit()

    def find_reset(self, token_hash: str) -> StoredReset | None:
        row = (
            self._session.execute(
                text(
                    "SELECT r.reset_id, r.user_id, r.expires_at, r.used_at, u.email, u.disabled"
                    " FROM password_resets r JOIN users u ON u.user_id = r.user_id"
                    " WHERE r.token_hash = :hash"
                ),
                {"hash": token_hash},
            )
            .mappings()
            .one_or_none()
        )
        return StoredReset.model_validate(row) if row else None

    def use_reset(self, reset_id: UUID, when: datetime) -> bool:
        """Mark a reset token used; False if it already was (two requests racing)."""
        result = self._session.execute(
            text(
                "UPDATE password_resets SET used_at = :when"
                " WHERE reset_id = :id AND used_at IS NULL"
            ),
            {"when": when, "id": reset_id},
        )
        self._session.commit()
        return bool(result.rowcount)  # type: ignore[attr-defined]

    def void_resets(self, user_id: UUID, when: datetime) -> None:
        """Retire the user's unused reset tokens: only the newest link should work."""
        self._session.execute(
            text(
                "UPDATE password_resets SET used_at = :when"
                " WHERE user_id = :user_id AND used_at IS NULL"
            ),
            {"when": when, "user_id": user_id},
        )
        self._session.commit()

    def session_ids(self, user_id: UUID) -> list[UUID]:
        """The user's active login tokens (not API keys)."""
        rows = self._session.execute(
            text(
                "SELECT token_id FROM auth_tokens WHERE user_id = :user_id AND kind = 'session'"
                " AND revoked_at IS NULL"
            ),
            {"user_id": user_id},
        )
        return [row.token_id for row in rows]

    def list_sessions(self, user_id: UUID, *, limit: int, offset: int) -> Paged[SessionRead]:
        params = {"user_id": user_id, "limit": limit, "offset": offset}
        active = (
            "user_id = :user_id AND kind = 'session' AND revoked_at IS NULL AND expires_at > now()"
        )
        rows = self._session.execute(
            text(
                "SELECT token_id, prefix, created_at, expires_at, last_used_at FROM auth_tokens"  # noqa: S608
                f" WHERE {active} ORDER BY created_at DESC, token_id LIMIT :limit OFFSET :offset"
            ),
            params,
        ).mappings()
        items = [SessionRead.model_validate(row) for row in rows]
        total = self._session.execute(
            text(f"SELECT count(*) FROM auth_tokens WHERE {active}"),  # noqa: S608
            params,
        ).scalar_one()
        return Paged(items, int(total))

    def update_user(
        self, user_id: UUID, *, role: Role | None, disabled: bool | None
    ) -> UserRead | None:
        row = (
            self._session.execute(
                text(
                    "UPDATE users SET role = coalesce(:role, role),"  # noqa: S608
                    " disabled = coalesce(:disabled, disabled)"
                    f" WHERE user_id = :id RETURNING {_USER}"
                ),
                {"role": role, "disabled": disabled, "id": user_id},
            )
            .mappings()
            .one_or_none()
        )
        self._session.commit()
        return UserRead.model_validate(row) if row else None

    def set_email(self, user_id: UUID, email: str) -> None:
        try:
            self._session.execute(
                text("UPDATE users SET email = :email WHERE user_id = :id"),
                {"email": email, "id": user_id},
            )
            self._session.commit()
        except IntegrityError as error:
            self._session.rollback()
            raise ConflictError(f"an account with the email {email} already exists") from error

    def count_admins(self) -> int:
        return int(
            self._session.execute(
                text("SELECT count(*) FROM users WHERE role = 'admin' AND NOT disabled")
            ).scalar_one()
        )

    def delete_user(self, user_id: UUID) -> bool:
        """Delete the account; its tokens, resets and shows (with everything under them) go too."""
        result = self._session.execute(
            text("DELETE FROM users WHERE user_id = :id"), {"id": user_id}
        )
        self._session.commit()
        return bool(result.rowcount)  # type: ignore[attr-defined]

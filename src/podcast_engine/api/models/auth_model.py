"""Request and response schemas for login, users and API keys."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Role = Literal["admin", "creator"]
TokenKind = Literal["session", "api_key"]
Email = Annotated[
    str,
    Field(
        min_length=3,
        max_length=254,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
        description="Email address, used to log in",
        examples=["ada@example.org"],
    ),
]
Password = Annotated[
    str,
    Field(
        min_length=12,
        max_length=256,
        description="At least 12 characters; a passphrase is best",
        examples=["correct horse battery staple"],
    ),
]


class RegisterRequest(BaseModel):
    email: Email
    password: Password
    role: Role = Field(
        default="creator", description="Ignored for the first user, who is always `admin`"
    )


class LoginRequest(BaseModel):
    email: Email
    password: str = Field(min_length=1, max_length=256, description="The account's password")


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID = Field(description="The user's id")
    email: str = Field(description="Email address")
    role: Role = Field(description="`admin` can add users; `creator` makes shows")
    disabled: bool = Field(description="A disabled user cannot log in or use a token")
    created_at: datetime = Field(description="When the account was created")


class TokenResponse(BaseModel):
    """A login token. Send it as `Authorization: Bearer <access_token>`."""

    access_token: str = Field(description="The token; shown only now, never again")
    token_type: Literal["bearer"] = Field(default="bearer", description="How to send it")
    token_id: UUID = Field(description="Its id, to recognise or revoke it")
    expires_at: datetime = Field(description="When it stops working (six months from now)")


class ApiKeyCreate(BaseModel):
    name: str = Field(
        min_length=1, max_length=100, description="What the key is for", examples=["CI pipeline"]
    )


class ApiKeyRead(BaseModel):
    """An API key, without the key itself (which is stored only as a hash)."""

    model_config = ConfigDict(from_attributes=True)

    token_id: UUID = Field(description="The key's id")
    name: str = Field(description="What the key is for")
    prefix: str = Field(
        description="The key's first characters, to recognise it", examples=["pek_3Fq9"]
    )
    created_at: datetime = Field(description="When it was created")
    expires_at: datetime = Field(description="When it stops working")
    last_used_at: datetime | None = Field(description="When it was last used; null if never")
    revoked_at: datetime | None = Field(description="When it was revoked; null if it is active")


class ApiKeyCreated(ApiKeyRead):
    key: str = Field(description="The key; shown only now, never again. Send it as a bearer token")


class CurrentUser(BaseModel):
    """Who is making the request, and with which token."""

    user_id: UUID = Field(description="The user's id")
    email: str = Field(description="Email address")
    role: Role = Field(description="The user's role")
    token_id: UUID = Field(description="The token this request used")
    token_kind: TokenKind = Field(description="`session` (from login) or `api_key`")
    expires_at: datetime = Field(description="When that token stops working")


class StoredToken(BaseModel):
    """A token row joined with its user (internal, not a response)."""

    token_id: UUID
    user_id: UUID
    kind: TokenKind
    expires_at: datetime
    revoked_at: datetime | None
    last_used_at: datetime | None
    email: str
    role: Role
    disabled: bool


class StoredUser(UserRead):
    """A user with the password hash (internal, never a response)."""

    password_hash: str


class PasswordResetRequest(BaseModel):
    email: Email


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=10, max_length=200, description="The token from the reset link")
    new_password: Password


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=256, description="Your password now")
    new_password: Password


class Accepted(BaseModel):
    detail: str = Field(description="What happens next")


class StoredReset(BaseModel):
    """A reset token row joined with its user (internal, not a response)."""

    reset_id: UUID
    user_id: UUID
    expires_at: datetime
    used_at: datetime | None
    email: str
    disabled: bool


class UserUpdate(BaseModel):
    """What an admin may change about an account. Omitted fields stay as they are."""

    role: Role | None = Field(default=None, description="`admin` or `creator`")
    disabled: bool | None = Field(
        default=None, description="A disabled account cannot sign in; its tokens stop working"
    )


class AccountDelete(BaseModel):
    password: str = Field(min_length=1, max_length=256, description="Your password, to confirm")


class EmailChange(BaseModel):
    password: str = Field(min_length=1, max_length=256, description="Your password, to confirm")
    new_email: Email


class SessionRead(BaseModel):
    """A login token (a signed-in browser or device), without the token itself."""

    model_config = ConfigDict(from_attributes=True)

    token_id: UUID = Field(description="The sign-in's id")
    prefix: str = Field(description="The token's first characters")
    created_at: datetime = Field(description="When you signed in")
    expires_at: datetime = Field(description="When it stops working")
    last_used_at: datetime | None = Field(description="When it was last used")
    current: bool = Field(default=False, description="True for the sign-in making this request")


SecurityEventName = Literal[
    "user_registered",
    "login_succeeded",
    "login_failed",
    "account_locked",
    "login_throttled",
    "logout",
    "session_revoked",
    "password_reset_requested",
    "password_reset_completed",
    "password_changed",
    "email_changed",
    "api_key_created",
    "api_key_revoked",
    "user_updated",
    "user_deleted",
    "account_deleted",
]


class SecurityEventRead(BaseModel):
    """One entry in the security log."""

    model_config = ConfigDict(from_attributes=True)

    event_id: UUID = Field(description="The entry's id")
    user_id: UUID | None = Field(description="The account it concerns; null if unknown or deleted")
    event: str = Field(description="What happened", examples=["login_failed"])
    address: str = Field(description="The client address it came from")
    detail: dict[str, object] = Field(description="Extra facts, never secrets")
    created_at: datetime = Field(description="When")

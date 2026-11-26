"""Request and response schemas for login, users and API keys."""

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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


HexColour = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]
# A preset's name or any colour as #rrggbb.
BodyColour = Literal["pearl", "peach", "mint", "sky", "lilac", "lemon", "graphite"] | HexColour
GlowColour = Literal["amber", "gold", "cyan", "lime", "pink", "violet"] | HexColour

# Version 1 had one accessory; it now lives in the slot it belongs to.
_OLD_ACCESSORY = {"antenna": ("hat", "antenna"), "headphones": ("hat", "headphones"),
                  "bowtie": ("neck", "bowtie")}  # fmt: skip


class BotVoice(BaseModel):
    """How the bot reads its lines aloud, when the person turns speech on."""

    engine: Literal["browser", "gemini"] = Field(
        default="browser",
        description="`browser`: the device's own speech, free; `gemini`: Gemini TTS (uses quota)",
    )
    name: str = Field(
        default="", max_length=80, description="Voice name; empty picks the default for the engine"
    )
    rate: float = Field(default=1.0, ge=0.5, le=2.0, description="Speaking speed, 1 is normal")
    pitch: float = Field(default=1.0, ge=0.0, le=2.0, description="Pitch, 1 is normal")


class Avatar(BaseModel):
    """The assistant bot a person chose: which character, what it is called and how it looks.

    Every part has a default, so a bot saved by an older version of the app still loads.
    """

    character: Literal["toy", "pod", "rex"] = Field(
        default="toy",
        description="`toy`: the build-your-own bot; `pod`: the floating podcast bot; "
        "`rex`: the full-body robot with moves",
    )
    name: str = Field(
        default="James", min_length=1, max_length=24, description="What the bot is called"
    )
    color: BodyColour = Field(default="pearl", description="Body colour: a preset or #rrggbb")
    accent: HexColour = Field(default="#c2410c", description="Trim and outfit colour, #rrggbb")
    glow: GlowColour = Field(
        default="amber", description="Colour of its eyes and lights: a preset or #rrggbb"
    )
    finish: Literal["matte", "glossy", "metallic", "pearlescent"] = Field(
        default="glossy", description="What its shell is made of"
    )
    body: Literal["round", "capsule", "boxy", "tall"] = Field(
        default="round", description="Body shape (toy only)"
    )
    head: Literal["sphere", "cube", "dome", "screen"] = Field(
        default="sphere", description="Head shape (toy only)"
    )
    eyes: Literal["dots", "visor", "pixel", "sleepy", "star"] = Field(
        default="dots", description="Eye style (toy only)"
    )
    mouth: Literal["smile", "open", "line", "none"] = Field(
        default="smile", description="Mouth style (toy only)"
    )
    hat: Literal["none", "antenna", "headphones", "cap", "beanie", "crown", "halo"] = Field(
        default="antenna", description="What it wears on its head"
    )
    neck: Literal["none", "bowtie", "scarf", "medal"] = Field(
        default="none", description="What it wears at its neck"
    )
    extra: Literal["none", "glasses", "mic", "ears"] = Field(
        default="none", description="One more thing it carries or wears"
    )
    personality: Literal["cheerful", "calm", "witty", "formal"] = Field(
        default="cheerful", description="How it moves and how it talks"
    )
    voice: BotVoice = Field(default_factory=BotVoice, description="How it speaks")

    @model_validator(mode="before")
    @classmethod
    def _upgrade(cls, data: Any) -> Any:
        if isinstance(data, dict) and "accessory" in data:
            data = dict(data)
            slot = _OLD_ACCESSORY.get(data.pop("accessory"))
            if slot is None:
                data.setdefault("hat", "none")
            else:
                data.setdefault(slot[0], slot[1])
                if slot[0] != "hat":
                    data.setdefault("hat", "none")
        return data

    @field_validator("name")
    @classmethod
    def _tidy_name(cls, value: str) -> str:
        name = " ".join(value.split())
        if not name:
            raise ValueError("the name needs at least one visible character")
        return name

    @field_validator("accent", "color", "glow")
    @classmethod
    def _lower_hex(cls, value: str) -> str:
        return value.lower() if value.startswith("#") else value


class CurrentUser(BaseModel):
    """Who is making the request, and with which token."""

    user_id: UUID = Field(description="The user's id")
    email: str = Field(description="Email address")
    role: Role = Field(description="The user's role")
    token_id: UUID = Field(description="The token this request used")
    token_kind: TokenKind = Field(description="`session` (from login) or `api_key`")
    expires_at: datetime = Field(description="When that token stops working")
    avatar: Avatar | None = Field(
        default=None, description="Their chosen assistant bot; null until they choose one"
    )


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
    avatar: dict[str, Any] | None = None


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


class SetupStatus(BaseModel):
    """Whether accounts can be created without signing in: the first one, or anyone's own."""

    first_account_open: bool = Field(
        description="True until the first account exists; that account becomes the admin"
    )
    signup_open: bool = Field(
        default=False,
        description="True when anyone may create their own account (always a `creator`)",
    )
    google_sign_in: bool = Field(
        default=False,
        description="True when people can sign in with Google (`GET /auth/google/start`)",
    )

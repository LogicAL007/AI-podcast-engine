"""Schemas for cloned voices: a recording of someone's voice, kept with their consent record."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field

from podcast_engine.api.paths import V1

# The consent form's wording. Each voice stores the version and text its speaker agreed to, so a
# later change of wording never rewrites what someone signed.
CONSENT_VERSION = "2026-10-25"
CONSENT_STATEMENT = (
    "I am the person speaking in this recording, or I hold their written permission to use it. "
    "I agree that Podcast Engine may use it to create a synthetic copy of this voice, used only "
    "to read scripts for this account's podcasts. Episodes voiced with it are labelled as "
    "AI-generated. Consent can be withdrawn at any time by deleting the voice, which removes the "
    "recording and stops its use in new episodes."
)

Relationship = Literal["self", "permission"]
VoiceSource = Literal["recorded", "uploaded"]


class VoiceConsent(BaseModel):
    """What the speaker agreed to, as signed."""

    version: str = Field(description="Which wording of the consent form was signed")
    statement: str = Field(description="The exact text agreed to")
    relationship: Relationship = Field(
        description="`self`: the speaker signed for their own voice; `permission`: the account "
        "holder holds the speaker's written permission"
    )
    signed_by: str = Field(description="The full name typed as a signature")
    permission_record: str = Field(
        default="", description="Where the speaker's written permission is kept (permission only)"
    )
    agreed_at: datetime = Field(description="When the form was signed")


class VoiceRead(BaseModel):
    """A registered voice. Only its owner sees it, and only the Chatterbox backend can clone it."""

    model_config = ConfigDict(from_attributes=True)

    voice_id: UUID = Field(description="The voice's id")
    name: str = Field(description="A label for the voice", examples=["My voice"])
    speaker: str = Field(description="Whose voice it is")
    license: str = Field(description="The terms the recording may be used under")
    source: VoiceSource = Field(description="Recorded in the browser, or an uploaded file")
    duration_seconds: float = Field(description="Length of the recording")
    consent: VoiceConsent = Field(description="The consent record")
    created_at: datetime = Field(description="When it was registered")
    object_key: str = Field(exclude=True)

    @computed_field(description="Where to play the recording (its owner only)")  # type: ignore[prop-decorator]
    @property
    def audio(self) -> str:
        return f"{V1}/voices/{self.voice_id}/audio.wav"


class ConsentForm(BaseModel):
    """The consent form as submitted with a recording (internal, not a request body)."""

    name: str
    speaker: str
    license: str
    relationship: Relationship
    signature: str
    permission_record: str = ""
    agree_clone: bool
    agree_ai_label: bool
    agree_withdraw: bool

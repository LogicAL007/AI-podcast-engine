from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field

from podcast_engine.api.paths import V1
from podcast_engine.common.context import HOST_NAMES
from podcast_engine.common.models import Delivery
from podcast_engine.common.voice_fx import VoiceEffects

MAX_CHARACTERS = 600
HostName = Literal["Alex", "Sam", "Jordan", "Riley"]
assert set(HOST_NAMES) == {"Alex", "Sam", "Jordan", "Riley"}  # noqa: S101 - keep the two in step
ClipStatus = Literal["queued", "working", "done", "failed"]


class RecordedVoice(BaseModel):
    """One of your registered (recorded) voices. Needs the Chatterbox voice engine."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["recorded"] = "recorded"
    voice_id: UUID = Field(description="The voice's id (see /voices)")


class EngineVoice(BaseModel):
    """The voice engine's own voice for a host: a Gemini prebuilt voice, or Chatterbox's default."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["engine"] = "engine"
    host: HostName = Field(description="Whose engine voice: Alex, Sam, Jordan or Riley")


SpeechVoice = Annotated[RecordedVoice | EngineVoice, Field(discriminator="kind")]


class SpeechCreate(BaseModel):
    """A line to voice."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "text": "Welcome back to the show. Today we are talking about tides.",
                    "voice": {"kind": "engine", "host": "Alex"},
                    "delivery": "warm",
                    "effects": {"deepen": 40, "warmth": 20, "broadcast": True},
                }
            ]
        },
    )

    text: str = Field(
        min_length=1, max_length=MAX_CHARACTERS, description="What to say (up to 600 characters)"
    )
    voice: SpeechVoice
    delivery: Delivery = Field(Delivery.NEUTRAL, description="How it is said")
    effects: VoiceEffects = Field(default_factory=VoiceEffects, description="Voice effects")


class SpeechClipRead(BaseModel):
    """A type-to-speech clip: queued, being voiced, done (with its audio) or failed (with why)."""

    model_config = ConfigDict(from_attributes=True)

    clip_id: UUID = Field(description="The clip's id")
    voice: SpeechVoice
    text: str = Field(description="What it says")
    delivery: str = Field(description="How it is said")
    effects: VoiceEffects = Field(description="The voice effects applied")
    status: ClipStatus = Field(description="queued, working, done or failed")
    duration_s: float | None = Field(None, description="Length, once done")
    error: str | None = Field(None, description="Why it failed")
    created_at: datetime = Field(description="When it was asked for")
    finished_at: datetime | None = Field(None, description="When it was done or failed")

    @computed_field(description="Where to play or download it, once done")  # type: ignore[prop-decorator]
    @property
    def audio(self) -> str | None:
        """Path in the API to play or download the clip, once it is done."""
        return f"{V1}/speech/{self.clip_id}/audio.wav" if self.status == "done" else None


class EngineVoiceOption(BaseModel):
    """One of the engine's own voices, as a picker offers it."""

    host: HostName = Field(description="Use as EngineVoice.host")
    label: str = Field(description="What to call it in a picker")


class SpeechEngine(BaseModel):
    """What this server's voice engine can say, and today's budget for it."""

    backend: str = Field(description="The voice engine: chatterbox, gemini, say or placeholder")
    recorded_voices: bool = Field(description="Whether recorded voices can speak here")
    engine_voices: list[EngineVoiceOption] = Field(description="The engine's own voices")
    uses_quota: bool = Field(description="Whether each clip spends the daily Gemini TTS budget")
    clips_left_today: int | None = Field(
        None, description="Clips the shared Gemini budget still allows today (Gemini only)"
    )
    max_characters: int = Field(MAX_CHARACTERS, description="Longest text accepted")
    deliveries: list[str] = Field(description="Delivery styles")
    presets: dict[str, VoiceEffects] = Field(description="Named effect settings")

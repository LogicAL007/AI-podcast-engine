from typing import Literal

from pydantic import BaseModel, Field


class ModelUsage(BaseModel):
    """One Gemini model's requests today."""

    model: str = Field(description="The Gemini model", examples=["gemini-3.8-flash"])
    kind: Literal["text", "voice"] = Field(
        description="`text`: plans, scripts, fact-checks and the bot; `voice`: speech"
    )
    used: int = Field(description="Requests sent today (Pacific time)")
    limit: int | None = Field(description="Today's cap (LLM_/TTS_REQUESTS_PER_DAY); null: none")
    left: int | None = Field(description="Requests left today; null when there is no cap")


class UsageRead(BaseModel):
    """What today's Gemini budget allows, shared by every account on this server."""

    day: str = Field(description="Today's date in Pacific time, when Gemini's quota resets")
    resets_in_seconds: int = Field(description="Seconds until the quota resets (midnight Pacific)")
    writer: Literal["gemini", "offline"] = Field(
        description="Who writes scripts: Gemini, or the offline extractive writer"
    )
    voice_engine: str = Field(
        description="What voices episodes: `gemini`, `chatterbox` (cloned voices, no quota), "
        "`say` or `placeholder`",
        examples=["chatterbox"],
    )
    models: list[ModelUsage] = Field(description="The Gemini models in use and their budgets")

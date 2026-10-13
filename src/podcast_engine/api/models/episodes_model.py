"""Response schemas for the episodes API."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field

from podcast_engine.common.models import EpisodeStatus

AUDIO_MEDIA_TYPE = "audio/wav"
NOTES_MEDIA_TYPE = "text/markdown; charset=utf-8"


class EpisodeLinks(BaseModel):
    """Where to fetch what the episode produced, relative to the API's base URL.

    ``audio`` and ``notes`` are null until the pipeline has produced them.
    """

    self: str = Field(
        description="This episode", examples=["/episodes/3fa85f64-5717-4562-b3fc-2c963f66afa6"]
    )
    script: str = Field(description="Script with citations and fact-check verdicts")
    runs: str = Field(description="Per-stage run records")
    audio: str | None = Field(description="The episode audio (WAV), once assembled")
    notes: str | None = Field(description="Show notes (Markdown), once published")
    feed: str = Field(description="The show's RSS feed")


class EpisodeRead(BaseModel):
    """An episode and its progress through the pipeline."""

    model_config = ConfigDict(from_attributes=True)

    episode_id: UUID = Field(description="The episode's id")
    show_id: UUID = Field(description="The show it belongs to")
    status: EpisodeStatus = Field(
        description=(
            "`queued` → `processing` → `published`. Or `needs_review` (the fact-check gate "
            "held it), "
            "`unchanged` (a refresh found no changed source) or `failed`; `error` says why."
        )
    )
    stage: str | None = Field(
        default=None, description="The stage running, or the last one that ran", examples=["voice"]
    )
    error: str | None = Field(
        default=None, description="Why it failed, was held for review, or was not regenerated"
    )
    revision: int = Field(default=1, description="1 for a show's first episode, +1 per refresh")
    rewrite_count: int = Field(description="Times the fact-check gate sent the script back")
    created_at: datetime = Field(description="When the episode was started")
    published_at: datetime | None = Field(description="When it was published; null until then")
    approved_at: datetime | None = Field(
        default=None, description="When a reviewer released it to voicing; null if never"
    )
    has_audio: bool = Field(default=False, exclude=True)
    has_notes: bool = Field(default=False, exclude=True)

    @computed_field(description="Where to fetch what the episode produced")  # type: ignore[prop-decorator]
    @property
    def links(self) -> EpisodeLinks:
        base = f"/episodes/{self.episode_id}"
        return EpisodeLinks(
            self=base,
            script=f"{base}/script",
            runs=f"{base}/runs",
            audio=f"{base}/audio.wav" if self.has_audio else None,
            notes=f"{base}/notes.md" if self.has_notes else None,
            feed=f"/feeds/{self.show_id}/rss.xml",
        )


class ClaimRead(BaseModel):
    """A factual statement in the script and the evidence for it."""

    text: str = Field(description="The claim as spoken")
    chunk_ids: list[UUID] = Field(description="Passages cited as support; empty means uncited")
    supported: bool | None = Field(
        default=None, description="The fact-check verdict; null until the gate has judged it"
    )
    reason: str | None = Field(
        default=None, description="The judge's reason", examples=["word overlap 100%"]
    )


class LineRead(BaseModel):
    """One spoken line."""

    speaker: str = Field(description="The host who says it", examples=["Alex"])
    text: str = Field(description="What is said")
    claims: list[ClaimRead] = Field(
        default=[], description="Claims in this line; empty for framing"
    )


class SegmentScript(BaseModel):
    """One segment of the outline and its lines."""

    position: int = Field(description="Order in the episode, from 1")
    title: str = Field(description="Segment heading, also the chapter title")
    source_item_ids: list[UUID] = Field(description="The source sections this segment draws on")
    lines: list[LineRead] = Field(description="The dialogue, in order")


class EpisodeScript(BaseModel):
    """The script with each claim's citations and verdict, for review."""

    episode_id: UUID = Field(description="The episode's id")
    segments: list[SegmentScript] = Field(description="Segments in order; empty until scripted")
    fact_check: dict[str, Any] | None = Field(
        default=None,
        description=(
            "The gate's judge, each pass (claims, unsupported, support rate, next stage) and "
            "the flagged claims"
        ),
    )


class StageRunRead(BaseModel):
    """One completed stage run, for transparency and reproducibility."""

    model_config = ConfigDict(from_attributes=True)

    stage: str = Field(description="Pipeline stage", examples=["script"])
    seconds: float | None = Field(description="How long it took")
    model: str | None = Field(
        description="Model or backend used", examples=["gemini:gemini-3.8-flash"]
    )
    prompt_version: str | None = Field(
        description="Prompt file used, if any", examples=["script.v2"]
    )
    seed: int | None = Field(description="Random seed, so the run can be repeated")
    started_at: datetime = Field(description="When the record was written")


class EpisodeFiles(BaseModel):
    """Where an episode's published files live in object storage (internal, not a response)."""

    audio_key: str | None
    notes_key: str | None


class ClaimDetail(BaseModel):
    """A claim in the episode's script, with where it is and how the fact-check judged it."""

    model_config = ConfigDict(from_attributes=True)

    claim_id: UUID = Field(description="The claim's id")
    segment: int = Field(description="Position of the segment it is in, from 1")
    text: str = Field(description="The claim as spoken")
    chunk_ids: list[UUID] = Field(description="Passages cited as support; empty means uncited")
    supported: bool | None = Field(description="The verdict; null until judged")
    reason: str | None = Field(description="The judge's reason", examples=["word overlap 100%"])


class LineEdit(BaseModel):
    """One line of a replacement segment."""

    speaker: str = Field(description="One of the show's hosts", examples=["Sam"])
    text: str = Field(min_length=1, max_length=2000, description="What is said")
    chunk_ids: list[UUID] | None = Field(
        default=None,
        description=(
            "Passages that support the line, which makes it a claim. Null for framing or "
            "reactions; an empty list is a claim with no citation, which the fact-check rejects"
        ),
    )


class SegmentEdit(BaseModel):
    """The new lines for one segment; they replace all of its current lines."""

    position: int = Field(ge=1, description="Which segment, from 1")
    lines: list[LineEdit] = Field(min_length=1, max_length=200, description="The segment's lines")


class ScriptEdit(BaseModel):
    """Replacement lines for one or more segments. Segments not listed stay as they are."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "segments": [
                        {
                            "position": 2,
                            "lines": [
                                {"speaker": "Alex", "text": "Next up: column storage."},
                                {
                                    "speaker": "Sam",
                                    "text": "ClickHouse stores each column separately.",
                                    "chunk_ids": ["3fa85f64-5717-4562-b3fc-2c963f66afa6"],
                                },
                            ],
                        }
                    ]
                }
            ]
        }
    )

    segments: list[SegmentEdit] = Field(min_length=1, description="Segments to replace")

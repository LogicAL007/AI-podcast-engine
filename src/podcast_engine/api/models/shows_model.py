"""Request and response schemas for the shows API."""

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AfterValidator, AnyHttpUrl, BaseModel, ConfigDict, Field

from podcast_engine.common.context import HOST_NAMES
from podcast_engine.common.models import ExpertiseLevel, Tone
from podcast_engine.common.music import ShowMusic
from podcast_engine.common.voice_fx import VoiceEffects

Topic = Annotated[
    str,
    Field(
        min_length=3,
        max_length=200,
        description="What the show is about; spoken in the opening and matched against passages",
        examples=["What ClickHouse is and why it is fast for analytics"],
    ),
]
ToneField = Annotated[Tone, Field(description="Speaking style of the hosts")]
Minutes = Annotated[int, Field(ge=1, le=30, description="Target episode length in minutes")]
HostCount = Annotated[
    int, Field(ge=1, le=4, description="Number of hosts, each with a distinct voice")
]
Language = Annotated[
    str,
    Field(
        pattern=r"^[a-z]{2}(-[A-Z]{2})?$",
        description="BCP 47 language tag",
        examples=["en", "fr-CA"],
    ),
]
Expertise = Annotated[ExpertiseLevel, Field(description="How much the audience already knows")]
SourceUrls = Annotated[
    list[AnyHttpUrl],
    Field(
        max_length=50,
        description="Web pages to build episodes from; each page section becomes a citable source",
        examples=[["https://clickhouse.com/docs/get-started/about/intro"]],
    ),
]


def _tidy_queries(value: list[str]) -> list[str]:
    queries = list(dict.fromkeys(" ".join(q.split()) for q in value))
    if any(len(q) < 2 for q in queries):
        raise ValueError("a search needs at least 2 characters")
    return queries


SearchQueries = Annotated[
    list[Annotated[str, Field(max_length=200)]],
    AfterValidator(_tidy_queries),
    Field(
        max_length=3,
        description=(
            "Searches run each time an episode is made; the top results are read like the "
            "show's own pages, so a refresh picks up new results (FR2). Up to 3"
        ),
        examples=[["ClickHouse column-oriented database"]],
    ),
]
Keywords = Annotated[
    str,
    Field(
        max_length=1000,
        description="Words that describe the topic, used with it to match passages",
        examples=["ClickHouse column-oriented database OLAP analytics queries"],
    ),
]
Attribution = Annotated[
    str,
    Field(
        max_length=2000,
        description="Credit and licence line printed in the show notes",
        examples=["Source material: ClickHouse Documentation, CC BY-NC-SA 4.0."],
    ),
]
MaxSegments = Annotated[
    int, Field(ge=1, le=12, description="At most this many segments per episode")
]
ReviewBeforeVoice = Annotated[
    bool,
    Field(
        description=(
            "Pause each episode after the fact-check until a person approves it, "
            "so nothing is voiced unreviewed"
        )
    ),
]


def _known_hosts[V](value: dict[str, V]) -> dict[str, V]:
    unknown = sorted(set(value) - set(HOST_NAMES))
    if unknown:
        raise ValueError(f"hosts are named {', '.join(HOST_NAMES)}; not {', '.join(unknown)}")
    return value


HostVoices = Annotated[
    dict[str, UUID],
    AfterValidator(_known_hosts),
    Field(
        description=(
            "A registered voice (see /voices) for each host who should speak with it, by host "
            "name: Alex, Sam, Jordan, Riley. Used by the Chatterbox voice backend; other hosts, "
            "and other backends, keep their own voices"
        ),
        examples=[{"Alex": "6f1c2e8a-0d5b-4f7e-9a3c-2b8d1e4f5a6b"}],
    ),
]
HostEffects = Annotated[
    dict[str, VoiceEffects],
    AfterValidator(_known_hosts),
    Field(
        description=(
            "Voice effects per host name (Alex, Sam, Jordan, Riley), applied when an episode is "
            "assembled: `deepen` (0-100, up to 5 semitones lower), `warmth` (0-100) and "
            "`broadcast` (compression, presence and de-essing, a radio voice)"
        ),
        examples=[{"Alex": {"deepen": 40, "warmth": 20, "broadcast": True}}],
    ),
]
Music = Annotated[
    ShowMusic,
    Field(
        description=(
            "Intro, outro, sting and bed: built-in tracks (GET /v1/music) or ones you uploaded. "
            "Empty slots keep the default chime, and no bed"
        )
    ),
]
RankingProfile = Annotated[
    Literal["daily", "explainer"],
    Field(description="`daily` favours fresh sources; `explainer` favours authoritative ones"),
]

EXAMPLE: dict[str, Any] = {
    "topic": "What ClickHouse is and why it is fast for analytics",
    "tone": "casual",
    "target_minutes": 7,
    "host_count": 2,
    "language": "en",
    "expertise": "beginner",
    "sources": ["https://clickhouse.com/docs/get-started/about/intro"],
    "search_queries": ["ClickHouse column-oriented database"],
    "topic_keywords": "ClickHouse column-oriented database OLAP analytics queries",
    "attribution": "Source material: ClickHouse Documentation, CC BY-NC-SA 4.0.",
    "max_segments": 6,
    "ranking_profile": "explainer",
    "review_before_voice": False,
}


class ShowCreate(BaseModel):
    """What a creator supplies to set up a show."""

    model_config = ConfigDict(json_schema_extra={"examples": [EXAMPLE]})

    topic: Topic
    tone: ToneField = Tone.NEUTRAL
    target_minutes: Minutes = 7
    host_count: HostCount = 2
    language: Language = "en"
    expertise: Expertise = ExpertiseLevel.INTERMEDIATE
    sources: SourceUrls = []
    search_queries: SearchQueries = []
    topic_keywords: Keywords = ""
    attribution: Attribution = ""
    max_segments: MaxSegments = 6
    ranking_profile: RankingProfile = "explainer"
    review_before_voice: ReviewBeforeVoice = False
    host_voices: HostVoices = {}
    host_effects: HostEffects = Field(default_factory=dict)  # optional for clients
    music: Music = Field(default_factory=ShowMusic)


class ShowUpdate(BaseModel):
    """Partial update: omitted or null fields are left unchanged."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"max_segments": 4, "tone": "formal"}]}
    )

    topic: Topic | None = None
    tone: ToneField | None = None
    target_minutes: Minutes | None = None
    host_count: HostCount | None = None
    language: Language | None = None
    expertise: Expertise | None = None
    sources: SourceUrls | None = None
    search_queries: SearchQueries | None = None
    topic_keywords: Keywords | None = None
    attribution: Attribution | None = None
    max_segments: MaxSegments | None = None
    ranking_profile: RankingProfile | None = None
    review_before_voice: ReviewBeforeVoice | None = None
    host_voices: HostVoices | None = None
    host_effects: HostEffects | None = None
    music: Music | None = None


class ShowRead(BaseModel):
    """A show as stored."""

    model_config = ConfigDict(from_attributes=True)

    show_id: UUID = Field(description="The show's id")
    topic: str = Field(description="What the show is about")
    tone: Tone = Field(description="Speaking style of the hosts")
    target_minutes: int = Field(description="Target episode length in minutes")
    host_count: int = Field(description="Number of hosts")
    language: str = Field(description="BCP 47 language tag")
    expertise: ExpertiseLevel = Field(description="How much the audience already knows")
    sources: list[str] = Field(description="Source page URLs")
    search_queries: list[str] = Field(
        default_factory=list, description="Searches whose top results are read as sources"
    )
    topic_keywords: str = Field(default="", description="Words matched with the topic")
    attribution: str = Field(default="", description="Credit and licence line for the show notes")
    max_segments: int = Field(default=6, description="At most this many segments per episode")
    ranking_profile: str = Field(default="explainer", description="`daily` or `explainer`")
    review_before_voice: bool = Field(
        default=False, description="Episodes pause for approval before voicing"
    )
    host_voices: dict[str, UUID] = Field(
        default_factory=dict, description="Registered voice per host name, for Chatterbox"
    )
    host_effects: dict[str, VoiceEffects] = Field(
        default_factory=dict, description="Voice effects per host name"
    )
    music: ShowMusic = Field(default_factory=ShowMusic, description="Intro, outro, sting and bed")
    created_at: datetime = Field(description="When the show was created")

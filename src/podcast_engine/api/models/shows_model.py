"""Request and response schemas for the shows API."""

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field

from podcast_engine.common.models import ExpertiseLevel, Tone

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
    topic_keywords: Keywords = ""
    attribution: Attribution = ""
    max_segments: MaxSegments = 6
    ranking_profile: RankingProfile = "explainer"
    review_before_voice: ReviewBeforeVoice = False


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
    topic_keywords: Keywords | None = None
    attribution: Attribution | None = None
    max_segments: MaxSegments | None = None
    ranking_profile: RankingProfile | None = None
    review_before_voice: ReviewBeforeVoice | None = None


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
    topic_keywords: str = Field(default="", description="Words matched with the topic")
    attribution: str = Field(default="", description="Credit and licence line for the show notes")
    max_segments: int = Field(default=6, description="At most this many segments per episode")
    ranking_profile: str = Field(default="explainer", description="`daily` or `explainer`")
    review_before_voice: bool = Field(
        default=False, description="Episodes pause for approval before voicing"
    )
    created_at: datetime = Field(description="When the show was created")

"""Response schemas for the music library: built-in tracks and the ones you upload."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field

from podcast_engine.api.paths import V1
from podcast_engine.common.music import Role


class MusicTrackRead(BaseModel):
    """A track for a show's intro, outro, sting or bed."""

    model_config = ConfigDict(from_attributes=True)

    track_id: str = Field(description="`builtin:...` for a built-in track, else the upload's id")
    name: str = Field(description="The track's name")
    role: Role = Field(description="What it is made for: bed, intro, outro, sting or any")
    builtin: bool = Field(description="Made in the app (no licence needed) or uploaded by you")
    description: str = Field("", description="What it sounds like (built-in tracks)")
    credit: str = Field("", description="Credit line added to the show notes of episodes using it")
    duration_seconds: float = Field(description="Length")
    created_at: datetime | None = Field(None, description="When it was uploaded")
    object_key: str | None = Field(None, exclude=True)

    @computed_field(description="Where to play it")  # type: ignore[prop-decorator]
    @property
    def audio(self) -> str:
        return f"{V1}/music/{self.track_id}/audio.wav"

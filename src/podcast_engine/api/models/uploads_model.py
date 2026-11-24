from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field

from podcast_engine.api.paths import V1

PDF_MEDIA_TYPE = "application/pdf"


class UploadRead(BaseModel):
    """An uploaded source file. Its text is read when the show's next episode is ingested."""

    model_config = ConfigDict(from_attributes=True)

    upload_id: UUID = Field(description="The upload's id")
    show_id: UUID = Field(description="The show it belongs to")
    filename: str = Field(description="The name it was uploaded with", examples=["whitepaper.pdf"])
    content_type: str = Field(description="Media type", examples=[PDF_MEDIA_TYPE])
    size_bytes: int = Field(description="File size")
    created_at: datetime = Field(description="When it was uploaded")
    object_key: str = Field(exclude=True)

    @computed_field(description="Where to download the file")  # type: ignore[prop-decorator]
    @property
    def file(self) -> str:
        """Path in the API to download the file."""
        return f"{V1}/shows/{self.show_id}/uploads/{self.upload_id}/file"


class UploadContent(BaseModel):
    """An upload's bytes, for downloading (internal, not a response)."""

    filename: str
    content_type: str
    data: bytes

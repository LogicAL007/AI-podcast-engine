from dataclasses import dataclass

from pydantic import BaseModel, Field


class Page[T](BaseModel):
    """One page of results, with the total and a link to the next page."""

    items: list[T] = Field(description="The results on this page")
    total: int = Field(description="Results across all pages", examples=[42])
    limit: int = Field(description="Most results per page, as requested", examples=[20])
    offset: int = Field(description="Results skipped before this page", examples=[0])
    next: str | None = Field(
        description="Path and query of the next page; null on the last page",
        examples=["/shows?limit=20&offset=20"],
    )


@dataclass(frozen=True)
class Paged[T]:
    """What a service returns for a list: one page of items and the total (no HTTP details)."""

    items: list[T]
    total: int

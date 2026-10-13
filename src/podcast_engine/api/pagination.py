"""Shared paging parameters and the conversion from a service result to a ``Page``."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Query, Request

from podcast_engine.api.models.pagination_model import Page, Paged

MAX_LIMIT = 100


@dataclass(frozen=True)
class PageParams:
    limit: int
    offset: int


def page_params(
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT, description="Most results to return")] = 20,
    offset: Annotated[int, Query(ge=0, description="Results to skip, for paging")] = 0,
) -> PageParams:
    return PageParams(limit=limit, offset=offset)


Paging = Annotated[PageParams, Depends(page_params)]


def to_page[T](result: Paged[T], params: PageParams, request: Request) -> Page[T]:
    """The response envelope. ``next`` keeps the request's filters and moves the offset on."""
    following = params.offset + params.limit
    next_url = None
    if following < result.total:
        url = request.url.include_query_params(limit=params.limit, offset=following)
        next_url = f"{url.path}?{url.query}"
    return Page[T](
        items=result.items,
        total=result.total,
        limit=params.limit,
        offset=params.offset,
        next=next_url,
    )

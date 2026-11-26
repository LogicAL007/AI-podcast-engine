from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Query, Request

from podcast_engine.api.models.pagination_model import Page, Paged

MAX_LIMIT = 100


@dataclass(frozen=True)
class PageParams:
    """The page size and offset a list request asked for."""

    limit: int
    offset: int


def page_params(
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT, description="Most results to return")] = 20,
    offset: Annotated[int, Query(ge=0, description="Results to skip, for paging")] = 0,
) -> PageParams:
    """Read the paging parameters from the query string (a FastAPI dependency).

    Args:
        limit: Most results to return, 1 to 100.
        offset: Results to skip, for paging.

    Returns:
        The validated page size and offset.
    """
    return PageParams(limit=limit, offset=offset)


Paging = Annotated[PageParams, Depends(page_params)]


def to_page[T](result: Paged[T], params: PageParams, request: Request) -> Page[T]:
    """Turn a service's result into the response envelope every list endpoint returns.

    ``next`` keeps the request's filters and moves the offset on; it is None on the last page.

    Args:
        result: One page of items and the total, from a service.
        params: The page size and offset that were asked for.
        request: The request, used to build the next page's link.

    Returns:
        The page with its total, limits and next link.
    """
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

"""OpenAPI documentation shared by the routers: tag descriptions, error and file responses.

Every route documents its errors with the ``ErrorDetail`` schema (the ``{"detail": ...}`` body that
FastAPI's ``HTTPException`` produces), so clients and generated SDKs see one error shape.
"""

from typing import Any

from fastapi.routing import APIRoute
from pydantic import BaseModel, Field

Responses = dict[int | str, dict[str, Any]]

DESCRIPTION = """
Turns web pages into podcast episodes: a scripted conversation between two AI hosts, grounded in
the pages' content, with every factual claim tied to the passage it comes from.

A **show** holds a topic, a speaking style and the pages to draw on. Each **episode** of a show is
generated in the background. The pages are fetched and split into sections, the passages that fit
the topic are selected, and a script is written in which each claim cites its passage. The script is
fact-checked and rewritten if a claim is not supported, then voiced, mixed into a single audio file
and published with show notes and an RSS feed.

A new episode of an existing show is a refresh: only the segments whose source sections changed
are regenerated, and nothing is regenerated if no source changed. Every episode is labelled as
AI-generated in its audio, show notes and feed.
"""

TAGS: list[dict[str, Any]] = [
    {"name": "shows", "description": "A show: its topic, style, hosts and source pages."},
    {
        "name": "episodes",
        "description": (
            "Start an episode, follow its progress through the pipeline, and fetch what it "
            "produced: audio, show notes, the script with citations, and per-stage run records."
        ),
    },
    {"name": "feeds", "description": "Each show's RSS feed, for podcast apps."},
    {"name": "ops", "description": "Liveness for load balancers and container health checks."},
]


class ErrorDetail(BaseModel):
    """The body of every error response."""

    detail: str = Field(description="What went wrong", examples=["episode 3fa8... not found"])


def errors(**descriptions: str) -> Responses:
    """Error responses by status code, with the ``ErrorDetail`` schema: ``errors(e404="...")``."""
    return {
        int(code.removeprefix("e")): {"model": ErrorDetail, "description": text}
        for code, text in descriptions.items()
    }


def file_response(media_type: str, description: str, *, binary: bool) -> Responses:
    """A 200 response whose body is a file, documented with its media type and schema."""
    schema = {"type": "string", "format": "binary"} if binary else {"type": "string"}
    return {200: {"description": description, "content": {media_type: {"schema": schema}}}}


def operation_id(route: APIRoute) -> str:
    """Name operations after their route functions (``get_episode_audio``), not FastAPI's default
    ``get_audio_episodes__episode_id__audio_wav_get``, so generated clients read naturally."""
    return route.name

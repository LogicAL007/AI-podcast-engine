"""Routes for episodes: paths, status codes and OpenAPI metadata only."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Request, status
from fastapi.responses import StreamingResponse

from podcast_engine.api.controllers.episodes_controller import (
    EVENT_STREAM,
    EpisodeController,
    follow_progress,
)
from podcast_engine.api.dependencies import (
    CurrentUserDep,
    SessionDep,
    get_episode_controller,
    get_episode_loader,
    get_progress_pacing,
)
from podcast_engine.api.models.episodes_model import (
    ClaimDetail,
    EpisodeRead,
    EpisodeScript,
    ScriptEdit,
    StageRunRead,
)
from podcast_engine.api.models.pagination_model import Page
from podcast_engine.api.openapi import errors
from podcast_engine.api.pagination import Paging, to_page
from podcast_engine.api.services.episodes_service import EpisodeLoader, ProgressPacing
from podcast_engine.common.models import EpisodeStatus

router = APIRouter(tags=["episodes"])

Controller = Annotated[EpisodeController, Depends(get_episode_controller)]
ShowId = Annotated[UUID, Path(description="The show's id")]
EpisodeId = Annotated[UUID, Path(description="The episode's id")]
StatusFilter = Annotated[
    EpisodeStatus | None, Query(alias="status", description="Only episodes with this status")
]


@router.post(
    "/shows/{show_id}/episodes",
    response_model=EpisodeRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start an episode",
    response_description="The new episode, `queued`; poll it for progress",
    responses=errors(
        e404="Show not found", e503="Job queue unavailable; the episode is marked `failed`"
    ),
)
def start_episode(show_id: ShowId, me: CurrentUserDep, controller: Controller) -> EpisodeRead:
    """Create an episode and start generating it in the background. Returns at once, with the
    episode `queued`; its status shows progress.

    For a show that already has a published episode, this is a refresh: only segments whose
    sources changed are re-scripted and re-voiced, and if no source changed the episode ends as
    `unchanged`.
    """
    return controller.start(show_id, me.user_id)


@router.get(
    "/shows/{show_id}/episodes",
    response_model=Page[EpisodeRead],
    summary="List a show's episodes",
    response_description="A page of episodes, newest first",
    responses=errors(e404="Show not found"),
)
def list_episodes(
    show_id: ShowId,
    me: CurrentUserDep,
    controller: Controller,
    paging: Paging,
    request: Request,
    status_filter: StatusFilter = None,
) -> Page[EpisodeRead]:
    """A page of the show's episodes, newest first, each with its status and links."""
    result = controller.list_for_show(
        show_id, me.user_id, status=status_filter, limit=paging.limit, offset=paging.offset
    )
    return to_page(result, paging, request)


@router.get(
    "/episodes",
    response_model=Page[EpisodeRead],
    summary="List episodes across shows",
    response_description="A page of episodes, newest first",
)
def list_all_episodes(
    me: CurrentUserDep,
    controller: Controller,
    paging: Paging,
    request: Request,
    status_filter: StatusFilter = None,
    show_id: Annotated[UUID | None, Query(description="Only episodes of this show")] = None,
) -> Page[EpisodeRead]:
    """Episodes of every show, newest first. With `status=needs_review` this is the review
    queue: episodes the fact-check held back, or paused for approval before voicing."""
    result = controller.list_all(
        me.user_id, status=status_filter, show_id=show_id, limit=paging.limit, offset=paging.offset
    )
    return to_page(result, paging, request)


@router.get(
    "/episodes/{episode_id}",
    response_model=EpisodeRead,
    summary="Get an episode",
    response_description="The episode, its progress, and links to what it produced",
    responses=errors(e404="Episode not found"),
)
def get_episode(episode_id: EpisodeId, me: CurrentUserDep, controller: Controller) -> EpisodeRead:
    """The episode's status, current stage and any error, with links to its audio, show notes,
    script, stage runs and feed. The audio and notes links are null until they exist."""
    return controller.get(episode_id, me.user_id)


@router.get(
    "/episodes/{episode_id}/events",
    response_class=StreamingResponse,
    summary="Follow an episode's progress",
    response_description="A stream of server-sent events",
    responses={
        200: {
            "description": (
                "Server-sent events. `episode` carries the status, stage, step (of 8), error and "
                "rewrite count, sent whenever they change. `gone` means the episode was deleted. "
                "Comment lines keep the connection alive."
            ),
            "content": {EVENT_STREAM: {"schema": {"type": "string"}}},
        },
        **errors(e404="Episode not found"),
    },
)
async def follow_episode(
    episode_id: EpisodeId,
    me: CurrentUserDep,
    session: SessionDep,
    load: Annotated[EpisodeLoader, Depends(get_episode_loader)],
    pacing: Annotated[ProgressPacing, Depends(get_progress_pacing)],
) -> StreamingResponse:
    """Watch an episode being made, live: an event whenever its status or stage changes, until
    nothing is running (published, held for review, unchanged, cancelled or failed). Browsers
    connect with `EventSource`, which sends the sign-in cookie and reconnects by itself."""
    session.close()  # the stream can stay open for an hour; it must not hold this connection
    return await follow_progress(episode_id, me.user_id, load, pacing)


@router.get(
    "/episodes/{episode_id}/script",
    response_model=EpisodeScript,
    summary="Get an episode's script",
    response_description="Segments and lines, with each claim's citations and verdict",
    responses=errors(e404="Episode not found"),
)
def get_episode_script(
    episode_id: EpisodeId, me: CurrentUserDep, controller: Controller
) -> EpisodeScript:
    """The script by segment. Each factual claim lists the passages it cites and the
    fact-check verdict, so it can be reviewed before or after voicing. Empty until the
    script stage has run."""
    return controller.get_script(episode_id, me.user_id)


@router.patch(
    "/episodes/{episode_id}/script",
    response_model=EpisodeRead,
    summary="Edit an episode's script",
    response_description="The episode, queued for the fact-check again",
    responses=errors(
        e404="Episode not found",
        e409="The episode is not waiting for review",
        e422="An unknown segment, speaker or passage",
        e503="Job queue unavailable; the edit is saved and the episode stays in review",
    ),
)
def edit_episode_script(
    episode_id: EpisodeId, edit: ScriptEdit, me: CurrentUserDep, controller: Controller
) -> EpisodeRead:
    """Replace the lines of one or more segments of an episode that is waiting for review.

    A line with `chunk_ids` is a claim citing those passages (they must come from the show's
    sources); a line without is framing. The script is fact-checked again. If it passes it goes
    on to voicing (or waits for approval, if the show reviews before voicing); if it fails it
    comes back for review. An edited script is never rewritten automatically.
    """
    return controller.edit_script(episode_id, me.user_id, edit)


@router.post(
    "/episodes/{episode_id}/approve",
    response_model=EpisodeRead,
    summary="Approve an episode for voicing",
    response_description="The episode, queued for voicing",
    responses=errors(
        e404="Episode not found",
        e409="The episode is not waiting for review",
        e503="Job queue unavailable; the episode stays in review",
    ),
)
def approve_episode(
    episode_id: EpisodeId, me: CurrentUserDep, controller: Controller
) -> EpisodeRead:
    """Release an episode that is waiting for review to voicing, with its script as it is. This
    includes a script the fact-check held back for unsupported claims: the reviewer decides, and
    the verdicts stay on record."""
    return controller.approve(episode_id, me.user_id)


@router.post(
    "/episodes/{episode_id}/retry",
    response_model=EpisodeRead,
    summary="Retry a failed episode",
    response_description="The episode, queued at the stage it stopped at",
    responses=errors(
        e404="Episode not found",
        e409="The episode has not failed or been cancelled",
        e503="Job queue unavailable",
    ),
)
def retry_episode(episode_id: EpisodeId, me: CurrentUserDep, controller: Controller) -> EpisodeRead:
    """Run a failed or cancelled episode again from the stage where it stopped, keeping what the
    earlier stages produced."""
    return controller.retry(episode_id, me.user_id)


@router.post(
    "/episodes/{episode_id}/cancel",
    response_model=EpisodeRead,
    summary="Cancel an episode",
    response_description="The episode, `cancelled`",
    responses=errors(e404="Episode not found", e409="The episode has already finished"),
)
def cancel_episode(
    episode_id: EpisodeId, me: CurrentUserDep, controller: Controller
) -> EpisodeRead:
    """Stop an episode that is queued, being generated or waiting for review. A stage that is
    already running finishes, but no further stage runs. It can be resumed with a retry."""
    return controller.cancel(episode_id, me.user_id)


@router.delete(
    "/episodes/{episode_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an episode",
    response_description="Deleted",
    responses=errors(e404="Episode not found", e409="The episode is running; cancel it first"),
)
def delete_episode(episode_id: EpisodeId, me: CurrentUserDep, controller: Controller) -> None:
    """Delete an episode, its script, claims and run records, and its audio and show notes. If it
    was published, the show's feed is rewritten without it."""
    controller.delete(episode_id, me.user_id)


@router.get(
    "/episodes/{episode_id}/runs",
    response_model=Page[StageRunRead],
    summary="List an episode's stage runs",
    response_description="A page of stage runs, oldest first",
    responses=errors(e404="Episode not found"),
)
def list_episode_runs(
    episode_id: EpisodeId,
    me: CurrentUserDep,
    controller: Controller,
    paging: Paging,
    request: Request,
) -> Page[StageRunRead]:
    """How long each stage took and which model, prompt version and seed it used, so a run can be
    timed, costed and repeated. Rewrites and retries add runs."""
    result = controller.list_runs(episode_id, me.user_id, limit=paging.limit, offset=paging.offset)
    return to_page(result, paging, request)


@router.get(
    "/episodes/{episode_id}/claims",
    response_model=Page[ClaimDetail],
    summary="List an episode's claims",
    response_description="A page of claims, in script order",
    responses=errors(e404="Episode not found"),
)
def list_episode_claims(
    episode_id: EpisodeId,
    me: CurrentUserDep,
    controller: Controller,
    paging: Paging,
    request: Request,
    supported: Annotated[
        bool | None,
        Query(description="`false` for the claims the fact-check rejected, `true` for the rest"),
    ] = None,
    segment: Annotated[int | None, Query(ge=1, description="Only claims in this segment")] = None,
) -> Page[ClaimDetail]:
    """Every factual claim in the script with the passages it cites and the fact-check's verdict
    and reason: the material for auditing an episode's accuracy."""
    result = controller.list_claims(
        episode_id,
        me.user_id,
        supported=supported,
        segment=segment,
        limit=paging.limit,
        offset=paging.offset,
    )
    return to_page(result, paging, request)

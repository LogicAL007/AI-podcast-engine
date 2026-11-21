"""Business rules for episodes. No HTTP and no SQL in here."""

import asyncio
import json
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from podcast_engine.api.errors import (
    ConflictError,
    InvalidInputError,
    NotFoundError,
    PipelineUnavailableError,
)
from podcast_engine.api.models.episodes_model import (
    ClaimDetail,
    EpisodeRead,
    EpisodeScript,
    ScriptEdit,
    StageRunRead,
)
from podcast_engine.api.models.pagination_model import Paged
from podcast_engine.api.repositories.episodes_repository import EpisodeRepository
from podcast_engine.api.repositories.shows_repository import ShowRepository
from podcast_engine.common.context import HOST_NAMES
from podcast_engine.common.logging import get_logger
from podcast_engine.common.models import EpisodeStatus
from podcast_engine.common.queue import PIPELINE_ORDER, Stage
from podcast_engine.common.storage import ObjectStore

# Enqueues a pipeline stage for an episode.
EnqueueStage = Callable[[UUID, Stage], None]
# Asks the publish worker to rewrite a show's RSS feed (after a published episode is deleted).
RebuildFeed = Callable[[UUID], None]

log = get_logger("api.episodes")

EDITABLE = {EpisodeStatus.NEEDS_REVIEW}
CANCELLABLE = {EpisodeStatus.QUEUED, EpisodeStatus.PROCESSING, EpisodeStatus.NEEDS_REVIEW}
RETRYABLE = {EpisodeStatus.FAILED, EpisodeStatus.CANCELLED}
RUNNING = {EpisodeStatus.QUEUED, EpisodeStatus.PROCESSING}
REMIXABLE = {EpisodeStatus.PUBLISHED}


def _utc_now() -> datetime:
    return datetime.now(UTC)


class EpisodeService:
    def __init__(
        self,
        episodes: EpisodeRepository,
        shows: ShowRepository,
        enqueue: EnqueueStage,
        store: ObjectStore | None = None,
        rebuild_feed: RebuildFeed | None = None,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._episodes = episodes
        self._shows = shows
        self._enqueue = enqueue
        self._store = store
        self._rebuild_feed = rebuild_feed
        self._now = now

    # ---- creating and reading -------------------------------------------------------------
    def start(self, show_id: UUID, owner: UUID, *, rebuild: bool = False) -> EpisodeRead:
        """Create an episode for a show and hand it to the pipeline.

        The first episode builds everything. A later one is a refresh: only segments whose
        sources changed are regenerated, and if none changed the episode ends as ``unchanged``.
        With ``rebuild``, a refresh regenerates every segment, changed or not.

        The row is committed before the job is enqueued, so a worker can always read it. If the
        queue is unreachable the episode is marked failed rather than left queued forever.
        """
        if self._shows.get(show_id, owner) is None:
            raise NotFoundError("show", show_id)
        episode = self._episodes.add(show_id, rebuild=rebuild)
        self._dispatch(episode.episode_id, Stage.INGEST)
        return episode

    def get(self, episode_id: UUID, owner: UUID) -> EpisodeRead:
        """The owner's episode; another user's is reported as not found."""
        episode = self._episodes.get(episode_id, owner)
        if episode is None:
            raise NotFoundError("episode", episode_id)
        return episode

    def list_for_show(
        self,
        show_id: UUID,
        owner: UUID,
        *,
        status: EpisodeStatus | None,
        limit: int,
        offset: int,
    ) -> Paged[EpisodeRead]:
        if self._shows.get(show_id, owner) is None:
            raise NotFoundError("show", show_id)
        return self._episodes.list_page(
            owner, show_id=show_id, status=status, limit=limit, offset=offset
        )

    def list_all(
        self,
        owner: UUID,
        *,
        status: EpisodeStatus | None,
        show_id: UUID | None,
        limit: int,
        offset: int,
    ) -> Paged[EpisodeRead]:
        """The owner's episodes across their shows; ``status=needs_review`` is the review queue."""
        return self._episodes.list_page(
            owner, show_id=show_id, status=status, limit=limit, offset=offset
        )

    def get_script(self, episode_id: UUID, owner: UUID) -> EpisodeScript:
        self.get(episode_id, owner)
        script = self._episodes.get_script(episode_id)
        if script is None:
            raise NotFoundError("episode", episode_id)
        return script

    def list_runs(
        self, episode_id: UUID, owner: UUID, *, limit: int, offset: int
    ) -> Paged[StageRunRead]:
        self.get(episode_id, owner)
        return self._episodes.list_runs(episode_id, limit=limit, offset=offset)

    def list_claims(
        self,
        episode_id: UUID,
        owner: UUID,
        *,
        supported: bool | None,
        segment: int | None,
        limit: int,
        offset: int,
    ) -> Paged[ClaimDetail]:
        self.get(episode_id, owner)
        return self._episodes.list_claims(
            episode_id, supported=supported, segment=segment, limit=limit, offset=offset
        )

    def get_audio(self, episode_id: UUID) -> bytes:
        """Public (podcast apps fetch it), so not scoped to an owner: the id is the secret."""
        files = self._episodes.get_files(episode_id)
        if files is None:
            raise NotFoundError("episode", episode_id)
        return self._read(files.audio_key, "audio for episode", episode_id)

    def get_notes(self, episode_id: UUID) -> str:
        """Public, like the audio."""
        files = self._episodes.get_files(episode_id)
        if files is None:
            raise NotFoundError("episode", episode_id)
        return self._read(files.notes_key, "show notes for episode", episode_id).decode("utf-8")

    # ---- review -----------------------------------------------------------------------------
    def edit_script(self, episode_id: UUID, owner: UUID, edit: ScriptEdit) -> EpisodeRead:
        """Replace segments' lines, then fact-check the script again.

        Only an episode waiting for review can be edited. Edited claims get new ids and are
        judged afresh. An edited script is never rewritten automatically: if it still fails the
        fact-check, it comes back for review instead of being regenerated over the edit.
        """
        episode = self._require(episode_id, owner, EDITABLE, "edited")
        show = self._shows.get(episode.show_id, owner)
        if show is None:
            raise NotFoundError("show", episode.show_id)
        positions = set(self._episodes.segment_positions(episode_id))
        hosts = set(HOST_NAMES[: show.host_count])
        problems: list[str] = []
        cited: set[UUID] = set()
        for segment in edit.segments:
            if segment.position not in positions:
                problems.append(f"segment {segment.position} does not exist")
            for line in segment.lines:
                if line.speaker not in hosts:
                    problems.append(f"speaker {line.speaker!r} is not a host ({sorted(hosts)})")
                cited.update(line.chunk_ids or [])
        unknown = cited - self._episodes.chunks_in_show(episode.show_id, cited)
        problems += [
            f"passage {chunk} is not one of this show's sources" for chunk in sorted(unknown)
        ]
        if problems:
            raise InvalidInputError("; ".join(dict.fromkeys(problems)))

        from podcast_engine.stages.script.service import claim_id_for

        script: dict[str, Any] = dict(self._episodes.get_raw_script(episode_id) or {})
        segments = dict(script.get("segments", {}))
        for segment in edit.segments:
            segments[str(segment.position)] = [
                {
                    "speaker": line.speaker,
                    "text": line.text,
                    "delivery": line.delivery.value,
                    "claims": []
                    if line.chunk_ids is None
                    else [
                        {
                            "claim_id": str(claim_id_for(episode_id, segment.position, line.text)),
                            "text": line.text,
                            "chunk_ids": [str(chunk) for chunk in line.chunk_ids],
                        }
                    ],
                }
                for line in segment.lines
            ]
        script["segments"] = dict(sorted(segments.items(), key=lambda kv: int(kv[0])))
        edited = sorted({*script.get("edited_segments", []), *(s.position for s in edit.segments)})
        script["edited_segments"] = edited
        self._episodes.save_script(episode_id, script)
        self._episodes.update(
            episode_id, status=EpisodeStatus.QUEUED, stage=Stage.FACTCHECK.value, error=None,
            approved_at=None,
        )  # fmt: skip
        self._dispatch(episode_id, Stage.FACTCHECK, revert_to=EpisodeStatus.NEEDS_REVIEW)
        return self.get(episode_id, owner)

    def approve(self, episode_id: UUID, owner: UUID) -> EpisodeRead:
        """Release an episode waiting for review to voicing, as it is.

        This is a reviewer's decision, so it also releases a script the fact-check held back
        for unsupported claims; the verdicts stay on record in the script and claims.
        """
        self._require(episode_id, owner, EDITABLE, "approved")
        self._episodes.update(
            episode_id, status=EpisodeStatus.QUEUED, stage=Stage.VOICE.value, error=None,
            approved_at=self._now(),
        )  # fmt: skip
        self._dispatch(episode_id, Stage.VOICE, revert_to=EpisodeStatus.NEEDS_REVIEW)
        return self.get(episode_id, owner)

    def remix(self, episode_id: UUID, owner: UUID) -> EpisodeRead:
        """Assemble a published episode again from its voiced lines, with the show's current
        voice effects and music, and publish it again. Nothing is voiced again (no TTS quota);
        the published audio is replaced."""
        self._require(episode_id, owner, REMIXABLE, "remixed")
        files = self._episodes.get_files(episode_id)
        if files is None or not files.audio_key:
            raise ConflictError(f"episode {episode_id} has no audio to remix")
        self._episodes.update(
            episode_id, status=EpisodeStatus.QUEUED, stage=Stage.ASSEMBLE.value, error=None
        )
        self._dispatch(episode_id, Stage.ASSEMBLE, revert_to=EpisodeStatus.PUBLISHED)
        return self.get(episode_id, owner)

    # ---- lifecycle --------------------------------------------------------------------------
    def retry(self, episode_id: UUID, owner: UUID) -> EpisodeRead:
        """Run a failed or cancelled episode again from the stage it stopped at."""
        episode = self._require(episode_id, owner, RETRYABLE, "retried")
        stage = Stage(episode.stage) if episode.stage else Stage.INGEST
        self._episodes.update(episode_id, status=EpisodeStatus.QUEUED, error=None)
        self._dispatch(episode_id, stage, revert_to=episode.status)
        return self.get(episode_id, owner)

    def cancel(self, episode_id: UUID, owner: UUID) -> EpisodeRead:
        """Stop an episode. A stage already running finishes, but nothing runs after it."""
        self._require(episode_id, owner, CANCELLABLE, "cancelled")
        self._episodes.update(
            episode_id, status=EpisodeStatus.CANCELLED, error="Cancelled on request."
        )
        return self.get(episode_id, owner)

    def delete(self, episode_id: UUID, owner: UUID) -> None:
        """Delete an episode with its audio and show notes. A running episode must be cancelled
        first. If it was published, the show's feed is rebuilt without it."""
        episode = self.get(episode_id, owner)
        if episode.status in RUNNING:
            raise ConflictError(
                f"episode {episode_id} is {episode.status.value}; cancel it before deleting"
            )
        files = self._episodes.get_files(episode_id)
        if self._store is not None and files is not None:
            for key in (files.audio_key, files.notes_key):
                if key:
                    self._store.delete(key)
        self._episodes.delete(episode_id)
        if episode.status is EpisodeStatus.PUBLISHED and self._rebuild_feed is not None:
            try:
                self._rebuild_feed(episode.show_id)
            except Exception:  # the episode is gone either way; the next publish fixes the feed
                log.exception("feed_rebuild_enqueue_failed", show_id=str(episode.show_id))

    # ---- helpers ----------------------------------------------------------------------------
    def _require(
        self, episode_id: UUID, owner: UUID, allowed: set[EpisodeStatus], action: str
    ) -> EpisodeRead:
        episode = self.get(episode_id, owner)
        if episode.status not in allowed:
            states = ", ".join(sorted(s.value for s in allowed))
            raise ConflictError(
                f"episode {episode_id} is {episode.status.value}; only an episode that is "
                f"{states} can be {action}"
            )
        return episode

    def _dispatch(
        self, episode_id: UUID, stage: Stage, *, revert_to: EpisodeStatus = EpisodeStatus.FAILED
    ) -> None:
        """Enqueue a stage. If the queue is unreachable, put the episode back as it was (or
        mark a new one failed) rather than leave it queued forever."""
        try:
            self._enqueue(episode_id, stage)
        except Exception as error:
            log.exception("enqueue_failed", episode_id=str(episode_id), stage=stage.value)
            self._episodes.update(
                episode_id, status=revert_to, error="The job queue was unavailable."
            )
            raise PipelineUnavailableError(
                "The job queue is unavailable; try again later"
            ) from error

    def _read(self, key: str | None, what: str, episode_id: UUID) -> bytes:
        if key is None or self._store is None or not self._store.exists(key):
            raise NotFoundError(what, episode_id)
        return self._store.get(key)


# ---- live progress -------------------------------------------------------------------------
EpisodeLoader = Callable[[UUID, UUID], EpisodeRead | None]  # (episode, owner) -> episode or None


@dataclass(frozen=True)
class ProgressPacing:
    """How often the stream checks the episode, when it sends a keep-alive, and when it stops
    (the browser reconnects by itself). Injected, so tests run without waiting."""

    poll_s: float = 1.0
    heartbeat_s: float = 15.0
    max_s: float = 3600.0
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    clock: Callable[[], float] = time.monotonic


def progress_of(episode: EpisodeRead) -> dict[str, Any]:
    """What the web app shows while an episode is made: status, stage, and step N of 8."""
    stages = [stage.value for stage in PIPELINE_ORDER]
    if episode.status in {EpisodeStatus.PUBLISHED, EpisodeStatus.UNCHANGED}:
        step = len(stages)
    elif episode.stage in stages:
        step = stages.index(episode.stage) + 1
    else:
        step = 0
    return {
        "episode_id": str(episode.episode_id),
        "status": episode.status.value,
        "stage": episode.stage,
        "step": step,
        "steps": len(stages),
        "error": episode.error,
        "rewrite_count": episode.rewrite_count,
        "running": episode.status in RUNNING,
    }


async def stream_progress(
    load: Callable[[], Awaitable[EpisodeRead | None]], pacing: ProgressPacing
) -> AsyncIterator[str]:
    """Server-sent events: an ``episode`` event whenever the progress changes, a comment as a
    keep-alive, and the end of the stream once nothing is running (published, held for review,
    unchanged, cancelled or failed), or when the episode is deleted (a ``gone`` event)."""
    yield "retry: 3000\n\n"  # reconnect after 3 s if the connection drops
    started = last_sent = pacing.clock()
    last: dict[str, Any] | None = None
    while True:
        episode = await load()
        if episode is None:
            yield "event: gone\ndata: {}\n\n"
            return
        progress = progress_of(episode)
        if progress != last:
            yield f"event: episode\ndata: {json.dumps(progress)}\n\n"
            last, last_sent = progress, pacing.clock()
        if not progress["running"]:
            return
        if pacing.clock() - started >= pacing.max_s:
            return
        if pacing.clock() - last_sent >= pacing.heartbeat_s:
            yield ": keep-alive\n\n"
            last_sent = pacing.clock()
        await pacing.sleep(pacing.poll_s)

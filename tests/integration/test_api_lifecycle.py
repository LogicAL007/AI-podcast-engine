"""Review, lifecycle and new sources, end to end: the API's services and Postgres repositories
drive the real pipeline, which runs in this process whenever the API enqueues a stage.

Needs a pgvector database (DATABASE_URL); skipped when it is unreachable, like test_pipeline.
"""

from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import pymupdf
import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from podcast_engine.api.errors import ConflictError
from podcast_engine.api.models.episodes_model import LineEdit, ScriptEdit, SegmentEdit
from podcast_engine.api.repositories.episodes_repository import PostgresEpisodeRepository
from podcast_engine.api.repositories.shows_repository import PostgresShowRepository
from podcast_engine.api.repositories.sources_repository import PostgresSourceRepository
from podcast_engine.api.repositories.uploads_repository import PostgresUploadRepository
from podcast_engine.api.services.episodes_service import EpisodeService
from podcast_engine.api.services.uploads_service import UploadService
from podcast_engine.common.context import PipelineContext
from podcast_engine.common.models import EpisodeStatus
from podcast_engine.common.queue import Stage
from podcast_engine.common.storage import feed_key
from podcast_engine.pipeline import run_inline
from podcast_engine.stages.publish.service import rebuild_feed
from tests.integration.test_pipeline import PAGE, PAGE_URL, MemoryStore, make_context
from tests.integration.test_pipeline import engine as engine  # the shared fixture

pytestmark = pytest.mark.integration

BODY = (
    "Tidewater stores every column of a table in its own file on disk. "
    "Queries read only the columns they need, which keeps scans fast. "
    "Similar values sit next to each other and compress well."
)


OWNER: UUID | None = None  # the account owning this module's shows; set per test


@pytest.fixture(autouse=True)
def owner(engine: Engine) -> Iterator[UUID]:
    """A throwaway account that owns every show a test creates (deleted with them after)."""
    global OWNER
    with engine.begin() as connection:
        OWNER = connection.execute(
            text(
                "INSERT INTO users (email, password_hash) VALUES (:email, 'not-a-real-hash')"
                " RETURNING user_id"
            ),
            {"email": f"owner-{uuid4()}@example.invalid"},
        ).scalar_one()
    yield OWNER
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM users WHERE user_id = :id"), {"id": OWNER})


class Api:
    """The API's episode service over real repositories; enqueued stages run straight away."""

    def __init__(self, engine: Engine, ctx: PipelineContext) -> None:
        self.session = Session(engine)
        self.ctx = ctx
        assert OWNER is not None
        self.owner: UUID = OWNER
        self.routes: list[list[str]] = []
        self.episodes = EpisodeService(
            PostgresEpisodeRepository(self.session),
            PostgresShowRepository(self.session),
            self._run,
            ctx.store,
            self._rebuild_feed,
        )

    def _rebuild_feed(self, show_id: UUID) -> None:
        rebuild_feed(show_id, self.ctx)

    def _run(self, episode_id: UUID, stage: Stage) -> None:
        """Like a worker: a stage that raises fails the episode, never the API call."""
        self.session.commit()  # the pipeline reads with its own connection
        try:
            self.routes.append(run_inline(episode_id, self.ctx, start=stage))
        except Exception as error:  # run_stage has already marked the episode failed
            self.routes.append([f"raised {type(error).__name__}"])

    def episode(self, episode_id: UUID) -> Any:
        self.session.expire_all()
        return self.ctx.repo.get_episode(episode_id)


def _show(engine: Engine, *, sources: list[str], review: bool = False) -> UUID:
    with engine.begin() as connection:
        show_id: UUID = connection.execute(
            text(
                "INSERT INTO shows (topic, tone, target_minutes, host_count, sources,"
                " topic_keywords, max_segments, review_before_voice, owner_id) VALUES"
                " ('What Tidewater is and why it is fast', 'casual', 3, 2,"
                " CAST(:sources AS jsonb), 'Tidewater storage engine columns tables', 6, :review,"
                " :owner)"
                " RETURNING show_id"
            ),
            {"sources": str(sources).replace("'", '"'), "review": review, "owner": OWNER},
        ).scalar_one()
    return show_id


@pytest.fixture
def cleanup(engine: Engine) -> Iterator[list[UUID]]:
    shows: list[UUID] = []
    yield shows
    with engine.begin() as connection:
        for show_id in shows:
            connection.execute(text("DELETE FROM shows WHERE show_id = :id"), {"id": show_id})


def test_review_before_voice_pauses_then_an_edit_and_approval_publish(
    engine: Engine, cleanup: list[UUID]
) -> None:
    show_id = _show(engine, sources=[PAGE_URL], review=True)
    cleanup.append(show_id)
    api = Api(engine, make_context(engine, MemoryStore()))

    started = api.episodes.start(show_id, api.owner)
    episode = api.episode(started.episode_id)
    assert api.routes[-1][-1] == "factcheck"  # stopped before voicing
    assert episode.status is EpisodeStatus.NEEDS_REVIEW
    assert "waiting for approval" in (episode.error or "")
    assert episode.audio_key is None

    script = api.episodes.get_script(started.episode_id, api.owner)
    first = script.segments[0]
    cited = next(claim for line in first.lines for claim in line.claims if claim.chunk_ids)
    edit = ScriptEdit(
        segments=[
            SegmentEdit(
                position=first.position,
                lines=[
                    LineEdit(speaker="Alex", text="Here is what a reviewer wrote."),
                    LineEdit(speaker="Sam", text=cited.text, chunk_ids=cited.chunk_ids),
                ],
            )
        ]
    )
    api.episodes.edit_script(started.episode_id, api.owner, edit)
    assert api.routes[-1] == ["factcheck"]  # re-checked, then paused again for approval
    assert api.episode(started.episode_id).status is EpisodeStatus.NEEDS_REVIEW

    api.episodes.approve(started.episode_id, api.owner)
    episode = api.episode(started.episode_id)
    assert api.routes[-1] == ["voice", "assemble", "publish"]
    assert episode.status is EpisodeStatus.PUBLISHED, episode.error
    assert episode.approved_at is not None
    notes = api.ctx.store.get(episode.notes_key or "").decode()
    assert cited.text in notes
    lines = [line["text"] for line in episode.voice_lines or []]
    assert "Here is what a reviewer wrote." in lines


def test_an_edited_claim_that_fails_comes_back_for_review_not_a_rewrite(
    engine: Engine, cleanup: list[UUID]
) -> None:
    show_id = _show(engine, sources=[PAGE_URL], review=True)
    cleanup.append(show_id)
    api = Api(engine, make_context(engine, MemoryStore()))
    episode_id = api.episodes.start(show_id, api.owner).episode_id

    uncited = LineEdit(speaker="Alex", text="Tidewater was invented in 1952.", chunk_ids=[])
    api.episodes.edit_script(
        episode_id, api.owner, ScriptEdit(segments=[SegmentEdit(position=1, lines=[uncited])])
    )

    assert api.routes[-1] == ["factcheck"]  # no trip back through the script stage
    episode = api.episode(episode_id)
    assert episode.status is EpisodeStatus.NEEDS_REVIEW
    assert "reviewer's edit" in (episode.error or "")
    unsupported = api.episodes.list_claims(
        episode_id, api.owner, supported=False, segment=None, limit=10, offset=0
    )
    assert [c.text for c in unsupported.items] == ["Tidewater was invented in 1952."]


def test_cancel_stops_the_pipeline_and_retry_resumes_it(
    engine: Engine, cleanup: list[UUID]
) -> None:
    show_id = _show(engine, sources=[PAGE_URL])
    cleanup.append(show_id)
    store = MemoryStore()
    failing = make_context(engine, store)

    def unreachable(_url: str) -> str:
        raise ConnectionError("the page is unreachable")

    failing.fetch = unreachable
    api = Api(engine, failing)
    episode_id = api.episodes.start(show_id, api.owner).episode_id
    assert api.routes[-1] == ["raised ConnectionError"]
    failed = api.episode(episode_id)
    assert failed.status is EpisodeStatus.FAILED
    assert failed.stage == "ingest"
    assert "unreachable" in (failed.error or "")

    api.ctx = make_context(engine, store)  # the page is back
    api.episodes.retry(episode_id, api.owner)
    assert api.episode(episode_id).status is EpisodeStatus.PUBLISHED

    later = PostgresEpisodeRepository(api.session).add(show_id)
    api.episodes.cancel(later.episode_id, api.owner)
    assert run_inline(later.episode_id, api.ctx) == ["ingest"]  # nothing ran
    assert api.episode(later.episode_id).status is EpisodeStatus.CANCELLED
    assert api.ctx.repo.list_stage_runs(later.episode_id) == []


def test_deleting_the_published_episode_removes_its_files_and_the_feed(
    engine: Engine, cleanup: list[UUID]
) -> None:
    show_id = _show(engine, sources=[PAGE_URL])
    cleanup.append(show_id)
    store = MemoryStore()
    api = Api(engine, make_context(engine, store))
    episode_id = api.episodes.start(show_id, api.owner).episode_id
    episode = api.episode(episode_id)
    assert store.exists(feed_key(show_id))
    PostgresEpisodeRepository(api.session).update(episode_id, status=EpisodeStatus.PROCESSING)
    with pytest.raises(ConflictError):  # a running episode cannot be deleted
        api.episodes.delete(episode_id, api.owner)
    PostgresEpisodeRepository(api.session).update(episode_id, status=EpisodeStatus.PUBLISHED)

    api.episodes.delete(episode_id, api.owner)
    assert not store.exists(episode.audio_key or "")
    assert not store.exists(episode.notes_key or "")
    assert not store.exists(feed_key(show_id))  # nothing published any more


def _pdf() -> bytes:
    document = pymupdf.open()
    for heading in ("Storage engine", "Replication"):
        page = document.new_page()
        page.insert_textbox(pymupdf.Rect(72, 72, 520, 120), heading, fontsize=20)
        page.insert_textbox(pymupdf.Rect(72, 130, 520, 400), BODY, fontsize=11)
    data: bytes = document.tobytes()
    document.close()
    return data


def test_an_uploaded_pdf_is_ingested_and_cited(engine: Engine, cleanup: list[UUID]) -> None:
    show_id = _show(engine, sources=[])
    cleanup.append(show_id)
    store = MemoryStore()
    ctx = make_context(engine, store)
    api = Api(engine, ctx)
    uploads = UploadService(
        PostgresUploadRepository(api.session), PostgresShowRepository(api.session), store,
        max_bytes=1_000_000,
    )  # fmt: skip
    upload = uploads.add(show_id, api.owner, filename="tidewater.pdf", data=_pdf())

    episode = api.episode(api.episodes.start(show_id, api.owner).episode_id)
    assert episode.status is EpisodeStatus.PUBLISHED, episode.error
    sources = PostgresSourceRepository(api.session).list_page(show_id, limit=10, offset=0)
    assert [s.title for s in sources.items] == ["Storage engine", "Replication"]
    assert all(f"/uploads/{upload.upload_id}/file#page=" in s.url for s in sources.items)
    notes = store.get(episode.notes_key or "").decode()
    assert f"/uploads/{upload.upload_id}/file#page=1" in notes


def test_an_rss_feed_source_reads_summaries_and_linked_pages(
    engine: Engine, cleanup: list[UUID]
) -> None:
    feed_url = "https://blog.tidewater.test/rss.xml"
    show_id = _show(engine, sources=[feed_url])
    cleanup.append(show_id)
    rss = f"""<?xml version="1.0"?><rss version="2.0"><channel><title>Tidewater blog</title>
    <item><title>Why columns</title><link>https://blog.tidewater.test/columns</link>
    <description><![CDATA[<p>{BODY} {BODY}</p><p>{BODY}</p>]]></description></item>
    <item><title>Teaser</title><link>{PAGE_URL}</link><description>Read more.</description></item>
    </channel></rss>"""
    ctx = make_context(engine, MemoryStore())
    ctx.fetch = lambda url: rss if url == feed_url else PAGE
    api = Api(engine, ctx)

    episode = api.episode(api.episodes.start(show_id, api.owner).episode_id)
    assert episode.status is EpisodeStatus.PUBLISHED, episode.error
    titles = [
        s.title
        for s in PostgresSourceRepository(api.session).list_page(show_id, limit=50, offset=0).items
    ]
    assert titles[0] == "Why columns"
    assert any(t.startswith("Teaser") for t in titles[1:])  # read from the linked page


def test_api_lists_page_and_filter_in_sql(engine: Engine, cleanup: list[UUID]) -> None:
    show_id = _show(engine, sources=[PAGE_URL])
    cleanup.append(show_id)
    api = Api(engine, make_context(engine, MemoryStore()))
    published = api.episodes.start(show_id, api.owner).episode_id
    repo = PostgresEpisodeRepository(api.session)
    repo.add(show_id)  # a second, queued episode

    every = api.episodes.list_for_show(show_id, api.owner, status=None, limit=1, offset=0)
    assert every.total == 2
    assert len(every.items) == 1
    only = api.episodes.list_for_show(
        show_id, api.owner, status=EpisodeStatus.PUBLISHED, limit=10, offset=0
    )
    assert [e.episode_id for e in only.items] == [published]
    runs = api.episodes.list_runs(published, api.owner, limit=3, offset=0)
    assert (runs.total, len(runs.items)) == (8, 3)
    claims = api.episodes.list_claims(
        published, api.owner, supported=True, segment=1, limit=50, offset=0
    )
    assert claims.total > 0
    assert all(c.segment == 1 and c.supported for c in claims.items)

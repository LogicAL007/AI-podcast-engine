"""Runs all eight stages in-process against a real Postgres (pgvector), as the workers would.

Offline settings (hashing embedder, extractive writer, word-overlap judge, placeholder voices), an
in-memory object store and a bundled page, so it needs no network, key or GPU. Needs a database
with db/init applied; the migrations are applied here. Skipped when Postgres is unreachable:

    DATABASE_URL=postgresql+psycopg://... pytest -m integration tests/integration/test_pipeline.py
"""

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import feedparser
import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import OperationalError

from podcast_engine.common.audio import read_wav_bytes
from podcast_engine.common.config import Settings
from podcast_engine.common.context import PipelineContext
from podcast_engine.common.llm import LlmClient
from podcast_engine.common.migrate import apply_migrations
from podcast_engine.common.models import EpisodeStatus
from podcast_engine.common.queue import Stage
from podcast_engine.common.quota import DailyBudget, MemoryCounter
from podcast_engine.common.repository import PipelineRepository
from podcast_engine.common.storage import feed_key
from podcast_engine.pipeline import run_inline
from podcast_engine.stages.publish.service import AI_DISCLOSURE

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
PAGE_URL = "https://docs.tidewater.test/intro"
PAGE = (ROOT / "tests" / "fixtures" / "pages" / "intro.html").read_text(encoding="utf-8")


class MemoryStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = data

    def get(self, key: str) -> bytes:
        return self.objects[key]

    def exists(self, key: str) -> bool:
        return key in self.objects

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        pytest.skip("DATABASE_URL is not set")
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1 FROM shows LIMIT 1"))
    except OperationalError:
        pytest.skip("Postgres not reachable")
    apply_migrations(engine, ROOT / "db" / "migrations")
    yield engine
    engine.dispose()


@pytest.fixture
def show_id(engine: Engine) -> Iterator[UUID]:
    with engine.begin() as connection:
        created: UUID = connection.execute(
            text(
                "INSERT INTO shows (topic, tone, target_minutes, host_count, sources, "
                "topic_keywords, attribution, max_segments) VALUES (:topic, 'casual', 3, 2, "
                "CAST(:sources AS jsonb), :keywords, :attribution, 6) RETURNING show_id"
            ),
            {
                "topic": "What Tidewater is and why it is fast",
                "sources": f'["{PAGE_URL}"]',
                "keywords": "Tidewater storage engine columns tables scan queries",
                "attribution": "Source material: the Tidewater test page.",
            },
        ).scalar_one()
    yield created
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM shows WHERE show_id = :id"), {"id": created})


def make_context(
    engine: Engine, store: MemoryStore, page: str = PAGE, **overrides: Any
) -> PipelineContext:
    settings = Settings(
        _env_file=None,
        **{
            "database_url": str(engine.url),
            "llm_enabled": False,
            "tts_backend": "placeholder",
            "embedding_model": "hashing",
            "config_dir": ROOT / "config",
            "prompts_dir": ROOT / "prompts",
            "assets_dir": ROOT / "assets",
            **overrides,
        },
    )
    return PipelineContext(
        settings=settings, repo=PipelineRepository(engine), store=store, fetch=lambda _url: page
    )


def new_episode(ctx: PipelineContext, show_id: UUID) -> UUID:
    return ctx.repo.create_episode(show_id)


def test_first_episode_runs_every_stage_and_publishes(engine: Engine, show_id: UUID) -> None:
    store = MemoryStore()
    ctx = make_context(engine, store)
    episode_id = new_episode(ctx, show_id)

    route = run_inline(episode_id, ctx)

    assert route == [stage.value for stage in Stage]
    episode = ctx.repo.get_episode(episode_id)
    assert episode.status is EpisodeStatus.PUBLISHED, episode.error
    assert episode.revision == 1
    segments = ctx.repo.list_segments(episode_id)
    assert segments
    assert all(s.chunk_ids and not s.needs_script for s in segments)
    assert [s.position for s in segments] == list(range(1, len(segments) + 1))

    claims = ctx.repo.list_claims(episode_id)
    assert claims
    assert all(c.supported for c in claims)
    assert episode.fact_check is not None
    assert episode.fact_check["history"][-1]["support_rate"] == 1.0

    assert episode.assembly is not None
    assert episode.assembly["checks_pass"], episode.assembly
    audio = read_wav_bytes(store.get(episode.audio_key or ""))
    assert len(audio) / 24_000 == pytest.approx(episode.assembly["after"]["duration_s"])

    notes = store.get(episode.notes_key or "").decode()
    assert notes.startswith(AI_DISCLOSURE)
    assert "## Sources" in notes
    assert PAGE_URL in notes
    feed = feedparser.parse(store.get(feed_key(show_id)))
    assert len(feed.entries) == 1
    assert "AI-generated" in feed.entries[0].title
    assert feed.entries[0].enclosures[0].href.endswith(f"/api/v1/episodes/{episode_id}/audio.wav")

    runs = ctx.repo.list_stage_runs(episode_id)
    assert [r.stage for r in runs] == [stage.value for stage in Stage]
    assert episode.manifest is not None
    assert episode.manifest["script_backend"] == "offline-extractive"
    assert set(episode.manifest["voices"]) == {"Alex", "Sam"}


def test_refresh_with_unchanged_sources_stops_after_ingest(engine: Engine, show_id: UUID) -> None:
    ctx = make_context(engine, MemoryStore())
    run_inline(new_episode(ctx, show_id), ctx)

    second = new_episode(ctx, show_id)
    route = run_inline(second, ctx)

    assert route == ["ingest"]
    assert ctx.repo.get_episode(second).status is EpisodeStatus.UNCHANGED


def test_refresh_regenerates_only_the_changed_segment(engine: Engine, show_id: UUID) -> None:
    store = MemoryStore()
    ctx = make_context(engine, store)
    first = new_episode(ctx, show_id)
    run_inline(first, ctx)
    before = ctx.repo.get_episode(first)
    voiced = len(store.objects)

    edited = PAGE.replace(
        "Teams use it to scan very large tables", "Teams use it to scan huge tables"
    )
    assert edited != PAGE
    ctx = make_context(engine, store, page=edited)
    second = new_episode(ctx, show_id)
    run_inline(second, ctx)

    after = ctx.repo.get_episode(second)
    assert after.status is EpisodeStatus.PUBLISHED, after.error
    assert after.revision == 2
    assert after.changed_item_ids is not None
    assert len(after.changed_item_ids) == 1
    changed = {
        s.position
        for s in ctx.repo.list_segments(second)
        if set(s.source_item_ids) & set(after.changed_item_ids)
    }
    assert len(changed) == 1
    old_text = {
        p: [ln["text"] for ln in lines] for p, lines in (before.script or {})["segments"].items()
    }
    new_text = {
        p: [ln["text"] for ln in lines] for p, lines in (after.script or {})["segments"].items()
    }
    for position, lines in new_text.items():
        if int(position) not in changed:
            assert lines == old_text[position], f"segment {position} should be reused unchanged"
    assert new_text[str(next(iter(changed)))] != old_text[str(next(iter(changed)))]
    # Unchanged lines come from the voice cache: only the edited line and the new files are added.
    assert len(store.objects) - voiced <= 5
    feed = feedparser.parse(store.get(feed_key(show_id)))
    assert len(feed.entries) == 2


def _plant_uncited_claim(ctx: PipelineContext, episode_id: UUID) -> None:
    episode = ctx.repo.get_episode(episode_id)
    script = dict(episode.script or {})
    planted = {
        "speaker": "Alex",
        "text": "Tidewater was invented in 1952 by a team of librarians in Vienna.",
        "claims": [
            {"claim_id": str(uuid4()), "text": "Tidewater was invented in 1952.", "chunk_ids": []}
        ],
    }
    script["segments"]["1"] = [*script["segments"]["1"], planted]
    ctx.repo.update_episode(episode_id, script=script)


def test_gate_sends_an_unsupported_claim_back_for_a_rewrite(engine: Engine, show_id: UUID) -> None:
    ctx = make_context(engine, MemoryStore())
    episode_id = new_episode(ctx, show_id)
    run_inline(episode_id, ctx, start=Stage.INGEST, stop_after=Stage.SCRIPT)
    _plant_uncited_claim(ctx, episode_id)

    route = run_inline(episode_id, ctx, start=Stage.FACTCHECK)

    assert route[:3] == ["factcheck", "script", "factcheck"]
    episode = ctx.repo.get_episode(episode_id)
    assert episode.status is EpisodeStatus.PUBLISHED, episode.error
    assert episode.rewrite_count == 1
    history = (episode.fact_check or {})["history"]
    assert history[0]["unsupported"] == 1
    assert history[-1]["unsupported"] == 0


def test_gate_holds_for_review_when_rewrites_are_spent(engine: Engine, show_id: UUID) -> None:
    ctx = make_context(engine, MemoryStore(), max_rewrites=0)
    episode_id = new_episode(ctx, show_id)
    run_inline(episode_id, ctx, stop_after=Stage.SCRIPT)
    _plant_uncited_claim(ctx, episode_id)

    route = run_inline(episode_id, ctx, start=Stage.FACTCHECK)

    assert route == ["factcheck"]
    episode = ctx.repo.get_episode(episode_id)
    assert episode.status is EpisodeStatus.NEEDS_REVIEW
    assert episode.audio_key is None
    assert "unsupported" in (episode.error or "")


class SilentJudge(LlmClient):
    """A Gemini stand-in that returns no verdicts, so every claim counts as unsupported."""

    provider = "gemini"

    def parse(self, *, system: str, user: str, output_format: Any, max_tokens: int = 0) -> Any:
        return output_format.model_validate({"verdicts": []})


def test_an_episode_the_daily_budget_cannot_finish_does_not_start(
    engine: Engine, show_id: UUID
) -> None:
    budget = DailyBudget(MemoryCounter(), {"gemini-3.8-flash": 20})
    budget.spend("gemini-3.8-flash", 15)  # 5 left; outline + 6 segments + fact-check need 8
    ctx = make_context(engine, MemoryStore(), llm_enabled=True)
    ctx.llm_override = SilentJudge("gemini-3.8-flash", seed=1)
    ctx.budget_override = budget
    episode_id = new_episode(ctx, show_id)

    assert run_inline(episode_id, ctx) == ["ingest", "index", "retrieve_plan"]
    episode = ctx.repo.get_episode(episode_id)
    assert episode.status is EpisodeStatus.FAILED
    assert "cannot cover a whole episode" in (episode.error or "")
    assert "5 of today's 20 left" in (episode.error or "")
    assert budget.used("gemini-3.8-flash") == 15  # nothing was spent on a half episode


def test_a_rewrite_the_daily_budget_cannot_cover_is_held_for_review(
    engine: Engine, show_id: UUID
) -> None:
    store = MemoryStore()
    ctx = make_context(engine, store)
    episode_id = new_episode(ctx, show_id)
    run_inline(episode_id, ctx, stop_after=Stage.SCRIPT)
    budget = DailyBudget(MemoryCounter(), {"gemini-3.8-flash": 20})
    budget.spend("gemini-3.8-flash", 19)  # 1 left; a rewrite needs a segment and a re-check
    judged = make_context(engine, store, llm_enabled=True)
    judged.llm_override = SilentJudge("gemini-3.8-flash", seed=1)
    judged.budget_override = budget

    assert run_inline(episode_id, judged, start=Stage.FACTCHECK) == ["factcheck"]
    episode = ctx.repo.get_episode(episode_id)
    assert episode.status is EpisodeStatus.NEEDS_REVIEW
    assert episode.rewrite_count == 0
    assert "today's Gemini budget cannot cover another pass" in (episode.error or "")


def test_a_show_without_sources_fails_with_the_reason(engine: Engine, show_id: UUID) -> None:
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE shows SET sources = '[]' WHERE show_id = :id"), {"id": show_id}
        )
    ctx = make_context(engine, MemoryStore())
    episode_id = new_episode(ctx, show_id)

    assert run_inline(episode_id, ctx) == ["ingest"]
    episode = ctx.repo.get_episode(episode_id)
    assert episode.status is EpisodeStatus.FAILED
    assert episode.error is not None
    assert "no sources" in episode.error


def test_only_published_idle_shows_are_due_for_refresh(engine: Engine, show_id: UUID) -> None:
    ctx = make_context(engine, MemoryStore())
    assert show_id not in ctx.repo.shows_due_for_refresh(0.0)  # nothing published yet
    episode_id = new_episode(ctx, show_id)
    run_inline(episode_id, ctx)
    assert show_id not in ctx.repo.shows_due_for_refresh(1.0)  # started within the hour
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE episodes SET created_at = now() - interval '2 hours' WHERE show_id = :id"),
            {"id": show_id},
        )
    assert show_id in ctx.repo.shows_due_for_refresh(1.0)
    ctx.repo.create_episode(show_id)  # a queued episode blocks another refresh
    assert show_id not in ctx.repo.shows_due_for_refresh(1.0)

"""How episodes use the daily budget: reservations follow the stage runner, and the script keeps
every segment it has written when a later one fails."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest

from podcast_engine.common.models import EpisodeStatus
from podcast_engine.common.queue import Stage
from podcast_engine.common.quota import DailyBudget, MemoryCounter
from podcast_engine.common.runner import run_stage
from podcast_engine.stages.script.service import DraftLine, DraftSegment, write_script

TEXT = "gemini-3.8-flash"
PROMPTS = Path(__file__).resolve().parents[2] / "prompts"


def runner_ctx(budget: DailyBudget) -> Any:
    episode = SimpleNamespace(status=EpisodeStatus.PROCESSING, manifest={})
    repo = SimpleNamespace(
        get_episode=lambda _: episode,
        update_episode=lambda _, **fields: None,
        record_stage_run=lambda *_, **__: None,
    )
    settings = SimpleNamespace(seed=1, llm_enabled=False)
    return SimpleNamespace(repo=repo, settings=settings, budget=budget)


def test_a_stage_spends_from_its_episodes_reservation() -> None:
    budget = DailyBudget(MemoryCounter(), {TEXT: 18})
    episode_id = uuid4()
    budget.reserve(str(episode_id), {TEXT: 8}, "a whole episode")

    def script(episode_id: UUID, ctx: Any = None) -> Stage | None:
        ctx.budget.require({TEXT: 18}, "all of today")  # its own reservation is available to it
        ctx.budget.spend(TEXT, 3)
        return Stage.FACTCHECK

    assert run_stage(Stage.SCRIPT, script, episode_id, runner_ctx(budget)) is Stage.FACTCHECK
    assert budget.holdings(TEXT) == {str(episode_id): 5}  # still running: the rest is kept


@pytest.mark.parametrize("outcome", ["finished", "failed"])
def test_the_reservation_is_released_when_the_episode_stops(outcome: str) -> None:
    budget = DailyBudget(MemoryCounter(), {TEXT: 18})
    episode_id = uuid4()
    budget.reserve(str(episode_id), {TEXT: 8}, "a whole episode")

    def stage(episode_id: UUID, ctx: Any = None) -> Stage | None:
        if outcome == "failed":
            raise ValueError("no stored passages")
        return None  # published, unchanged or held for review

    assert run_stage(Stage.PUBLISH, stage, episode_id, runner_ctx(budget)) is None
    assert budget.holdings(TEXT) == {}


# ---- the script keeps each segment as it is written ----------------------------------------


class OverloadedError(Exception):
    pass


class ScriptRepo:
    def __init__(self, positions: list[int]) -> None:
        self.item = SimpleNamespace(item_id=uuid4(), title="Tides", text="The Moon pulls.")
        self.chunks = {
            p: SimpleNamespace(chunk_id=uuid4(), item_id=self.item.item_id, text=f"Fact {p}.")
            for p in positions
        }
        self.segments = {
            p: SimpleNamespace(
                position=p, title=f"Part {p}", chunk_ids=[self.chunks[p].chunk_id],
                needs_script=True,
            )
            for p in positions
        }  # fmt: skip
        self.episode = SimpleNamespace(show_id=uuid4(), script=None, rewrite_count=0)
        self.show = SimpleNamespace(
            show_id=self.episode.show_id, topic="Tides", target_minutes=6,
            tone=SimpleNamespace(value="neutral"), expertise=SimpleNamespace(value="beginner"),
            language="en", host_count=2,
        )  # fmt: skip

    def get_episode(self, _: UUID) -> Any:
        return self.episode

    def get_show(self, _: UUID) -> Any:
        return self.show

    def list_segments(self, _: UUID) -> list[Any]:
        return [self.segments[p] for p in sorted(self.segments)]

    def list_items(self, _: UUID) -> list[Any]:
        return [self.item]

    def get_chunks(self, ids: list[UUID]) -> dict[UUID, Any]:
        return {c.chunk_id: c for c in self.chunks.values() if c.chunk_id in ids}

    def update_episode(self, _: UUID, **fields: Any) -> None:
        if "script" in fields:
            self.episode.script = fields["script"]

    def update_segment(self, _: UUID, position: int, **fields: Any) -> None:
        for name, value in fields.items():
            setattr(self.segments[position], name, value)


class FlakyWriter:
    """Writes segments, but is overloaded from the ``fail_at``-th request on."""

    def __init__(self, fail_at: int | None) -> None:
        self.fail_at = fail_at
        self.calls = 0
        self.usage: dict[str, int] = {}

    def parse(self, *, system: str, user: str, output_format: type[Any], **_: Any) -> Any:
        self.calls += 1
        if self.fail_at is not None and self.calls >= self.fail_at:
            raise OverloadedError("503 UNAVAILABLE")
        return DraftSegment(
            lines=[DraftLine(speaker="Alex", text=f"Line {self.calls}.", is_claim=False)]
        )


def script_ctx(repo: ScriptRepo, writer: FlakyWriter) -> Any:
    settings = SimpleNamespace(prompts_dir=PROMPTS, llm_fallback_model="", seed=1)
    return SimpleNamespace(
        repo=repo, settings=settings, llm=writer, budget=None, hosts=lambda n: ["Alex", "Sam"]
    )


def test_a_failure_partway_keeps_the_segments_already_written() -> None:
    repo = ScriptRepo([1, 2, 3, 4])
    with pytest.raises(OverloadedError):
        write_script(uuid4(), script_ctx(repo, FlakyWriter(fail_at=3)))
    assert sorted(repo.episode.script["segments"]) == ["1", "2"]
    assert [s.needs_script for s in repo.list_segments(uuid4())] == [False, False, True, True]

    retry = FlakyWriter(fail_at=None)
    assert write_script(uuid4(), script_ctx(repo, retry)) is Stage.FACTCHECK
    assert retry.calls == 2  # only segments 3 and 4 are written again
    assert sorted(repo.episode.script["segments"]) == ["1", "2", "3", "4"]


def test_the_length_budget_leaves_room_for_the_opening_and_closing() -> None:
    from podcast_engine.stages.script.service import segment_words

    assert segment_words(2, 1) == 237  # (120 s - 25 s) at 150 words a minute
    assert segment_words(7, 3) == 329
    assert segment_words(1, 4) == 60  # never fewer than 60 words


def test_a_one_host_show_is_written_as_a_narration() -> None:
    from podcast_engine.common.context import PROMPT_VERSIONS, script_prompt
    from podcast_engine.stages.script.service import load_prompt

    assert script_prompt(2) == "script"
    assert script_prompt(1) == "script_narrator"
    narration = load_prompt(PROMPTS, "script_narrator", PROMPT_VERSIONS["script_narrator"])
    assert "single narrator" in narration
    assert "react to each other" not in narration

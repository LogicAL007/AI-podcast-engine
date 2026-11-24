import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from podcast_engine.common.context import PROMPT_VERSIONS, PipelineContext, get_context
from podcast_engine.common.logging import get_logger
from podcast_engine.common.models import ReliabilityTier
from podcast_engine.common.queue import Stage
from podcast_engine.common.quota import reserve_episode
from podcast_engine.common.repository import EpisodeRecord, RankedChunk, SegmentRecord, ShowRecord

log = get_logger("retrieve_plan")

HALF_LIFE_DAYS = 14
AUTHORITY = {
    ReliabilityTier.PRIMARY: 1.0,
    ReliabilityTier.ESTABLISHED: 0.6,
    ReliabilityTier.UNVERIFIED: 0.2,
}
RANKING_PROFILES = {
    "daily": {"recency_weight": 0.8, "authority_weight": 0.0},  # favours fresh items
    "explainer": {"recency_weight": 0.1, "authority_weight": 0.4},  # favours authoritative ones
}
OUTLINE_PASSAGES = 24  # how many top passages the LLM sees when planning


def recency_score(published_at: datetime | None, *, now: datetime, half_life_days: float) -> float:
    """Score how fresh an item is, by exponential decay.

    1.0 for a brand-new item, 0.5 after one half-life. Items with no publish date score 0, so they
    never outrank dated ones on recency alone.

    Args:
        published_at: When the item was published, or None.
        now: The current time.
        half_life_days: Days for the score to halve.

    Returns:
        The score, in [0, 1].

    Raises:
        ValueError: ``half_life_days`` is not positive.
    """
    if published_at is None:
        return 0.0
    if half_life_days <= 0:
        raise ValueError("half_life_days must be positive")
    age_days = max((now - published_at).total_seconds() / 86_400, 0.0)
    return math.pow(0.5, age_days / half_life_days)


def combined_score(relevance: float, recency: float, *, recency_weight: float) -> float:
    """Blend relevance and recency: a daily show uses a high weight, an explainer a low one.

    Args:
        relevance: How well the passage matches the topic.
        recency: How fresh it is.
        recency_weight: The share given to recency, in [0, 1].

    Returns:
        The blended score.

    Raises:
        ValueError: The weight is outside [0, 1].
    """
    if not 0.0 <= recency_weight <= 1.0:
        raise ValueError("recency_weight must be in [0, 1]")
    return (1 - recency_weight) * relevance + recency_weight * recency


def utc_now() -> datetime:
    """Return the current time in UTC.

    Returns:
        The current time, timezone-aware.
    """
    return datetime.now(UTC)


@dataclass(frozen=True)
class Ranked:
    """A passage with its recency, authority and final ranking score."""

    chunk: RankedChunk
    recency: float
    authority: float
    score: float


def rank(
    chunks: list[RankedChunk], *, profile: str, now: datetime, threshold: float
) -> list[Ranked]:
    """Rank passages for a show's topic.

    Passages below the topic threshold are dropped; the rest are ranked by relevance, recency and
    authority, weighted by the show's ranking profile.

    Args:
        chunks: The show's passages, with their relevance to the topic.
        profile: The show's ranking profile, such as ``explainer``.
        now: The current time.
        threshold: The lowest relevance kept; below it a passage is off-topic.

    Returns:
        The passages kept, best first.

    Raises:
        ValueError: The ranking profile is unknown.
    """
    if profile not in RANKING_PROFILES:
        raise ValueError(
            f"ranking profile must be one of {sorted(RANKING_PROFILES)}, not {profile!r}"
        )
    weights = RANKING_PROFILES[profile]
    pool = []
    for chunk in chunks:
        if chunk.relevance < threshold:
            continue
        recency = recency_score(chunk.published_at, now=now, half_life_days=HALF_LIFE_DAYS)
        authority = AUTHORITY[chunk.reliability]
        blended = combined_score(chunk.relevance, recency, recency_weight=weights["recency_weight"])
        score = (1 - weights["authority_weight"]) * blended + weights[
            "authority_weight"
        ] * authority
        pool.append(Ranked(chunk, recency, authority, score))
    return sorted(pool, key=lambda r: r.score, reverse=True)


class OutlineSegment(BaseModel):
    """One segment the outline model plans: its title and the passages it draws on."""

    title: str
    passage_ids: list[str]


class Outline(BaseModel):
    """What the outline model returns: the episode's segments."""

    segments: list[OutlineSegment]


def passages_per_segment(ctx: PipelineContext) -> int:
    """Return how many passages each segment's script gets.

    Args:
        ctx: The pipeline context.

    Returns:
        The configured number, else 3 offline and 6 with an LLM.
    """
    configured = ctx.settings.passages_per_segment
    return configured or (6 if ctx.settings.llm_enabled else 3)


def passages_for(pool: list[Ranked], item_ids: list[UUID], limit: int) -> list[UUID]:
    """Pick the best passages for one segment, drawn only from that segment's sources.

    Args:
        pool: The ranked passages.
        item_ids: The segment's source items.
        limit: Most passages to pick.

    Returns:
        The chosen passages' ids, best first.
    """
    wanted = set(item_ids)
    return [r.chunk.chunk_id for r in pool if r.chunk.item_id in wanted][:limit]


def plan_offline(pool: list[Ranked], max_segments: int) -> list[tuple[str, list[UUID]]]:
    """Plan one segment per source section, offline.

    The best-ranked sections are chosen and told in the page's order.

    Args:
        pool: The ranked passages.
        max_segments: Most segments to plan.

    Returns:
        Each segment's title and source items.
    """
    best: dict[UUID, Ranked] = {}
    for ranked in pool:
        best.setdefault(ranked.chunk.item_id, ranked)
    chosen = list(best.values())[:max_segments]
    chosen.sort(key=lambda r: r.chunk.item_position)
    return [(r.chunk.item_title, [r.chunk.item_id]) for r in chosen]


def plan_llm(
    pool: list[Ranked], show: ShowRecord, ctx: PipelineContext
) -> list[tuple[str, list[UUID]]]:
    """Ask the LLM to plan the episode's segments from the top passages.

    The model sees the top passages, labelled with their source and date, and names the passages
    each segment uses. The segments are then told in the page's order, whatever order the model
    chose.

    Args:
        pool: The ranked passages.
        show: The show: its topic and most segments.
        ctx: The pipeline context, with an LLM client.

    Returns:
        Each segment's title and source items.

    Raises:
        RuntimeError: There is no LLM client.
        ValueError: A segment cites no known passage.
    """
    from podcast_engine.stages.script.service import load_prompt

    if ctx.llm is None:
        raise RuntimeError("plan_llm needs an LLM client")
    labelled = {f"P{n + 1}": r for n, r in enumerate(pool[:OUTLINE_PASSAGES])}
    listing = "\n".join(
        f"[{pid}] ({r.chunk.item_title}"
        + (f", {r.chunk.published_at:%Y-%m-%d}" if r.chunk.published_at else "")
        + f") {r.chunk.text}"
        for pid, r in labelled.items()
    )
    outline = ctx.llm.parse(
        system=load_prompt(ctx.settings.prompts_dir, "outline", PROMPT_VERSIONS["outline"]),
        user=(
            f"Show topic: {show.topic}\nUse at most {show.max_segments} segments.\n\n"
            f"Passages:\n{listing}\n\nPlan the segments, following the rules above."
        ),
        output_format=Outline,
    )
    planned = []
    for segment in outline.segments[: show.max_segments]:
        items = list(
            dict.fromkeys(labelled[p].chunk.item_id for p in segment.passage_ids if p in labelled)
        )
        if not items:
            raise ValueError(
                f"segment {segment.title!r} cites no known passage: {segment.passage_ids}"
            )
        planned.append((segment.title, items))
    first_position = {r.chunk.item_id: r.chunk.item_position for r in pool}
    planned.sort(key=lambda seg: min(first_position[i] for i in seg[1]))
    return planned


def _previous_episode(ctx: PipelineContext, episode: EpisodeRecord) -> EpisodeRecord | None:
    """Return the show's latest published episode other than this one.

    Args:
        ctx: The pipeline context.
        episode: The episode being made.

    Returns:
        That episode, or None for a show's first episode.
    """
    earlier = [
        e for e in ctx.repo.list_published(episode.show_id) if e.episode_id != episode.episode_id
    ]
    return earlier[0] if earlier else None


def _carry_over(
    ctx: PipelineContext,
    episode: EpisodeRecord,
    previous: EpisodeRecord,
    pool: list[Ranked],
    limit: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Keep the previous episode's plan, re-scripting only segments whose sources changed (FR8).

    A segment whose every source is gone from the page is dropped. A segment is re-retrieved and
    re-scripted when a source changed or went away; the others keep their passages and their script.

    Args:
        ctx: The pipeline context.
        episode: The episode being made.
        previous: The episode it refreshes.
        pool: The ranked passages.
        limit: Most passages per re-retrieved segment.

    Returns:
        The segments, and the script carried over for the unchanged ones.
    """
    from podcast_engine.stages.script.service import with_episode_claim_ids

    changed = set(episode.changed_item_ids or [])
    existing = {r.chunk.item_id for r in pool}
    old_lines = (previous.script or {}).get("segments", {})
    segments: list[dict[str, Any]] = []
    carried: dict[str, Any] = {}
    old: SegmentRecord
    for old in ctx.repo.list_segments(previous.episode_id):
        items = [i for i in old.source_item_ids if i in existing]
        if not items:
            continue
        position = len(segments) + 1
        affected = bool(changed & set(old.source_item_ids)) or items != old.source_item_ids
        segments.append(
            {
                "position": position,
                "title": old.title,
                "source_item_ids": items,
                "chunk_ids": passages_for(pool, items, limit) if affected else old.chunk_ids,
                "needs_script": affected or str(old.position) not in old_lines,
            }
        )
        if not segments[-1]["needs_script"]:
            carried[str(position)] = with_episode_claim_ids(
                old_lines[str(old.position)], episode.episode_id, position
            )
    return segments, {"segments": carried, "avoid": {}}


def retrieve_and_plan(episode_id: UUID, ctx: PipelineContext | None = None) -> Stage | None:
    """Rank passages for the topic and build the outline, tagged with sources (stage 3, FR3).

    A refresh carries over the previous plan; otherwise the LLM, or the offline planner, plans
    afresh. Only an episode today's Gemini budget can finish is started, and its requests are set
    aside so the bot or another episode cannot spend them first.

    Args:
        episode_id: The episode being made.
        ctx: Shared clients; built from settings when omitted.

    Returns:
        The next stage, script.

    Raises:
        ValueError: No passage matched the topic.
        GeminiQuotaError: Today's budget cannot cover the episode.
    """
    ctx = ctx or get_context()
    episode = ctx.repo.get_episode(episode_id)
    show = ctx.repo.get_show(episode.show_id)
    topic = ctx.embedder.encode([f"{show.topic}. {show.topic_keywords}"])[0]
    pool = rank(
        ctx.repo.rank_chunks(show.show_id, topic),
        profile=show.ranking_profile,
        now=ctx.now(),
        threshold=ctx.settings.topic_threshold,
    )
    if not pool:
        raise ValueError(
            f"No passage matched the topic (threshold {ctx.settings.topic_threshold})."
        )
    limit = passages_per_segment(ctx)
    previous = _previous_episode(ctx, episode)
    incremental = previous is not None and episode.changed_item_ids is not None
    if ctx.budget is not None:
        reserve_episode(
            ctx.budget, ctx.settings, str(episode_id), show.max_segments, plan=not incremental
        )
    if previous is not None and episode.changed_item_ids is not None:
        segments, script = _carry_over(ctx, episode, previous, pool, limit)
        ctx.repo.update_episode(episode_id, script=script)
        mode = "incremental"
    else:
        plan = (
            plan_llm(pool, show, ctx)
            if ctx.llm is not None
            else plan_offline(pool, show.max_segments)
        )
        segments = [
            {
                "position": n,
                "title": title,
                "source_item_ids": items,
                "chunk_ids": passages_for(pool, items, limit),
                "needs_script": True,
            }
            for n, (title, items) in enumerate(plan, start=1)
        ]
        ctx.repo.update_episode(episode_id, script={"segments": {}, "avoid": {}})
        mode = "llm" if ctx.llm is not None else "offline"
    ctx.repo.replace_segments(episode_id, segments)
    log.info(
        "outline_planned",
        episode_id=str(episode_id),
        mode=mode,
        pool=len(pool),
        segments=len(segments),
        to_script=[s["position"] for s in segments if s["needs_script"]],
    )
    return Stage.SCRIPT

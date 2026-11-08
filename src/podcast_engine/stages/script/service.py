"""Script: grounded multi-speaker dialogue generation."""

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

from pydantic import BaseModel, Field

from podcast_engine.common.context import (
    PROMPT_VERSIONS,
    PipelineContext,
    get_context,
    script_prompt,
)
from podcast_engine.common.logging import get_logger
from podcast_engine.common.models import Claim, Delivery, ScriptLine
from podcast_engine.common.queue import Stage
from podcast_engine.common.repository import ChunkRecord, SegmentRecord, ShowRecord, StoredItem
from podcast_engine.common.text import speakable_sentences

log = get_logger("script")

OPEN_LINES = ["Let's start with {title}.", "Next up: {title}.", "Now, {title}."]
QUESTION_LINES = [
    "Here is the question: {title}?",
    "Let's tackle this one: {title}?",
    "So, {title}?",
]
REACT_LINES = [
    "That makes sense.",
    "Right, that is the key idea.",
    "Good point, say more.",
    "I like that.",
]


def load_prompt(prompts_dir: Path, name: str, version: int) -> str:
    """Read a versioned prompt (``<name>.v<version>.md``).

    Prompts are versioned files, never inline strings, so each episode can log exactly which
    prompt produced it and experiments can be rerun.
    """
    path = prompts_dir / f"{name}.v{version}.md"
    return path.read_text(encoding="utf-8")


class DraftLine(BaseModel):
    speaker: str
    text: str
    is_claim: bool = Field(
        description="True for a factual statement, False for framing or reactions"
    )
    passage_ids: list[str] = Field(
        default_factory=list, description="Passage ids that support a claim"
    )
    delivery: Delivery = Field(default=Delivery.NEUTRAL, description="How the line is said")


class DraftSegment(BaseModel):
    lines: list[DraftLine]


@dataclass(frozen=True)
class Passage:
    chunk: ChunkRecord
    item: StoredItem


def claim_id_for(episode_id: UUID, position: int, text: str) -> UUID:
    return uuid5(episode_id, f"{position}/{text}")


def with_episode_claim_ids(
    lines: list[dict[str, Any]], episode_id: UUID, position: int
) -> list[dict[str, Any]]:
    """A segment's lines reused in another episode, with claim ids that belong to that episode."""
    out = []
    for raw in lines:
        line = ScriptLine.model_validate(raw)
        claims = tuple(
            claim.model_copy(update={"claim_id": claim_id_for(episode_id, position, claim.text)})
            for claim in line.claims
        )
        out.append(line.model_copy(update={"claims": claims}).model_dump(mode="json"))
    return out


def opening_line(title: str, rng: random.Random) -> str:
    """Introduce a segment by its heading, keeping names like ClickHouse in their own case."""
    plain = title.rstrip("?.! ")
    if title.rstrip().endswith("?"):
        return rng.choice(QUESTION_LINES).format(title=plain)
    lowered = plain[0].lower() + plain[1:] if plain[1:2].islower() else plain
    return rng.choice(OPEN_LINES).format(title=lowered)


def to_script_lines(
    lines: list[DraftLine],
    labelled: dict[str, Passage],
    *,
    hosts: list[str],
    episode_id: UUID,
    position: int,
) -> list[ScriptLine]:
    out = []
    for line in lines:
        if line.speaker not in hosts:
            raise ValueError(f"unknown speaker {line.speaker!r}; hosts are {hosts}")
        claims: tuple[Claim, ...] = ()
        if line.is_claim:
            chunk_ids = tuple(labelled[p].chunk.chunk_id for p in line.passage_ids if p in labelled)
            claims = (
                Claim(
                    claim_id=claim_id_for(episode_id, position, line.text),
                    text=line.text,
                    chunk_ids=chunk_ids,
                ),
            )
        out.append(
            ScriptLine(speaker=line.speaker, text=line.text, claims=claims, delivery=line.delivery)
        )
    return out


def write_segment_offline(
    segment: SegmentRecord,
    passages: list[Passage],
    *,
    hosts: list[str],
    avoid: set[str],
    facts_per_segment: int,
    rng: random.Random,
) -> list[DraftLine]:
    """Quote whole sentences from the passages: a sentence is used only if one passage holds it."""
    labelled = {f"P{n + 1}": p for n, p in enumerate(passages)}
    pid_of = {p.chunk.chunk_id: pid for pid, p in labelled.items()}
    lines = [DraftLine(speaker=hosts[0], text=opening_line(segment.title, rng), is_claim=False)]
    found: dict[tuple[UUID, int], tuple[str, UUID]] = {}
    for passage in passages:
        for index, sentence in enumerate(speakable_sentences(passage.item.text)):
            if sentence in passage.chunk.text:
                found.setdefault((passage.item.item_id, index), (sentence, passage.chunk.chunk_id))
    facts = [found[key] for key in sorted(found, key=lambda k: k[1])][:facts_per_segment]
    for n, (sentence, chunk_id) in enumerate(facts):
        lines.append(
            DraftLine(
                speaker=hosts[(n + 1) % len(hosts)],
                text=sentence,
                is_claim=True,
                passage_ids=[pid_of[chunk_id]],
            )
        )
        if n % 2 == 1:
            lines.append(
                DraftLine(
                    speaker=hosts[n % len(hosts)], text=rng.choice(REACT_LINES), is_claim=False
                )
            )
    return [line for line in lines if line.text not in avoid]


# Spoken words per minute the length budget assumes, and the seconds of every episode that are not
# segments: the disclosure, opening and closing lines, chimes and transitions. Measured on a
# 2-minute Chatterbox episode (25 s); without it a 2-minute show ran to 2:23.
WORDS_PER_MINUTE = 150
FRAME_SECONDS = 25


def segment_words(target_minutes: int, segment_count: int) -> int:
    """The spoken words one segment gets, so the whole episode, frame included, fits the target."""
    seconds = max(target_minutes * 60 - FRAME_SECONDS, 0)
    return max(60, seconds * WORDS_PER_MINUTE // 60 // max(segment_count, 1))


def style_for(show: ShowRecord, hosts: list[str], segment_count: int) -> str:
    """Tone, audience, hosts and length for one segment; shared with the RQ1 ungrounded baseline."""
    words = segment_words(show.target_minutes, segment_count)
    return (
        f"Tone: {show.tone.value}. Audience expertise: {show.expertise.value}. Language: "
        f"{show.language}. Hosts: {', '.join(hosts)}. About {words} spoken words for this segment."
    )


def write_segment_llm(
    segment: SegmentRecord,
    passages: list[Passage],
    *,
    show: ShowRecord,
    segment_count: int,
    hosts: list[str],
    avoid: set[str],
    ctx: PipelineContext,
) -> list[DraftLine]:
    if ctx.llm is None:
        raise RuntimeError("write_segment_llm needs an LLM client")
    labelled = {f"P{n + 1}": p for n, p in enumerate(passages)}
    style = style_for(show, hosts, segment_count)
    listing = "\n".join(f"[{pid}] ({p.item.title}) {p.chunk.text}" for pid, p in labelled.items())
    redo = ""
    if avoid:
        redo = (
            "\n\nA reviewer found these statements unsupported by the passages. Do not repeat "
            "them:\n- " + "\n- ".join(sorted(avoid))
        )
    prompt = script_prompt(len(hosts))
    draft = ctx.llm.parse(
        system=load_prompt(ctx.settings.prompts_dir, prompt, PROMPT_VERSIONS[prompt])
        + "\n\n"
        + style,
        user=(
            f"Show: {show.topic}\nThis is segment {segment.position} of {segment_count}.\n\n"
            f"Segment title: {segment.title}\n\nPassages:\n{listing}{redo}\n\n"
            "Write this segment's lines, following the rules above."
        ),
        output_format=DraftSegment,
    )
    return draft.lines


def write_script(episode_id: UUID, ctx: PipelineContext | None = None) -> Stage | None:
    """FR4/FR5: write the dialogue from retrieved passages; every claim carries a citation.

    Only segments marked ``needs_script`` are written: all of them on a first build, the changed
    ones on a refresh, and the ones the fact-check gate sent back on a rewrite.
    """
    ctx = ctx or get_context()
    episode = ctx.repo.get_episode(episode_id)
    show = ctx.repo.get_show(episode.show_id)
    hosts = ctx.hosts(show.host_count)
    segments = ctx.repo.list_segments(episode_id)
    script = dict(episode.script or {})
    written: dict[str, Any] = {
        k: v
        for k, v in script.get("segments", {}).items()
        if int(k) in {s.position for s in segments}
    }
    avoid_by_segment: dict[str, list[str]] = script.get("avoid", {})
    items = {item.item_id: item for item in ctx.repo.list_items(show.show_id)}
    to_write = [s for s in segments if s.needs_script]
    if ctx.llm is not None and ctx.budget is not None and not ctx.settings.llm_fallback_model:
        # Do not start what cannot finish today (the episode's reservation counts as available).
        # A fallback model has its own quota; with one, each call is checked as it goes.
        ctx.budget.require(
            {ctx.settings.llm_model: len(to_write)}, f"writing {len(to_write)} segment(s)"
        )
    for segment in to_write:
        chunks = ctx.repo.get_chunks(segment.chunk_ids)
        passages = [
            Passage(chunks[c], items[chunks[c].item_id]) for c in segment.chunk_ids if c in chunks
        ]
        if not passages:
            raise ValueError(f"segment {segment.position} ({segment.title}) has no stored passages")
        avoid = set(avoid_by_segment.get(str(segment.position), []))
        if ctx.llm is not None:
            drafts = write_segment_llm(
                segment,
                passages,
                show=show,
                segment_count=len(segments),
                hosts=hosts,
                avoid=avoid,
                ctx=ctx,
            )
        else:
            rng = random.Random(f"{ctx.settings.seed}:{segment.position}:{episode.rewrite_count}")  # noqa: S311
            drafts = write_segment_offline(
                segment,
                passages,
                hosts=hosts,
                avoid=avoid,
                facts_per_segment=ctx.settings.facts_per_segment,
                rng=rng,
            )
        labelled = {f"P{n + 1}": p for n, p in enumerate(passages)}
        lines = to_script_lines(
            drafts, labelled, hosts=hosts, episode_id=episode_id, position=segment.position
        )
        written[str(segment.position)] = [line.model_dump(mode="json") for line in lines]
        # Saved at once, so if a later segment fails (an overloaded model, today's budget), a
        # retry writes only the segments still missing.
        script["segments"] = dict(sorted(written.items(), key=lambda kv: int(kv[0])))
        ctx.repo.update_episode(episode_id, script=script)
        ctx.repo.update_segment(episode_id, segment.position, needs_script=False)
    log.info(
        "script_written",
        episode_id=str(episode_id),
        written=[s.position for s in to_write],
        reused=[s.position for s in segments if not s.needs_script],
        writer="llm" if ctx.llm is not None else "offline-extractive",
    )
    return Stage.FACTCHECK


def script_lines(episode_script: dict[str, Any] | None) -> dict[int, list[ScriptLine]]:
    """The stored script as {position: lines}, for the stages after this one."""
    segments = (episode_script or {}).get("segments", {})
    return {
        int(k): [ScriptLine.model_validate(line) for line in v]
        for k, v in sorted(segments.items(), key=lambda kv: int(kv[0]))
    }

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

    Prompts are versioned files, never inline strings, so each episode can log exactly which prompt
    produced it and experiments can be rerun.

    Args:
        prompts_dir: The prompts folder.
        name: The prompt's name, such as ``script``.
        version: Its version number.

    Returns:
        The prompt's text.
    """
    path = prompts_dir / f"{name}.v{version}.md"
    return path.read_text(encoding="utf-8")


class DraftLine(BaseModel):
    """One drafted line: speaker, text, delivery and, for a claim, the passages it cites."""

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
    """What the script model returns for one segment: its lines."""

    lines: list[DraftLine]


@dataclass(frozen=True)
class Passage:
    """A retrieved passage and the source item it comes from."""

    chunk: ChunkRecord
    item: StoredItem


def claim_id_for(episode_id: UUID, position: int, text: str) -> UUID:
    """Return a claim's stable id within an episode.

    Args:
        episode_id: The episode.
        position: The segment's number.
        text: The claim's text.

    Returns:
        A UUID derived from the three, so the same claim keeps its id.
    """
    return uuid5(episode_id, f"{position}/{text}")


def with_episode_claim_ids(
    lines: list[dict[str, Any]], episode_id: UUID, position: int
) -> list[dict[str, Any]]:
    """Reuse a segment's lines in another episode, with claim ids that belong to that episode.

    Args:
        lines: The segment's stored lines.
        episode_id: The episode reusing them.
        position: The segment's number there.

    Returns:
        The lines with new claim ids.
    """
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
    """Introduce a segment by its heading, keeping names like ClickHouse in their own case.

    Args:
        title: The segment's heading.
        rng: The seeded random source that picks the wording.

    Returns:
        The line that opens the segment.
    """
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
    """Turn drafted lines into script lines, citing each claim's passages.

    Args:
        lines: The drafted lines.
        labelled: The segment's passages, by the label the writer saw (``P1``, ...).
        hosts: The host names, in speaking order.
        episode_id: The episode.
        position: The segment's number.

    Returns:
        The script lines.

    Raises:
        ValueError: A line's speaker is not one of the hosts.
    """
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
    """Write a segment offline by quoting whole sentences from its passages.

    A sentence is used only if one passage holds it, so every claim cites exactly where it came
    from. Statements the fact-check cut are not used again.

    Args:
        segment: The segment.
        passages: Its passages.
        hosts: The host names, in speaking order.
        avoid: Statements the fact-check cut.
        facts_per_segment: Most sentences to quote.
        rng: The seeded random source for the framing lines.

    Returns:
        The drafted lines.
    """
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
    """Return the spoken words one segment gets, so the whole episode fits the target length.

    The episode's frame (the disclosure, opening and closing lines, chimes and transitions) is taken
    off first; a segment gets at least 60 words.

    Args:
        target_minutes: The show's target length.
        segment_count: How many segments the episode has.

    Returns:
        The segment's word budget.
    """
    seconds = max(target_minutes * 60 - FRAME_SECONDS, 0)
    return max(60, seconds * WORDS_PER_MINUTE // 60 // max(segment_count, 1))


def style_for(show: ShowRecord, hosts: list[str], segment_count: int) -> str:
    """Describe the tone, audience, hosts and length for one segment.

    Shared with the RQ1 ungrounded baseline, so both conditions get the same instructions.

    Args:
        show: The show.
        hosts: The host names, in speaking order.
        segment_count: How many segments the episode has.

    Returns:
        The style instructions.
    """
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
    """Ask the LLM to write a segment from its passages, citing them.

    The passages are labelled ``P1``, ``P2``, ... so the model can cite them, and statements the
    fact-check cut are listed so it does not repeat them. A one-host show gets the narrator prompt.

    Args:
        segment: The segment.
        passages: Its passages.
        show: The show.
        segment_count: How many segments the episode has.
        hosts: The host names, in speaking order.
        avoid: Statements the fact-check cut.
        ctx: The pipeline context, with an LLM client.

    Returns:
        The drafted lines.

    Raises:
        RuntimeError: There is no LLM client.
    """
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
    """Write the dialogue from retrieved passages, every claim cited (stage 4, FR4/FR5).

    Only segments marked ``needs_script`` are written: all of them on a first build, the changed
    ones on a refresh, and the ones the fact-check gate sent back on a rewrite.

    Without a fallback model, the step is checked against today's budget first, so nothing starts
    that cannot finish (the episode's reservation counts as available); with one, each call is
    checked as it goes. Each segment is saved as soon as it is written, so if a later one fails (an
    overloaded model, today's budget), a retry writes only the segments still missing.

    Args:
        episode_id: The episode being made.
        ctx: Shared clients; built from settings when omitted.

    Returns:
        The next stage, fact-check.

    Raises:
        ValueError: A segment has no stored passages, or a line names an unknown speaker.
        GeminiQuotaError: Today's budget cannot cover the segments.
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
    """Read the stored script as lines by segment, for the stages after this one.

    Args:
        episode_script: The episode's stored script, or None.

    Returns:
        Each segment's lines, by segment number in order.
    """
    segments = (episode_script or {}).get("segments", {})
    return {
        int(k): [ScriptLine.model_validate(line) for line in v]
        for k, v in sorted(segments.items(), key=lambda kv: int(kv[0]))
    }

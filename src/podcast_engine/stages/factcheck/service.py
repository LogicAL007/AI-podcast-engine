"""Fact-check: the gate between script and voice."""

from uuid import UUID

from pydantic import BaseModel

from podcast_engine.common.context import PROMPT_VERSIONS, PipelineContext, get_context
from podcast_engine.common.logging import get_logger
from podcast_engine.common.models import Claim, EpisodeStatus, FactCheckReport
from podcast_engine.common.queue import Stage
from podcast_engine.common.text import content_tokens

log = get_logger("factcheck")

SUPPORT_THRESHOLD = 0.6  # offline judge: share of a claim's content words found in its passages


class Verdict(BaseModel):
    claim_number: int
    supported: bool
    reason: str


class Verdicts(BaseModel):
    verdicts: list[Verdict]


def route_after_factcheck(
    report: FactCheckReport, *, rewrites_done: int, max_rewrites: int
) -> Stage | None:
    """Decide where the episode goes after the gate.

    Passing scripts go to voice. Failing scripts loop back to the script stage until the
    rewrite budget is spent; then None holds the episode for human review rather than voicing
    unsupported claims.
    """
    if report.passed:
        return Stage.VOICE
    if rewrites_done < max_rewrites:
        return Stage.SCRIPT
    return None


def lexical_support(claim: str, passages: list[str]) -> float:
    """Offline stand-in for the judge.

    It catches invented claims made of new words, not ones that reuse the source's words.
    """
    tokens = set(content_tokens(claim))
    if not tokens:
        return 1.0
    evidence = set(content_tokens(" ".join(passages)))
    return len(tokens & evidence) / len(tokens)


def judge_llm(
    items: list[tuple[Claim, list[str]]], ctx: PipelineContext
) -> dict[int, tuple[bool, str]]:
    from podcast_engine.stages.script.service import load_prompt

    if ctx.llm is None:
        raise RuntimeError("judge_llm needs an LLM client")
    listing = "\n\n".join(
        f"Claim {n}: {claim.text}\nCited passages:\n" + "\n".join(f"- {p}" for p in passages)
        for n, (claim, passages) in enumerate(items, start=1)
    )
    result = ctx.llm.parse(
        system=load_prompt(ctx.settings.prompts_dir, "factcheck", PROMPT_VERSIONS["factcheck"]),
        user=listing,
        output_format=Verdicts,
    )
    return {v.claim_number: (v.supported, v.reason) for v in result.verdicts}


def check_script(episode_id: UUID, ctx: PipelineContext | None = None) -> Stage | None:
    """FR9: judge each claim against its retrieved passages, then route with the report."""
    from podcast_engine.stages.script.service import script_lines

    ctx = ctx or get_context()
    episode = ctx.repo.get_episode(episode_id)
    script = script_lines(episode.script)
    if not script:
        raise ValueError("There is no script to check.")
    chunk_ids = {
        c
        for lines in script.values()
        for line in lines
        for claim in line.claims
        for c in claim.chunk_ids
    }
    chunks = ctx.repo.get_chunks(chunk_ids)

    segment_of: dict[UUID, int] = {}
    to_judge: list[tuple[Claim, list[str]]] = []
    verdicts: dict[UUID, tuple[bool, str]] = {}
    for position, lines in script.items():
        claims = [claim for line in lines for claim in line.claims]
        ctx.repo.replace_claims(
            episode_id,
            position,
            [{"claim_id": c.claim_id, "text": c.text, "chunk_ids": c.chunk_ids} for c in claims],
        )
        for claim in claims:
            segment_of[claim.claim_id] = position
            if not claim.chunk_ids:
                verdicts[claim.claim_id] = (False, "no citation")
            else:
                to_judge.append((claim, [chunks[c].text for c in claim.chunk_ids if c in chunks]))
    by_number = judge_llm(to_judge, ctx) if ctx.llm is not None and to_judge else {}
    for n, (claim, passages) in enumerate(to_judge, start=1):
        if ctx.llm is not None:
            verdicts[claim.claim_id] = by_number.get(n, (False, "no verdict returned"))
        else:
            score = lexical_support(claim.text, passages)
            verdicts[claim.claim_id] = (score >= SUPPORT_THRESHOLD, f"word overlap {score:.0%}")
    ctx.repo.set_verdicts(verdicts)

    claims_by_id = {
        claim.claim_id: claim
        for lines in script.values()
        for line in lines
        for claim in line.claims
    }
    unsupported = tuple(claims_by_id[cid] for cid, (ok, _) in verdicts.items() if not ok)
    report = FactCheckReport(
        episode_id=episode_id, unsupported=unsupported, total_claims=len(claims_by_id)
    )
    # A script a reviewer edited is never regenerated over the edit: if it fails, it goes back
    # to review. A passing script waits for approval when the show reviews before voicing.
    edited = bool((episode.script or {}).get("edited_segments"))
    decision = route_after_factcheck(
        report,
        rewrites_done=episode.rewrite_count,
        max_rewrites=0 if edited else ctx.settings.max_rewrites,
    )
    # A rewrite is one request per flagged segment plus another check. If today's Gemini budget
    # cannot cover that, hold the episode for review instead of failing it halfway.
    flagged_segments = {segment_of[c.claim_id] for c in unsupported}
    low_budget = (
        decision is Stage.SCRIPT
        and ctx.llm is not None
        and ctx.budget is not None
        and ctx.budget.shortfall({ctx.settings.llm_model: len(flagged_segments) + 1}) is not None
    )
    if low_budget:
        decision = None
    awaiting_approval = (
        decision is Stage.VOICE
        and episode.approved_at is None
        and ctx.repo.get_show(episode.show_id).review_before_voice
    )
    history = list((episode.fact_check or {}).get("history", []))
    history.append(
        {
            "pass": len(history) + 1,
            "claims": report.total_claims,
            "unsupported": len(unsupported),
            "support_rate": report.support_rate,
            "next": "needs_review" if decision is None or awaiting_approval else decision.value,
        }
    )
    fact_check = {
        "judge": f"{ctx.llm.provider}:{ctx.llm.model}"
        if ctx.llm is not None
        else "offline-word-overlap",
        "history": history,
        "flagged": [
            {"segment": segment_of[c.claim_id], "claim": c.text, "reason": verdicts[c.claim_id][1]}
            for c in unsupported
        ],
    }
    log.info(
        "gate_passed" if report.passed else "gate_failed", episode_id=str(episode_id), **history[-1]
    )

    if decision is Stage.SCRIPT:
        script_state = dict(episode.script or {})
        avoid = {k: list(v) for k, v in script_state.get("avoid", {}).items()}
        for claim in unsupported:
            avoid.setdefault(str(segment_of[claim.claim_id]), []).append(claim.text)
        script_state["avoid"] = avoid
        for position in sorted(flagged_segments):
            ctx.repo.update_segment(episode_id, position, needs_script=True)
        ctx.repo.update_episode(
            episode_id,
            fact_check=fact_check,
            script=script_state,
            rewrite_count=episode.rewrite_count + 1,
        )
        return Stage.SCRIPT
    if decision is None:
        after = "a reviewer's edit" if edited else f"{episode.rewrite_count} rewrite(s)"
        error = f"{len(unsupported)} unsupported claim(s) after {after}; not voiced."
        if low_budget:
            error = (
                f"{len(unsupported)} unsupported claim(s); not rewritten, because today's Gemini "
                "budget cannot cover another pass. Edit the flagged lines, or try again after "
                "midnight Pacific time."
            )
        ctx.repo.update_episode(
            episode_id, fact_check=fact_check, status=EpisodeStatus.NEEDS_REVIEW, error=error
        )
        return None
    if awaiting_approval:
        ctx.repo.update_episode(
            episode_id,
            fact_check=fact_check,
            status=EpisodeStatus.NEEDS_REVIEW,
            error="The script passed the fact-check and is waiting for approval before voicing.",
        )
        return None
    ctx.repo.update_episode(episode_id, fact_check=fact_check)
    return Stage.VOICE

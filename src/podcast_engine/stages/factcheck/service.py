"""Fact-check: the gate between script and voice."""

from uuid import UUID

from podcast_engine.common.models import FactCheckReport
from podcast_engine.common.queue import Stage


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


def check_script(episode_id: UUID) -> Stage | None:
    """FR9: judge each claim against its retrieved passages, then route with the report."""
    raise NotImplementedError("check_script: LLM-as-judge per claim, then route_after_factcheck")

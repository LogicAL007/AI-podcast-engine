from uuid import uuid4

from podcast_engine.common.models import Claim, FactCheckReport
from podcast_engine.common.queue import Stage
from podcast_engine.stages.factcheck.service import route_after_factcheck


def _report(unsupported: int, total: int = 10) -> FactCheckReport:
    claims = tuple(Claim(claim_id=uuid4(), text=f"claim {i}") for i in range(unsupported))
    return FactCheckReport(episode_id=uuid4(), unsupported=claims, total_claims=total)


def test_passing_script_goes_to_voice() -> None:
    assert route_after_factcheck(_report(0), rewrites_done=0, max_rewrites=2) is Stage.VOICE


def test_unsupported_claims_loop_back_to_script() -> None:
    assert route_after_factcheck(_report(2), rewrites_done=1, max_rewrites=2) is Stage.SCRIPT


def test_exhausted_rewrites_hold_the_episode() -> None:
    assert route_after_factcheck(_report(2), rewrites_done=2, max_rewrites=2) is None


def test_support_rate() -> None:
    assert _report(1, total=10).support_rate == 0.9
    assert _report(0, total=0).support_rate == 1.0

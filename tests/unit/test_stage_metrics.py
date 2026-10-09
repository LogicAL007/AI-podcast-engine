from uuid import uuid4

import pytest
from prometheus_client import REGISTRY

from podcast_engine.common.queue import Stage
from podcast_engine.common.timing import stage_timer


def _runs(stage: Stage, outcome: str) -> float:
    value = REGISTRY.get_sample_value(
        "podcast_stage_runs_total", {"stage": stage.value, "outcome": outcome}
    )
    return value or 0.0


def _observations(stage: Stage) -> float:
    value = REGISTRY.get_sample_value(
        "podcast_stage_duration_seconds_count", {"stage": stage.value}
    )
    return value or 0.0


def test_successful_run_is_counted_and_timed() -> None:
    runs, observed = _runs(Stage.VOICE, "success"), _observations(Stage.VOICE)
    with stage_timer(Stage.VOICE, uuid4()):
        pass
    assert _runs(Stage.VOICE, "success") == runs + 1
    assert _observations(Stage.VOICE) == observed + 1


def test_failed_run_is_counted_timed_and_reraised() -> None:
    runs, observed = _runs(Stage.SCRIPT, "failure"), _observations(Stage.SCRIPT)
    with pytest.raises(RuntimeError, match="boom"), stage_timer(Stage.SCRIPT, uuid4()):
        raise RuntimeError("boom")
    assert _runs(Stage.SCRIPT, "failure") == runs + 1
    assert _observations(Stage.SCRIPT) == observed + 1

from datetime import UTC, datetime, timedelta

import pytest

from podcast_engine.stages.retrieve_plan.service import combined_score, recency_score

NOW = datetime(2026, 10, 7, tzinfo=UTC)


def test_recency_halves_each_half_life() -> None:
    assert recency_score(NOW, now=NOW, half_life_days=7) == 1.0
    assert recency_score(NOW - timedelta(days=7), now=NOW, half_life_days=7) == pytest.approx(0.5)


def test_undated_items_score_zero() -> None:
    assert recency_score(None, now=NOW, half_life_days=7) == 0.0


def test_recency_weight_shifts_ranking() -> None:
    daily = combined_score(0.5, 1.0, recency_weight=0.8)
    explainer = combined_score(0.5, 1.0, recency_weight=0.1)
    assert daily > explainer


def test_weight_out_of_range_rejected() -> None:
    with pytest.raises(ValueError, match="recency_weight"):
        combined_score(0.5, 0.5, recency_weight=1.5)

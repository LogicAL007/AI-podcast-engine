import pytest

from evaluation.stats import (
    cohen_kappa,
    compare_independent,
    compare_paired,
    kappa_label,
    mean_interval,
    wilson_interval,
)


def test_kappa_matches_a_worked_example() -> None:
    # 50 items: both "yes" 20, both "no" 15, A yes/B no 5, A no/B yes 10.
    # p_o = 0.70, p_e = 0.5*0.6 + 0.5*0.4 = 0.50, kappa = 0.40.
    a = ["yes"] * 20 + ["no"] * 15 + ["yes"] * 5 + ["no"] * 10
    b = ["yes"] * 20 + ["no"] * 15 + ["no"] * 5 + ["yes"] * 10
    assert cohen_kappa(a, b) == pytest.approx(0.40)
    assert kappa_label(0.40) == "fair"
    assert cohen_kappa(["x", "y"], ["x", "y"]) == 1.0


def test_kappa_needs_matched_ratings() -> None:
    with pytest.raises(ValueError, match="same"):
        cohen_kappa(["a"], ["a", "b"])


def test_independent_uses_welch_for_normal_data_and_reports_direction() -> None:
    a = [5.1, 4.9, 5.3, 5.0, 5.2, 4.8, 5.1, 5.0, 4.9, 5.2]
    b = [4.1, 3.9, 4.3, 4.0, 4.2, 3.8, 4.1, 4.0, 3.9, 4.2]
    result = compare_independent(a, b)
    assert result.test == "Welch t-test"
    assert result.p_value < 0.001
    assert result.effect_size > 0  # a is higher


def test_independent_falls_back_to_mann_whitney_for_skewed_data() -> None:
    a = [1, 1, 1, 1, 1, 1, 1, 2, 9, 10]
    b = [0, 0, 0, 0, 0, 0, 0, 0, 1, 1]
    result = compare_independent(a, b)
    assert result.test == "Mann-Whitney U"
    assert result.effect_size > 0


def test_paired_detects_a_consistent_gain() -> None:
    before = [3.0, 3.2, 2.9, 3.1, 3.4, 2.8, 3.0, 3.3]
    after = [x + 0.5 + 0.01 * n for n, x in enumerate(before)]
    result = compare_paired(after, before)
    assert result.p_value < 0.01
    assert result.effect_size > 0


def test_paired_identical_data_is_not_significant() -> None:
    assert compare_paired([1, 2, 3], [1, 2, 3]).p_value == 1.0


def test_intervals() -> None:
    low, high = wilson_interval(27, 30)
    assert low < 0.9 < high
    assert wilson_interval(30, 30)[1] == 1.0
    low, high = mean_interval([4, 4, 5, 3, 4])
    assert low < 4.0 < high

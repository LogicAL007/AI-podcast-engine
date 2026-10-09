"""Statistics named in the PRD's analysis plan.

"Use paired or independent t-tests (or Mann-Whitney U where distributions are not normal), report
effect sizes", and Cohen's kappa for the two RQ1 raters. Each test reports which test ran and why,
so the choice is visible in the write-up rather than buried in code.
"""

import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any

from scipy import stats

NORMALITY_ALPHA = 0.05  # Shapiro-Wilk: below this, treat the data as not normal


@dataclass(frozen=True)
class TestResult:
    test: str
    reason: str
    statistic: float
    p_value: float
    effect_size: float
    effect_name: str
    n: tuple[int, ...]
    means: tuple[float, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def cohen_kappa(rater_a: Sequence[str], rater_b: Sequence[str]) -> float:
    """Agreement between two raters beyond chance: 1 perfect, 0 chance level, below 0 worse."""
    if len(rater_a) != len(rater_b) or not rater_a:
        raise ValueError("both raters must label the same, non-empty set of items")
    n = len(rater_a)
    observed = sum(a == b for a, b in zip(rater_a, rater_b, strict=True)) / n
    count_a, count_b = Counter(rater_a), Counter(rater_b)
    expected = sum(count_a[label] * count_b[label] for label in count_a.keys() | count_b.keys()) / (
        n * n
    )
    if expected == 1.0:
        return 1.0  # both raters used one identical label throughout
    return (observed - expected) / (1 - expected)


def kappa_label(kappa: float) -> str:
    """Landis and Koch's (1977) conventional wording."""
    for limit, word in (
        (0.0, "poor"),
        (0.2, "slight"),
        (0.4, "fair"),
        (0.6, "moderate"),
        (0.8, "substantial"),
    ):
        if kappa <= limit:
            return word
    return "almost perfect"


def _normal(values: Sequence[float]) -> bool:
    if len(values) < 3 or len(set(values)) < 3:
        return False
    return bool(stats.shapiro(values).pvalue >= NORMALITY_ALPHA)


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def compare_independent(a: Sequence[float], b: Sequence[float]) -> TestResult:
    """Two separate groups (RQ2). Welch's t if both look normal, else Mann-Whitney U."""
    if len(a) < 2 or len(b) < 2:
        raise ValueError("each group needs at least two values")
    if _normal(a) and _normal(b):
        result = stats.ttest_ind(a, b, equal_var=False)
        pooled = math.sqrt((stats.tvar(a) + stats.tvar(b)) / 2)
        effect = (_mean(a) - _mean(b)) / pooled if pooled else 0.0
        return TestResult(
            "Welch t-test",
            "both groups pass Shapiro-Wilk",
            float(result.statistic),
            float(result.pvalue),
            effect,
            "Cohen's d",
            (len(a), len(b)),
            (_mean(a), _mean(b)),
        )
    result = stats.mannwhitneyu(a, b, alternative="two-sided")
    effect = 1 - 2 * float(result.statistic) / (len(a) * len(b))  # rank-biserial correlation
    return TestResult(
        "Mann-Whitney U",
        "a group fails Shapiro-Wilk (or has too few distinct values)",
        float(result.statistic),
        float(result.pvalue),
        -effect,
        "rank-biserial r",
        (len(a), len(b)),
        (_mean(a), _mean(b)),
    )


def compare_paired(a: Sequence[float], b: Sequence[float]) -> TestResult:
    """The same people or topics under two conditions (RQ1 by topic, RQ3). Paired t or Wilcoxon."""
    if len(a) != len(b) or len(a) < 2:
        raise ValueError("paired data needs two equal-length sequences of at least two values")
    differences = [x - y for x, y in zip(a, b, strict=True)]
    if _normal(differences):
        result = stats.ttest_rel(a, b)
        sd = stats.tstd(differences)
        effect = _mean(differences) / sd if sd else 0.0
        return TestResult(
            "paired t-test",
            "differences pass Shapiro-Wilk",
            float(result.statistic),
            float(result.pvalue),
            effect,
            "Cohen's d_z",
            (len(a),),
            (_mean(a), _mean(b)),
        )
    nonzero = [d for d in differences if d != 0]
    if not nonzero:
        return TestResult(
            "Wilcoxon signed-rank",
            "every pair is identical",
            0.0,
            1.0,
            0.0,
            "matched-pairs rank-biserial r",
            (len(a),),
            (_mean(a), _mean(b)),
        )
    result = stats.wilcoxon(a, b)
    ranks = stats.rankdata([abs(d) for d in nonzero])
    positive = sum(r for r, d in zip(ranks, nonzero, strict=True) if d > 0)
    effect = (2 * positive - ranks.sum()) / ranks.sum()
    return TestResult(
        "Wilcoxon signed-rank",
        "differences fail Shapiro-Wilk (or have too few distinct values)",
        float(result.statistic),
        float(result.pvalue),
        float(effect),
        "matched-pairs rank-biserial r",
        (len(a),),
        (_mean(a), _mean(b)),
    )


def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """95% interval for a proportion (claim accuracy), sound even near 0% or 100%."""
    if total == 0:
        return (0.0, 1.0)
    p = successes / total
    centre = (p + z * z / (2 * total)) / (1 + z * z / total)
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / (1 + z * z / total)
    return (max(0.0, centre - half), min(1.0, centre + half))


def mean_interval(values: Sequence[float], confidence: float = 0.95) -> tuple[float, float]:
    """t-based interval for a mean rating (MOS)."""
    if len(values) < 2:
        raise ValueError("need at least two values")
    half = stats.t.ppf((1 + confidence) / 2, len(values) - 1) * stats.sem(values)
    centre = _mean(values)
    return (centre - float(half), centre + float(half))

import csv
import json
from pathlib import Path

import pytest

from evaluation.rq1_claim_audit.analyse import analyse, report
from evaluation.rq1_claim_audit.sheets import FIELDS


def _run(tmp_path: Path, ratings: list[tuple[str, str, str, str, str]]) -> Path:
    """ratings: (topic, condition, A accurate, B accurate, A notes)."""
    key: list[dict[str, object]] = []
    sheets: dict[str, list[dict[str, str]]] = {"A": [], "B": []}
    for n, (topic, condition, a, b, note) in enumerate(ratings, start=1):
        uid = f"c{n:04d}"
        key.append({"claim_uid": uid, "topic_id": topic, "condition": condition,
                    "cited": condition == "grounded", "text": uid, "rated": True})  # fmt: skip
        for rater, value in (("A", a), ("B", b)):
            sheets[rater].append({**dict.fromkeys(FIELDS, ""), "claim_uid": uid, "claim": uid,
                                  "accurate": value, "in_source": "yes" if value == "yes" else "no",
                                  "notes": note if rater == "A" else ""})  # fmt: skip
    (tmp_path / "key.json").write_text(json.dumps(key))
    for rater, rows in sheets.items():
        with (tmp_path / f"rater_{rater}.csv").open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
    return tmp_path


def test_accuracy_kappa_and_disputes(tmp_path: Path) -> None:
    ratings = []
    for topic in ("t1", "t2", "t3"):
        ratings += [(topic, "grounded", "yes", "yes", "")] * 3
        ratings += [(topic, "ungrounded", "yes", "yes", ""), (topic, "ungrounded", "no", "no", "")]
    ratings += [("t1", "ungrounded", "yes", "no", "")]  # a dispute
    ratings += [("t2", "ungrounded", "yes", "no", "final: no")]  # adjudicated
    result = analyse(_run(tmp_path, ratings), "exclude")

    grounded, ungrounded = result["conditions"]["grounded"], result["conditions"]["ungrounded"]
    assert grounded["accuracy"] == 1.0
    assert ungrounded["claims_settled"] == 7  # 6 agreed + 1 adjudicated; 1 excluded
    assert ungrounded["accuracy"] == pytest.approx(3 / 7)
    assert grounded["citation_coverage"] == 1.0
    assert ungrounded["citation_coverage"] == 0.0
    assert len(result["disputes"]) == 2
    assert 0 < result["kappa"]["accurate"]["value"] < 1
    assert result["topics_paired"] == 3
    assert "RQ1" in report(result)


def test_conservative_rule_counts_disputes_as_inaccurate(tmp_path: Path) -> None:
    ratings = [("t1", "grounded", "yes", "yes", ""), ("t1", "grounded", "yes", "unsure", ""),
               ("t1", "ungrounded", "no", "no", "")]  # fmt: skip
    result = analyse(_run(tmp_path, ratings), "inaccurate")
    assert result["conditions"]["grounded"]["accuracy"] == 0.5


def test_bad_labels_are_rejected(tmp_path: Path) -> None:
    run = _run(tmp_path, [("t1", "grounded", "maybe", "yes", "")])
    with pytest.raises(ValueError, match="accurate must be one of"):
        analyse(run, "exclude")

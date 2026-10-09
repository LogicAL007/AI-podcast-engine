"""RQ1, step 3: agreement between raters, then grounded vs ungrounded accuracy.

    python -m evaluation.rq1_claim_audit.analyse evaluation/results/rq1/<run> [--disputes exclude]

Reads rater_A.csv and rater_B.csv (filled in), key.json and scripts.jsonl, and reports the PRD's
measures: claim-level accuracy, unsupported-claim rate and citation coverage per condition, Cohen's
kappa for each label, and a paired test across topics (each topic has a script in both conditions).

A claim counts when both raters agree. Disagreements are listed for adjudication; until then
``--disputes exclude`` leaves them out and ``--disputes inaccurate`` counts them against the
condition (the conservative choice). An adjudicated value in rater A's ``notes`` column as
``final: yes`` or ``final: no`` settles a dispute.
"""

import argparse
import csv
import json
import re
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from evaluation.stats import cohen_kappa, compare_paired, kappa_label, wilson_interval

CONDITIONS = ("grounded", "ungrounded")
VALID = {"accurate": {"yes", "no", "unsure"}, "in_source": {"yes", "no"}}


def read_sheet(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = {row["claim_uid"]: row for row in csv.DictReader(handle)}
    for uid, row in rows.items():
        for field, allowed in VALID.items():
            value = row[field].strip().lower()
            if value not in allowed:
                raise ValueError(
                    f"{path.name} {uid}: {field} must be one of {sorted(allowed)}, not {value!r}"
                )
            row[field] = value
    return rows


def consensus(a: str, b: str, note: str, disputes: str) -> bool | None:
    """True/False when settled; None when the claim is left out."""
    adjudicated = re.search(r"final:\s*(yes|no)", note.lower())
    if a == b and a != "unsure":
        return a == "yes"
    if adjudicated:
        return adjudicated.group(1) == "yes"
    return False if disputes == "inaccurate" else None


def analyse(run: Path, disputes: str) -> dict[str, Any]:
    a, b = read_sheet(run / "rater_A.csv"), read_sheet(run / "rater_B.csv")
    if a.keys() != b.keys():
        raise ValueError("the two sheets must contain the same claims")
    key = {
        k["claim_uid"]: k for k in json.loads((run / "key.json").read_text()) if k.get("claim_uid")
    }
    all_claims = json.loads((run / "key.json").read_text())

    uids = sorted(a)
    kappas = {
        field: cohen_kappa([a[u][field] for u in uids], [b[u][field] for u in uids])
        for field in VALID
    }
    disputed = [
        {"claim_uid": u, "claim": a[u]["claim"], "A": a[u]["accurate"], "B": b[u]["accurate"]}
        for u in uids
        if a[u]["accurate"] != b[u]["accurate"] or a[u]["accurate"] == "unsure"
    ]

    per_condition: dict[str, dict[str, Any]] = {}
    by_topic: dict[str, dict[str, list[bool]]] = defaultdict(lambda: defaultdict(list))
    for condition in CONDITIONS:
        rated = [u for u in uids if key[u]["condition"] == condition]
        accurate = [
            consensus(a[u]["accurate"], b[u]["accurate"], a[u]["notes"], disputes) for u in rated
        ]
        in_source = [a[u]["in_source"] == b[u]["in_source"] == "yes" for u in rated]
        settled = [x for x in accurate if x is not None]
        for u, value in zip(rated, accurate, strict=True):
            if value is not None:
                by_topic[key[u]["topic_id"]][condition].append(value)
        everything = [c for c in all_claims if c["condition"] == condition]
        correct = sum(settled)
        per_condition[condition] = {
            "claims_rated": len(rated),
            "claims_settled": len(settled),
            "accuracy": correct / len(settled) if settled else None,
            "accuracy_ci95": wilson_interval(correct, len(settled)),
            "unsupported_rate": 1 - sum(in_source) / len(in_source) if in_source else None,
            "citation_coverage": sum(c["cited"] for c in everything) / len(everything)
            if everything
            else None,
            "claims_total": len(everything),
        }
    paired_topics = sorted(t for t, v in by_topic.items() if all(v[c] for c in CONDITIONS))
    paired = None
    if len(paired_topics) >= 2:
        grounded = [
            sum(by_topic[t]["grounded"]) / len(by_topic[t]["grounded"]) for t in paired_topics
        ]
        ungrounded = [
            sum(by_topic[t]["ungrounded"]) / len(by_topic[t]["ungrounded"]) for t in paired_topics
        ]
        paired = compare_paired(grounded, ungrounded).as_dict()
    return {
        "kappa": {f: {"value": k, "label": kappa_label(k)} for f, k in kappas.items()},
        "conditions": per_condition,
        "paired_by_topic": paired,
        "topics_paired": len(paired_topics),
        "disputes": disputed,
        "dispute_rule": disputes,
    }


def report(result: dict[str, Any]) -> str:
    lines = ["# RQ1: grounded vs ungrounded script accuracy", ""]
    for field, k in result["kappa"].items():
        lines.append(f"- Cohen's kappa, {field}: {k['value']:.2f} ({k['label']})")
    lines += ["", "| Measure | Grounded | Ungrounded |", "|---|---|---|"]

    def cell(condition: str, name: str) -> str:
        value = result["conditions"][condition][name]
        if value is None:
            return "n/a"
        if name == "accuracy":
            low, high = result["conditions"][condition]["accuracy_ci95"]
            return f"{value:.0%} (95% CI {low:.0%}-{high:.0%})"
        return f"{value:.0%}" if isinstance(value, float) else str(value)

    for name, label in (
        ("accuracy", "Claim accuracy (target >= 90% grounded)"),
        ("unsupported_rate", "Not stated in the source"),
        ("citation_coverage", "Claims with a citation"),
        ("claims_settled", "Claims counted"),
        ("claims_total", "Claims in the scripts"),
    ):
        lines.append(f"| {label} | {cell('grounded', name)} | {cell('ungrounded', name)} |")
    paired = result["paired_by_topic"]
    if paired:
        lines += [
            "",
            f"Per-topic accuracy, {result['topics_paired']} topics: {paired['test']} "
            f"({paired['reason']}), "
            f"statistic {paired['statistic']:.2f}, p = {paired['p_value']:.4f}, "
            f"{paired['effect_name']} = {paired['effect_size']:.2f}; means "
            f"{paired['means'][0]:.0%} vs {paired['means'][1]:.0%}.",
        ]
    lines += ["", f"{len(result['disputes'])} disputed claim(s), rule: {result['dispute_rule']}."]
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("run", type=Path)
    parser.add_argument("--disputes", choices=["exclude", "inaccurate"], default="exclude")
    args = parser.parse_args(argv)
    result = analyse(args.run, args.disputes)
    (args.run / "analysis.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    text = report(result)
    (args.run / "analysis.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

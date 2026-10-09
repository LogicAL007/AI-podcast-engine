"""RQ1, step 2: blinded claim-rating sheets for two raters, plus the key that unblinds them.

    python -m evaluation.rq1_claim_audit.sheets evaluation/results/rq1/<run> [--per-script 12]

Pools the claims of both conditions, shuffles them with a fixed seed and hides which condition each
came from. Raters judge each claim against the source page snapshot (sources/<topic>.md, the same
text the system saw), not against the passage the system cited, which would reveal the condition.

Labels (see RATING_GUIDE.md):
  accurate      yes / no / unsure   is the claim true?
  in_source     yes / no            does the source page state or directly imply it?

The grounded draft and the final script share most claims; each distinct claim text is rated once
per topic and condition. ``--per-script`` samples up to N claims per script ("a sample", as the PRD
puts it) to bound the raters' work; 0 rates every claim.
"""

import argparse
import csv
import json
import random
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from evaluation.harness import RESULTS, caching_fetch
from podcast_engine.stages.ingest.extract import extract_page

SEED = 2026
FIELDS = [
    "claim_uid",
    "topic_id",
    "topic",
    "source_file",
    "segment",
    "claim",
    "accurate",
    "in_source",
    "notes",
]


def claims_of(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Distinct claims of a record, with whether each is in the draft and the final script."""
    found: dict[str, dict[str, Any]] = {}
    for stage in ("draft", "final"):
        for segment in record.get(stage, []):
            for line in segment["lines"]:
                for claim in line["claims"]:
                    entry = found.setdefault(
                        claim["text"],
                        {"text": claim["text"], "segment": segment["title"],
                         "cited": bool(claim["chunk_ids"]), "in_draft": False, "in_final": False},
                    )  # fmt: skip
                    entry[f"in_{stage}"] = True
    return list(found.values())


def write_source(folder: Path, topic: dict[str, str], fetch: Any) -> str:
    page = extract_page(fetch(topic["url"]))
    path = folder / "sources" / f"{topic['id']}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n\n".join(f"## {s.heading}\n\n{s.text}" for s in page.sections)
    path.write_text(f"# {page.title}\n\n{topic['url']}\n\n{body}\n", encoding="utf-8")
    return f"sources/{topic['id']}.md"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("run", type=Path)
    parser.add_argument("--per-script", type=int, default=12)
    args = parser.parse_args(argv)
    rng = random.Random(SEED)  # noqa: S311 - a reproducible shuffle, not security
    fetch = caching_fetch(RESULTS / "pages")
    records = [
        json.loads(line) for line in (args.run / "scripts.jsonl").read_text().splitlines() if line
    ]
    key: list[dict[str, Any]] = []
    pool: list[tuple[dict[str, str], dict[str, Any]]] = []
    sources: dict[str, str] = {}
    for record in records:
        if record["condition"] == "error":
            continue
        topic = record["topic"]
        if topic["id"] not in sources:
            sources[topic["id"]] = write_source(args.run, topic, fetch)
        entries = [
            {"topic_id": topic["id"], "condition": record["condition"], "rated": False, **claim}
            for claim in claims_of(record)
        ]
        key.extend(entries)
        chosen = (
            entries
            if args.per_script <= 0
            else rng.sample(entries, min(args.per_script, len(entries)))
        )
        for entry in chosen:
            entry["rated"] = True
            pool.append((topic, entry))
    rng.shuffle(pool)
    sheet_rows = []
    for n, (topic, entry) in enumerate(pool, start=1):
        entry["claim_uid"] = f"c{n:04d}"
        sheet_rows.append(
            {"claim_uid": entry["claim_uid"], "topic_id": topic["id"], "topic": topic["topic"],
             "source_file": sources[topic["id"]], "segment": entry["segment"],
             "claim": entry["text"],
             "accurate": "", "in_source": "", "notes": ""}
        )  # fmt: skip
    for rater in ("A", "B"):
        with (args.run / f"rater_{rater}.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(sheet_rows)
    (args.run / "key.json").write_text(json.dumps(key, indent=1), encoding="utf-8")
    print(
        f"{len(sheet_rows)} claims to rate "
        f"({sum(e['condition'] == 'grounded' for _, e in pool)} grounded, "
        f"{sum(e['condition'] == 'ungrounded' for _, e in pool)} ungrounded) "
        f"from {len(sources)} topics\n"
        f"give each rater their sheet and the sources/ folder; keep key.json from them"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

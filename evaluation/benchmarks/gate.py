"""How well does the fact-check gate (FR9) catch unsupported claims? A labelled claim set, scored.

    python -m evaluation.benchmarks.gate [--llm]

Each claim cites a real chunk of the ClickHouse page and has a known label:

  supported    verbatim     a sentence of the cited passage
  supported    paraphrase   the cited passage's meaning in different words (hand-written)
  unsupported  fabricated   a false statement in new words (hand-written)
  unsupported  distorted    a cited sentence with one meaning-changing edit: a negation, rows and
                            columns swapped, another product named, a number or quantifier changed
  unsupported  misattributed a true sentence cited to a passage from another section
  unsupported  uncited      a true sentence with no citation

The offline judge is the word-overlap stand-in; ``--llm`` also scores the configured LLM judge
(spends API quota). Reports, per judge, recall on unsupported claims (how many the gate catches),
the false-alarm rate on supported ones, and results per category.
"""

import argparse
import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from evaluation.benchmarks.run import CLICKHOUSE
from evaluation.harness import (
    RESULTS,
    Bench,
    DirectoryStore,
    bench_settings,
    caching_fetch,
    engine_from_env,
    run_folder,
    write_json,
)
from evaluation.stats import wilson_interval
from podcast_engine.common.models import Claim
from podcast_engine.common.queue import Stage
from podcast_engine.common.text import speakable_sentences
from podcast_engine.pipeline import run_inline
from podcast_engine.stages.factcheck.service import SUPPORT_THRESHOLD, judge_llm, lexical_support

# Paraphrases a reviewer would accept as supported, by the section anchor they cite.
PARAPHRASES = {
    "page-title": [
        "ClickHouse is an SQL database that stores data by column and is built for analytical "
        "workloads.",
        "You can run ClickHouse yourself as open-source software or use it as a cloud service.",
    ],
    "what-are-analytics": [
        "Analytical queries crunch huge datasets with heavy calculations such as aggregations.",
        "Transactional queries touch only a handful of rows, while analytical ones can scan "
        "billions.",
        "Real-time analytics means answering in under a second.",
    ],
    "row-oriented-vs-column-oriented-storage": [
        "A row store keeps each record's values next to each other on disk.",
        "Column stores make filters and aggregations much quicker but make fetching a single "
        "record harder.",
    ],
    "data-replication-and-integrity": [
        "Data written to one replica is copied to the other replicas in the background.",
        "Most failures are recovered from without manual work.",
    ],
    "sql-support": [
        "ClickHouse queries are written in a dialect of SQL that often matches the ANSI standard.",
        "Window functions, joins and subqueries are all available in ClickHouse SQL.",
    ],
    "approximate-calculation": [
        "ClickHouse can give up some accuracy to answer faster.",
        "Running a query on a sample of the data gives a quick approximate answer.",
    ],
}
# False statements about ClickHouse, in words the page does not use much.
FABRICATIONS = {
    "page-title": [
        "ClickHouse was first released by NASA in 1987 to track satellite telemetry.",
        "ClickHouse is a graph database designed mainly for social-network friend lookups.",
    ],
    "what-are-analytics": [
        "Most analytics queries finish in about forty minutes on a typical laptop.",
        "Analytical workloads were invented for spreadsheet macros in Lotus 1-2-3.",
    ],
    "row-oriented-vs-column-oriented-storage": [
        "ClickHouse keeps every table in a single JSON document per day.",
    ],
    "data-replication-and-integrity": [
        "ClickHouse needs a nightly manual restart to keep replicas consistent.",
        "Every replica must be approved by an administrator before it receives copies.",
    ],
    "sql-support": [
        "ClickHouse refuses any query that contains a JOIN.",
        "ClickHouse queries are written in Python rather than a query language.",
    ],
    "approximate-calculation": [
        "ClickHouse guarantees exact answers and never approximates anything.",
    ],
}
_DISTORTIONS: list[tuple[str, re.Pattern[str], str]] = [
    ("negation", re.compile(r"\b(is|are|can|must)\b"), r"\1 not"),
    ("swap rows and columns", re.compile(r"\b(row|column)(s?)\b"), ""),  # handled below
    ("other product", re.compile(r"\bClickHouse\b"), "PostgreSQL"),
    ("quantifier", re.compile(r"\b(billions|millions|most|all|many|less than one second)\b"), ""),
]
_QUANTIFIER = {
    "billions": "hundreds",
    "millions": "dozens",
    "most": "very few",
    "all": "none of the",
    "many": "rare",
    "less than one second": "about ten minutes",
}


@dataclass(frozen=True)
class LabelledClaim:
    category: str
    supported: bool
    text: str
    chunk_ids: tuple[UUID, ...]


def distort(sentence: str) -> list[tuple[str, str]]:
    """Every applicable one-edit distortion of a sentence: (kind, distorted text)."""
    out = []
    for kind, pattern, replacement in _DISTORTIONS:
        if not pattern.search(sentence):
            continue
        if kind == "swap rows and columns":
            text = pattern.sub(lambda m: ("column" if m[1] == "row" else "row") + m[2], sentence)
        elif kind == "quantifier":
            text = pattern.sub(lambda m: _QUANTIFIER[m[1]], sentence, count=1)
        else:
            text = pattern.sub(replacement, sentence, count=1)
        if text != sentence:
            out.append((kind, text))
    return out


def build_claims(bench: Bench) -> list[LabelledClaim]:
    ctx = bench.context()
    show_id = bench.create_show(**CLICKHOUSE)
    episode_id = ctx.repo.create_episode(show_id)
    run_inline(episode_id, ctx, stop_after=Stage.INDEX)
    items = ctx.repo.list_items(show_id)
    anchor_of = {i.item_id: i.url.split("#", 1)[-1] for i in items}
    chunks = ctx.repo.rank_chunks(show_id, ctx.embedder.encode(["x"])[0])
    by_anchor: dict[str, list[Any]] = defaultdict(list)
    for chunk in sorted(chunks, key=lambda c: (c.item_position, c.position)):
        by_anchor[anchor_of[chunk.item_id]].append(chunk)

    claims: list[LabelledClaim] = []
    anchors = list(by_anchor)
    for n, (anchor, section_chunks) in enumerate(by_anchor.items()):
        item = next(i for i in items if anchor_of[i.item_id] == anchor)
        first = (section_chunks[0].chunk_id,)
        for sentence in speakable_sentences(item.text):
            home = next((c for c in section_chunks if sentence in c.text), None)
            if home is None:
                continue
            cite = (home.chunk_id,)
            claims.append(LabelledClaim("verbatim", True, sentence, cite))
            claims.extend(
                LabelledClaim(f"distorted: {kind}", False, text, cite)
                for kind, text in distort(sentence)
            )
            other = by_anchor[anchors[(n + 1) % len(anchors)]][0]
            claims.append(LabelledClaim("misattributed", False, sentence, (other.chunk_id,)))
            claims.append(LabelledClaim("uncited", False, sentence, ()))
        claims.extend(
            LabelledClaim("paraphrase", True, text, first) for text in PARAPHRASES.get(anchor, [])
        )
        claims.extend(
            LabelledClaim("fabricated", False, text, first) for text in FABRICATIONS.get(anchor, [])
        )
    return claims


def judge(claims: list[LabelledClaim], bench: Bench, *, use_llm: bool) -> list[bool]:
    """The gate's verdict per claim (True = supported). Uncited claims fail before judging."""
    ctx = bench.context()
    texts = {
        c.chunk_id: c.text
        for c in ctx.repo.get_chunks({i for c in claims for i in c.chunk_ids}).values()
    }
    verdicts = [False] * len(claims)
    to_judge = [(n, c) for n, c in enumerate(claims) if c.chunk_ids]
    if use_llm:
        batch = [
            (
                Claim(claim_id=uuid4(), text=c.text, chunk_ids=c.chunk_ids),
                [texts[i] for i in c.chunk_ids],
            )
            for _, c in to_judge
        ]
        answers = judge_llm(batch, ctx)
        for k, (n, _) in enumerate(to_judge, start=1):
            verdicts[n] = answers.get(k, (False, ""))[0]
    else:
        for n, c in to_judge:
            verdicts[n] = (
                lexical_support(c.text, [texts[i] for i in c.chunk_ids]) >= SUPPORT_THRESHOLD
            )
    return verdicts


def score(claims: list[LabelledClaim], verdicts: list[bool]) -> dict[str, Any]:
    flagged_bad = sum(not v for c, v in zip(claims, verdicts, strict=True) if not c.supported)
    bad = sum(not c.supported for c in claims)
    flagged_good = sum(not v for c, v in zip(claims, verdicts, strict=True) if c.supported)
    good = sum(c.supported for c in claims)
    flagged = flagged_bad + flagged_good
    per: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for c, v in zip(claims, verdicts, strict=True):
        per[c.category][0] += int(v == c.supported)  # the gate got it right
        per[c.category][1] += 1
    return {
        "recall_unsupported": flagged_bad / bad if bad else None,
        "recall_ci95": wilson_interval(flagged_bad, bad),
        "false_alarm_rate": flagged_good / good if good else None,
        "false_alarm_ci95": wilson_interval(flagged_good, good),
        "precision_of_flags": flagged_bad / flagged if flagged else None,
        "counts": {"unsupported": bad, "supported": good, "flagged": flagged},
        "per_category": {
            k: {"correct": right, "total": total, "rate": right / total}
            for k, (right, total) in sorted(per.items())
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--llm", action="store_true", help="also score the LLM judge (spends API quota)"
    )
    args = parser.parse_args(argv)
    folder = run_folder("gate")
    engine = engine_from_env()
    bench = Bench(
        engine,
        bench_settings(engine),
        DirectoryStore(folder / "store"),
        caching_fetch(RESULTS / "pages"),
    )
    claims = build_claims(bench)
    results = {"offline-word-overlap": score(claims, judge(claims, bench, use_llm=False))}
    if args.llm:
        llm_bench = Bench(
            engine, bench_settings(engine, llm_enabled=True), bench.store, bench.fetch
        )
        name = f"{llm_bench.settings.llm_provider}:{llm_bench.settings.llm_model}"
        results[name] = score(claims, judge(claims, llm_bench, use_llm=True))
    write_json(
        folder / "results.json",
        {"claims": [c.__dict__ for c in claims], "threshold": SUPPORT_THRESHOLD, "judges": results},
    )
    lines = [
        "# Fact-check gate benchmark",
        "",
        f"{len(claims)} labelled claims from {CLICKHOUSE['sources'][0]}",
        "",
    ]
    for name, result in results.items():
        lines += [
            f"## {name}",
            "",
            f"- Catches {result['recall_unsupported']:.0%} of unsupported claims "
            f"(95% CI {result['recall_ci95'][0]:.0%}-{result['recall_ci95'][1]:.0%}, "
            f"n={result['counts']['unsupported']})",
            f"- Wrongly flags {result['false_alarm_rate']:.0%} of supported claims "
            f"(95% CI {result['false_alarm_ci95'][0]:.0%}-{result['false_alarm_ci95'][1]:.0%}, "
            f"n={result['counts']['supported']})",
            "",
            "| Category | Correct | Rate |",
            "|---|---|---|",
            *(
                f"| {k} | {v['correct']}/{v['total']} | {v['rate']:.0%} |"
                for k, v in result["per_category"].items()
            ),
            "",
        ]
    (folder / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

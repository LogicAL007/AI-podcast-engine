"""RQ1, step 1: write a script per topic in both conditions, with the same model and settings.

    python -m evaluation.rq1_claim_audit.generate [--limit N] [--topics t01,t02]

Grounded: the pipeline itself (ingest, index, retrieve and plan, script, fact-check), stopped before
voicing. The first draft (before the gate) and the final script (after it) are both kept: the
draft measures grounded *generation* (the RQ), the final measures what the system would publish.

Ungrounded: the same LLM, same segment titles, tone, hosts and length, but no passages; it writes
from its own knowledge (prompts/script_ungrounded.v1.md). Only the retrieval differs.

This calls the configured LLM (``LLM_PROVIDER``/``LLM_MODEL``, key in secrets/llm_api_key.txt) and
spends quota: about 10 calls per topic. ``--dry-run`` estimates the calls without making any.
Output: evaluation/results/rq1/<run>/scripts.jsonl, one record per topic and condition.
"""

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

from evaluation.harness import (
    RESULTS,
    ROOT,
    Bench,
    DirectoryStore,
    bench_settings,
    caching_fetch,
    engine_from_env,
    run_folder,
    write_json,
)
from podcast_engine.common.context import PipelineContext
from podcast_engine.common.models import ExpertiseLevel, Tone
from podcast_engine.common.queue import Stage
from podcast_engine.common.repository import ShowRecord
from podcast_engine.pipeline import run_inline
from podcast_engine.stages.script.service import DraftSegment, load_prompt, style_for

TOPICS = Path(__file__).with_name("topics.yaml")
UNGROUNDED_PROMPT = ("script_ungrounded", 1)
MAX_SEGMENTS = 4  # bounds cost; the same segment titles are used in both conditions
TARGET_MINUTES = 3


def load_topics(selected: set[str] | None, limit: int | None) -> list[dict[str, str]]:
    topics: list[dict[str, str]] = yaml.safe_load(TOPICS.read_text(encoding="utf-8"))["topics"]
    if selected:
        topics = [t for t in topics if t["id"] in selected]
    return topics[:limit] if limit else topics


def _segments_of(script: dict[str, Any] | None, titles: dict[int, str]) -> list[dict[str, Any]]:
    out = []
    for position, lines in sorted(
        (script or {}).get("segments", {}).items(), key=lambda kv: int(kv[0])
    ):
        out.append(
            {
                "position": int(position),
                "title": titles.get(int(position), ""),
                "lines": [
                    {
                        "speaker": line["speaker"],
                        "text": line["text"],
                        "claims": [
                            {"text": c["text"], "chunk_ids": c["chunk_ids"]} for c in line["claims"]
                        ],
                    }
                    for line in lines
                ],
            }
        )
    return out


def grounded(bench: Bench, topic: dict[str, str]) -> tuple[dict[str, Any], list[str]]:
    ctx = bench.context()
    show_id = bench.create_show(
        topic=topic["topic"],
        sources=[topic["url"]],
        max_segments=MAX_SEGMENTS,
        target_minutes=TARGET_MINUTES,
    )
    episode_id = ctx.repo.create_episode(show_id)
    route = run_inline(episode_id, ctx, stop_after=Stage.SCRIPT)
    titles = {s.position: s.title for s in ctx.repo.list_segments(episode_id)}
    draft = ctx.repo.get_episode(episode_id).script
    route += run_inline(episode_id, ctx, start=Stage.FACTCHECK, stop_before=Stage.VOICE)
    episode = ctx.repo.get_episode(episode_id)
    record = {
        "condition": "grounded",
        "episode_id": str(episode_id),
        "status": str(episode.status),
        "error": episode.error,
        "route": route,
        "draft": _segments_of(draft, titles),
        "final": _segments_of(episode.script, titles),
        "fact_check": episode.fact_check,
        "llm_usage": (episode.manifest or {}).get("llm_usage"),
    }
    return record, [titles[p] for p in sorted(titles)]


def ungrounded(ctx: PipelineContext, topic: dict[str, str], titles: list[str]) -> dict[str, Any]:
    if ctx.llm is None:
        raise RuntimeError("the ungrounded condition needs LLM_ENABLED")
    # The same show settings as the grounded condition, so style_for gives identical instructions.
    record = ShowRecord.model_validate(
        {
            "show_id": "00000000-0000-0000-0000-000000000000",
            "topic": topic["topic"],
            "tone": Tone.CASUAL,
            "target_minutes": TARGET_MINUTES,
            "host_count": 2,
            "language": "en",
            "expertise": ExpertiseLevel.BEGINNER,
            "sources": [],
            "topic_keywords": "",
            "attribution": "",
            "max_segments": MAX_SEGMENTS,
            "ranking_profile": "explainer",
        }
    )
    hosts = ctx.hosts(2)
    system = (
        load_prompt(ctx.settings.prompts_dir, *UNGROUNDED_PROMPT)
        + "\n\n"
        + style_for(record, hosts, len(titles))
    )
    usage_before = dict(ctx.llm.usage)
    segments = []
    for position, title in enumerate(titles, start=1):
        draft = ctx.llm.parse(
            system=system,
            user=(
                f"Show: {topic['topic']}\nThis is segment {position} of {len(titles)}.\n\n"
                f"Segment title: {title}"
            ),
            output_format=DraftSegment,
        )
        segments.append(
            {
                "position": position,
                "title": title,
                "lines": [
                    {
                        "speaker": line.speaker,
                        "text": line.text,
                        "claims": [{"text": line.text, "chunk_ids": []}] if line.is_claim else [],
                    }
                    for line in draft.lines
                ],
            }
        )
    usage = {k: v - usage_before.get(k, 0) for k, v in ctx.llm.usage.items()}
    return {"condition": "ungrounded", "draft": segments, "final": segments, "llm_usage": usage}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--limit", type=int, help="only the first N topics (try 1 first)")
    parser.add_argument("--topics", help="comma-separated topic ids")
    parser.add_argument("--dry-run", action="store_true", help="estimate calls; make none")
    args = parser.parse_args(argv)
    topics = load_topics(set(args.topics.split(",")) if args.topics else None, args.limit)
    if args.dry_run:
        print(
            f"{len(topics)} topics; about {len(topics) * (2 + 2 * MAX_SEGMENTS)} LLM calls "
            f"(per topic: 1 outline, up to {MAX_SEGMENTS} grounded segments, 1+ fact-check, "
            f"{MAX_SEGMENTS} ungrounded segments, plus any rewrites)"
        )
        return 0
    folder = run_folder("rq1")
    engine = engine_from_env()
    settings = bench_settings(engine, llm_enabled=True)
    bench = Bench(
        engine, settings, DirectoryStore(folder / "store"), caching_fetch(RESULTS / "pages")
    )
    meta = {
        "llm": f"{settings.llm_provider}:{settings.llm_model}",
        "seed": settings.seed,
        "max_segments": MAX_SEGMENTS,
        "target_minutes": TARGET_MINUTES,
        "prompts": {"grounded": "script.v2", "ungrounded": "script_ungrounded.v1"},
        "topics_file": str(TOPICS.relative_to(ROOT)),
    }
    write_json(folder / "meta.json", meta)
    out = folder / "scripts.jsonl"
    failures = 0
    with out.open("w", encoding="utf-8") as handle:
        for topic in topics:
            print(f"{topic['id']} {topic['topic']} ...", flush=True)
            try:
                record, titles = grounded(bench, topic)
                if not titles:
                    raise RuntimeError(f"no segments planned: {record['error']}")
                baseline = ungrounded(bench.context(), topic, titles)
            except Exception as error:  # one topic failing should not lose the others
                failures += 1
                print(f"  failed: {error}", flush=True)
                handle.write(
                    json.dumps({"topic": topic, "condition": "error", "error": str(error)}) + "\n"
                )
                continue
            for item in (record, baseline):
                handle.write(json.dumps({"topic": topic, **item}, default=str) + "\n")
            handle.flush()
    print(f"wrote {out} ({failures} topic(s) failed)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

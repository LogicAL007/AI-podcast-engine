"""Technical benchmarks from the PRD, run on one real episode and scored against its targets.

    python -m evaluation.benchmarks.run [--tts placeholder|say|chatterbox] [--llm] [--url URL]

Measures (PRD "Technical benchmarks" and the non-functional requirements):
  * generation time per stage and in total, projected to a 7-minute episode (target < 10 min)
  * cost per episode from token usage (target < USD 1; zero when offline)
  * audio: sample rate, loudness, clipping, longest silence (24 kHz+, -16 LUFS, none, < 2 s)
  * grounding: every claim cited, gate support rate (target >= 90%; automated proxy only)
  * reproducibility: the same inputs and seed rebuild the identical script (and audio)
  * dynamic refresh: one changed section re-scripts one segment and reuses the rest
  * disclosure and feed: AI label spoken first, in show notes, RSS title and description
Word error rate (a speech-to-text round trip) is a separate step, ``evaluation.benchmarks.wer``.

Writes ``evaluation/results/benchmarks/<run>/`` with results.json, report.md, the audio, notes and
feed, and the page snapshot the run used.
"""

import argparse
import hashlib
import json
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any
from uuid import UUID

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
from podcast_engine.common.audio import SR, read_wav_bytes
from podcast_engine.common.storage import feed_key
from podcast_engine.pipeline import run_inline
from podcast_engine.stages.publish.service import AI_DISCLOSURE

CLICKHOUSE: dict[str, Any] = {
    "topic": "What ClickHouse is and why it is fast for analytics",
    "sources": ["https://clickhouse.com/docs/get-started/about/intro"],
    "topic_keywords": (
        "ClickHouse column-oriented database OLAP analytics queries rows columns storage "
        "replication SQL performance approximate calculation"
    ),
    "attribution": (
        "Source material: 'What is ClickHouse?', ClickHouse Documentation "
        "(https://clickhouse.com/docs/get-started/about/intro), CC BY-NC-SA 4.0; non-commercial "
        "adaptation."
    ),
    "max_segments": 6,
    "target_minutes": 3,
}
# USD per million tokens (input, output). List prices as of October 2026; verify before reporting.
PRICES = {
    "gemini-3.8-flash": (0.75, 3.75),
    "gemini-3.7-flash": (0.75, 3.75),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
}
SEVEN_MINUTES_S = 420.0


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def build(bench: Bench, show: dict[str, Any], show_id: UUID | None = None) -> dict[str, Any]:
    """Create (or reuse) a show, run one episode end to end and collect what it produced."""
    ctx = bench.context()
    show_id = show_id or bench.create_show(**show)
    episode_id = ctx.repo.create_episode(show_id)
    started = time.perf_counter()
    writes_before = bench.store.writes
    route = run_inline(episode_id, ctx)
    seconds = time.perf_counter() - started
    episode = ctx.repo.get_episode(episode_id)
    return {
        "show_id": show_id,
        "episode_id": episode_id,
        "route": route,
        "seconds": seconds,
        "episode": episode,
        "runs": ctx.repo.list_stage_runs(episode_id),
        "claims": ctx.repo.list_claims(episode_id),
        "segments": ctx.repo.list_segments(episode_id),
        "store_writes": bench.store.writes - writes_before,
    }


def script_text(result: dict[str, Any]) -> dict[str, list[str]]:
    segments = (result["episode"].script or {}).get("segments", {})
    return {k: [line["text"] for line in v] for k, v in segments.items()}


def edit_one_section(html: str, anchor: str) -> str:
    """Add a sentence to the first paragraph after the heading ``anchor``: a changed source."""
    from lxml import html as lxml_html

    doc = lxml_html.fromstring(html)
    (heading,) = doc.xpath(f"//*[@id='{anchor}']")
    for element in heading.itersiblings():
        if element.tag == "p" or element.get("data-as") == "p":
            element.text = (element.text or "") + " This sentence was added to test refresh. "
            break
    else:
        raise ValueError(f"no paragraph follows heading #{anchor}")
    return str(lxml_html.tostring(doc, encoding="unicode"))


def check(
    name: str, target: str, measured: str, passed: bool | None, note: str = ""
) -> dict[str, Any]:
    return {"name": name, "target": target, "measured": measured, "pass": passed, "note": note}


def evaluate(
    first: dict[str, Any],
    repeat: dict[str, Any] | None,
    refresh: dict[str, Any] | None,
    store: DirectoryStore,
    settings_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    episode = first["episode"]
    assembly = episode.assembly or {}
    after = assembly.get("after", {})
    duration = float(after.get("duration_s", 0.0))
    total = sum(float(r.seconds or 0) for r in first["runs"])
    projected = total * SEVEN_MINUTES_S / duration if duration else float("inf")
    claims = first["claims"]
    supported = sum(bool(c.supported) for c in claims)
    cited = sum(bool(c.chunk_ids) for c in claims)
    history = (episode.fact_check or {}).get("history", [])
    voice_s = sum(float(r.seconds or 0) for r in first["runs"] if r.stage == "voice")

    usage = (episode.manifest or {}).get("llm_usage") or {}
    model = settings_summary["llm_model"]
    cost: float | None = 0.0
    cost_note = "offline run: no paid calls"
    if settings_summary["llm_enabled"]:
        price = PRICES.get(model)
        cost = (
            None
            if price is None
            else (
                usage.get("input_tokens", 0) * price[0] + usage.get("output_tokens", 0) * price[1]
            )
            / 1e6
        )
        cost_note = (
            f"{usage} tokens; list prices Oct 2026, verify" if price else f"no price for {model}"
        )
    if settings_summary["tts_backend"] == "gemini":
        cost_note += "; Gemini TTS not priced here"

    lines = episode.voice_lines or []
    notes = store.get(episode.notes_key).decode() if episode.notes_key else ""
    import feedparser

    feed = feedparser.parse(store.get(feed_key(first["show_id"])))
    entry = feed.entries[0] if feed.entries else None
    voices = (episode.manifest or {}).get("voices", {})

    results = [
        check(
            "End-to-end status",
            "published",
            str(episode.status),
            episode.status == "published",
            f"route {' -> '.join(first['route'])}",
        ),
        check(
            "Generation time, 7-minute episode",
            "< 600 s",
            f"{total:.1f} s for {duration / 60:.1f} min of audio; "
            f"about {projected:.0f} s for 7 min",
            projected < 600,
            f"projected linearly; voice is {voice_s / max(total, 1e-9):.0%} of the time",
        ),
        check(
            "Episode length",
            "5 to 10 min",
            f"{duration / 60:.1f} min",
            5 <= duration / 60 <= 10,
            "length follows the source page and MAX_SEGMENTS",
        ),
        check(
            "Cost per episode",
            "< USD 1",
            "unknown" if cost is None else f"USD {cost:.4f}",
            None if cost is None else cost < 1.0,
            cost_note,
        ),
        check(
            "Sample rate",
            ">= 24000 Hz",
            f"{after.get('sample_rate_hz')} Hz",
            after.get("sample_rate_hz", 0) >= 24_000,
        ),
        check(
            "Loudness",
            "-16 LUFS +/- 1",
            f"{after.get('lufs', 0):.2f} LUFS",
            abs(after.get("lufs", 0) + 16) <= 1,
        ),
        check(
            "Clipping",
            "none",
            f"{after.get('clipped_samples')} samples, peak {after.get('peak', 0):.2f}",
            after.get("clipped_samples") == 0,
        ),
        check(
            "Longest silence",
            "< 2 s",
            f"{after.get('longest_silence_s', 0):.2f} s",
            after.get("longest_silence_s", 99) < 2,
        ),
        check(
            "Claims cited (FR5)",
            "100%",
            f"{cited}/{len(claims)}",
            bool(claims) and cited == len(claims),
        ),
        check(
            "Claims supported after the gate",
            ">= 90%",
            f"{supported}/{len(claims)} ({supported / max(len(claims), 1):.0%})",
            bool(claims) and supported / len(claims) >= 0.9,
            f"judge: {(episode.fact_check or {}).get('judge')}; "
            "automated proxy, not the manual audit",
        ),
        check("Gate passes", "recorded", json.dumps(history), bool(history)),
        check(
            "Distinct voice per host (FR6)",
            "one per host",
            ", ".join(f"{h}={v['voice_id']}" for h, v in voices.items()),
            len({v["voice_id"] for v in voices.values()}) == len(voices) >= 2,
        ),
        check(
            "Intro, outro, transitions (FR6)",
            "present",
            f"intro {assembly.get('intro')}, outro {assembly.get('outro')}, "
            f"{len(assembly.get('chapters', []))} chapters",
            bool(assembly.get("chapters")),
        ),
        check(
            "AI disclosure spoken first (FR13)",
            "first line",
            lines[0]["text"] if lines else "none",
            bool(lines) and lines[0]["text"] == AI_DISCLOSURE,
        ),
        check(
            "AI disclosure in notes and RSS (FR13)",
            "notes, title, description",
            f"notes {notes.startswith(AI_DISCLOSURE)}, "
            f"title {'AI-generated' in (entry.title if entry else '')}, "
            f"description {AI_DISCLOSURE in (entry.summary if entry else '')}",
            notes.startswith(AI_DISCLOSURE)
            and entry is not None
            and "AI-generated" in entry.title
            and AI_DISCLOSURE in entry.summary,
        ),
        check(
            "RSS feed parses with an enclosure (FR10)",
            ">= 1 entry with audio",
            f"{len(feed.entries)} entries",
            entry is not None and bool(entry.enclosures),
        ),
        check(
            "Versions logged per episode (transparency)",
            "model, prompts, seed",
            ", ".join(f"{r.stage}:{r.model}" for r in first["runs"]),
            all(r.seed is not None for r in first["runs"])
            and "prompt_versions" in (episode.manifest or {}),
        ),
    ]
    if repeat is not None:
        same_script = script_text(first) == script_text(repeat)
        audio_first = _sha(store.get(first["episode"].audio_key))
        audio_repeat = _sha(store.get(repeat["episode"].audio_key))
        results.append(
            check(
                "Reproducible from inputs and seed",
                "identical script",
                f"script identical: {same_script}; audio identical: {audio_first == audio_repeat}",
                same_script,
                "fresh show, same page snapshot and seed",
            )
        )
    if refresh is not None:
        r_episode = refresh["episode"]
        changed = set(r_episode.changed_item_ids or [])
        affected = sorted(
            s.position for s in refresh["segments"] if set(s.source_item_ids) & changed
        )
        old, new = script_text(first), script_text(refresh)
        reused_same = all(new[p] == old.get(p) for p in new if int(p) not in affected)
        r_lines = len(r_episode.voice_lines or [])
        new_clips = max(refresh["store_writes"] - 3, 0)  # minus the episode audio, notes and feed
        results.append(
            check(
                "Incremental refresh (FR8)",
                "only changed segments regenerated",
                f"{len(changed)} changed section(s) -> segment(s) {affected} re-scripted; "
                f"{new_clips} of {r_lines} lines synthesised; {refresh['seconds']:.1f} s vs "
                f"{first['seconds']:.1f} s first build",
                r_episode.status == "published" and len(affected) == 1 and reused_same,
                "unchanged segments' text identical" if reused_same else "a reused segment changed",
            )
        )
    return results


def report_markdown(results: list[dict[str, Any]], meta: dict[str, Any]) -> str:
    rows = "\n".join(
        f"| {r['name']} | {r['target']} | {r['measured']} | "
        f"{'n/a' if r['pass'] is None else ('PASS' if r['pass'] else '**FAIL**')} | {r['note']} |"
        for r in results
    )
    return (
        f"# Technical benchmarks\n\n{json.dumps(meta, default=str)}\n\n"
        "| Check | Target | Measured | Result | Note |\n|---|---|---|---|---|\n" + rows + "\n"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--tts", default="placeholder", choices=["placeholder", "say", "chatterbox", "gemini"]
    )
    parser.add_argument(
        "--llm", action="store_true", help="LLM writes and judges (spends API quota)"
    )
    parser.add_argument("--url", help="a different source page (default: the ClickHouse intro)")
    parser.add_argument("--no-repeat", action="store_true", help="skip the reproducibility rebuild")
    parser.add_argument("--no-refresh", action="store_true", help="skip the incremental refresh")
    args = parser.parse_args(argv)

    show = dict(CLICKHOUSE)
    if args.url:
        show.update(sources=[args.url], topic_keywords="", attribution="")
    folder = run_folder("benchmarks")
    engine = engine_from_env()
    settings = bench_settings(engine, tts_backend=args.tts, llm_enabled=args.llm)
    pages = RESULTS / "pages"  # shared snapshot: every run and condition reads the same HTML
    fetch: Callable[[str], str] = caching_fetch(pages)
    store = DirectoryStore(folder / "store")
    bench = Bench(engine, settings, store, fetch)

    print(f"first build ({args.tts}, {'LLM' if args.llm else 'offline'}) ...", flush=True)
    first = build(bench, show)
    repeat = None
    if not args.no_repeat and first["episode"].status == "published":
        print("reproducibility rebuild ...", flush=True)
        repeat = build(
            Bench(engine, settings, DirectoryStore(folder / "store_repeat"), fetch), show
        )
        store_repeat = DirectoryStore(folder / "store_repeat")
        # Both audio files are compared from one store.
        store.put(
            repeat["episode"].audio_key, store_repeat.get(repeat["episode"].audio_key), "audio/wav"
        )
    refresh = None
    if (
        not args.no_refresh
        and first["episode"].status == "published"
        and len(first["segments"]) > 1
    ):
        target = first["segments"][1]
        item_url = next(
            i.url
            for i in bench.context().repo.list_items(first["show_id"])
            if i.item_id in target.source_item_ids
        )
        anchor = item_url.split("#", 1)[1] if "#" in item_url else ""
        if anchor:
            print(f"refresh after editing section #{anchor} ...", flush=True)
            edited = edit_one_section(fetch(show["sources"][0]), anchor)
            refresh = build(
                Bench(engine, settings, store, lambda _url: edited), show, first["show_id"]
            )

    meta = {
        "tts_backend": settings.tts_backend,
        "llm_enabled": settings.llm_enabled,
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "embedding_model": settings.embedding_model,
        "seed": settings.seed,
        "source": show["sources"],
        "episode_id": first["episode_id"],
    }
    results = evaluate(first, repeat, refresh, store, meta)
    audio = store.get(first["episode"].audio_key) if first["episode"].audio_key else b""
    if audio:
        (folder / "episode.wav").write_bytes(audio)
        meta["episode_seconds"] = len(read_wav_bytes(audio)) / SR
    write_json(
        folder / "results.json",
        {
            "meta": meta,
            "checks": results,
            "stage_seconds": {r.stage: float(r.seconds or 0) for r in first["runs"]},
            "voice_lines": first["episode"].voice_lines,
            "store": str(store.root),
        },
    )
    (folder / "report.md").write_text(report_markdown(results, meta), encoding="utf-8")
    print(report_markdown(results, meta))
    print(
        f"wrote {folder.relative_to(Path.cwd()) if folder.is_relative_to(Path.cwd()) else folder}"
    )
    return 0 if all(r["pass"] is not False for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

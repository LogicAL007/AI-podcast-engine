"""Word error rate of a speech-to-text round trip: a rough intelligibility check (PRD benchmarks).

    .venv-cloning/bin/python -m evaluation.benchmarks.wer evaluation/results/benchmarks/<run>

Transcribes each voiced line of a benchmark run with a local Whisper model (transformers; the
model downloads once from Hugging Face, no API key) and compares it with the script text. Needs
torch and transformers, which the cloning environment has. Placeholder tones are not speech, so
runs made with ``--tts placeholder`` are refused.
"""

import argparse
import json
import re
import wave
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

_NUMBER_WORDS = {
    "0": "zero", "1": "one", "2": "two", "3": "three", "4": "four", "5": "five",
    "6": "six", "7": "seven", "8": "eight", "9": "nine", "10": "ten",
}  # fmt: skip


def normalise(text: str) -> list[str]:
    """Lower case, no punctuation, small numbers spelled out: only real word errors count."""
    words = re.sub(r"[^a-z0-9' ]+", " ", text.lower().replace("-", " ")).split()
    return [_NUMBER_WORDS.get(w, w) for w in words]


def word_errors(reference: list[str], hypothesis: list[str]) -> int:
    """Levenshtein distance over words: substitutions, deletions and insertions."""
    previous = list(range(len(hypothesis) + 1))
    for i, ref in enumerate(reference, start=1):
        current = [i]
        for j, hyp in enumerate(hypothesis, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ref != hyp)))
        previous = current
    return previous[-1]


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as handle:
        rate = handle.getframerate()
        frames = handle.readframes(handle.getnframes())
    return np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0, rate


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("run", type=Path, help="a folder written by evaluation.benchmarks.run")
    parser.add_argument("--model", default="openai/whisper-base.en")
    args = parser.parse_args(argv)

    results = json.loads((args.run / "results.json").read_text(encoding="utf-8"))
    if results["meta"]["tts_backend"] == "placeholder":
        parser.error(
            "this run used placeholder tones, which are not speech; "
            "rerun with --tts say or chatterbox"
        )
    store = Path(results["store"])

    import torch
    from transformers import pipeline

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    transcribe = pipeline("automatic-speech-recognition", model=args.model, device=device)

    rows: list[dict[str, Any]] = []
    total_errors = total_words = 0
    for line in results["voice_lines"]:
        samples, rate = read_wav(store / line["key"])
        heard = str(transcribe({"raw": samples, "sampling_rate": rate})["text"]).strip()
        reference, hypothesis = normalise(line["text"]), normalise(heard)
        errors = word_errors(reference, hypothesis)
        total_errors += errors
        total_words += len(reference)
        rows.append(
            {"speaker": line["speaker"], "text": line["text"], "heard": heard,
             "errors": errors, "words": len(reference)}
        )  # fmt: skip
    wer = total_errors / max(total_words, 1)
    worst = sorted(rows, key=lambda r: r["errors"] / max(r["words"], 1), reverse=True)[:5]
    by_speaker = {
        s: sum(r["errors"] for r in rows if r["speaker"] == s)
        / max(sum(r["words"] for r in rows if r["speaker"] == s), 1)
        for s in sorted({r["speaker"] for r in rows})
    }
    summary = {
        "model": args.model, "tts_backend": results["meta"]["tts_backend"], "lines": len(rows),
        "words": total_words, "wer": wer, "wer_by_speaker": by_speaker,
    }  # fmt: skip
    (args.run / "wer.json").write_text(
        json.dumps({**summary, "lines": rows}, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    print("highest-error lines:")
    for r in worst:
        print(
            f"  [{r['errors']}/{r['words']}] said: {r['text']!r}\n          heard: {r['heard']!r}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

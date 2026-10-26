"""Assemble: stitch audio together and normalise loudness."""

from pathlib import Path
from typing import Any
from uuid import UUID

import numpy as np

from podcast_engine.common.audio import (
    SILENCE_LIMIT_S,
    SR,
    audio_report,
    chime,
    normalise,
    read_wav_bytes,
    silence,
    wav_bytes,
)
from podcast_engine.common.context import PipelineContext, get_context
from podcast_engine.common.logging import get_logger
from podcast_engine.common.queue import Stage

TARGET_LUFS = -16.0
LOUDNESS_TOLERANCE_LU = 1.0
MIN_SAMPLE_RATE_HZ = 24_000

log = get_logger("assemble")


def needs_normalisation(measured_lufs: float) -> bool:
    """True when integrated loudness is outside the NFR target of about -16 LUFS."""
    return abs(measured_lufs - TARGET_LUFS) > LOUDNESS_TOLERANCE_LU


def episode_audio_key(episode_id: UUID) -> str:
    return f"episodes/{episode_id}.wav"


def load_asset(assets_dir: Path, name: str, fallback: np.ndarray) -> tuple[np.ndarray, str]:
    """``assets/audio/<name>.wav`` (24 kHz mono 16-bit) if present, else the synthetic chime."""
    path = assets_dir / "audio" / f"{name}.wav"
    if path.exists():
        try:
            return read_wav_bytes(path.read_bytes(), name=path.name), f"assets/audio/{name}.wav"
        except ValueError as error:
            log.warning("asset_ignored", reason=str(error))
    return fallback, "synthetic chime"


def mix(
    lines: list[dict[str, Any]],
    clips: list[np.ndarray | None],
    titles: dict[int, str],
    *,
    intro: np.ndarray,
    outro: np.ndarray,
    transition: np.ndarray,
) -> tuple[np.ndarray, list[tuple[float, str]]]:
    """Intro, lines with pauses, transitions between segments, outro. Returns audio and chapters.

    A line without a clip was voiced together with the lines before it, in their clip.
    """
    parts: list[np.ndarray] = []
    chapters: list[tuple[float, str]] = []
    cursor = 0.0

    def add(signal: np.ndarray) -> None:
        nonlocal cursor
        parts.append(signal)
        cursor += len(signal) / SR

    add(intro)
    add(silence(0.4))
    current: int | None = None
    previous_kind = "disclosure"
    for line, clip in zip(lines, clips, strict=True):
        if line["kind"] == "segment" and line["position"] != current:
            if current is not None:
                add(silence(0.3))
                add(transition)
            add(silence(0.5))
            chapters.append((cursor, titles[line["position"]]))
            current = line["position"]
        elif line["kind"] == "closing" and previous_kind == "segment":
            add(silence(0.3))
            add(transition)
            add(silence(0.5))
        previous_kind = line["kind"]
        if clip is None:
            continue
        add(clip)
        add(silence(0.7 if line["kind"] == "disclosure" else 0.25))
    add(silence(0.3))
    add(outro)
    return np.concatenate(parts), chapters


def assemble_episode(episode_id: UUID, ctx: PipelineContext | None = None) -> Stage | None:
    """FR6: add intro, outro and transitions, normalise loudness, run silence/clipping checks."""
    ctx = ctx or get_context()
    episode = ctx.repo.get_episode(episode_id)
    lines = episode.voice_lines or []
    if not lines:
        raise ValueError("There are no voiced lines to assemble.")
    clips = [
        read_wav_bytes(ctx.store.get(line["key"]), name=line["key"]) if line["key"] else None
        for line in lines
    ]
    titles = {s.position: s.title for s in ctx.repo.list_segments(episode_id)}
    intro, intro_source = load_asset(
        ctx.settings.assets_dir, "intro", chime((523.25, 659.25, 783.99, 1046.5), 2.4)
    )
    outro, outro_source = load_asset(
        ctx.settings.assets_dir, "outro", chime((1046.5, 783.99, 659.25, 523.25), 2.4)
    )
    raw, chapters = mix(
        lines, clips, titles, intro=intro, outro=outro, transition=chime((880.0, 1174.66), 0.5)
    )
    final = normalise(raw, TARGET_LUFS)
    after = audio_report(final)
    checks = {
        "sample_rate": after["sample_rate_hz"] >= MIN_SAMPLE_RATE_HZ,
        "loudness": not needs_normalisation(after["lufs"]),
        "clipping": after["clipped_samples"] == 0,
        "silence": after["longest_silence_s"] < SILENCE_LIMIT_S,
    }
    key = episode_audio_key(episode_id)
    data = wav_bytes(final)
    ctx.store.put(key, data, "audio/wav")
    assembly = {
        "before": audio_report(raw),
        "after": after,
        "checks": checks,
        "checks_pass": all(checks.values()),
        "chapters": chapters,
        "audio_bytes": len(data),
        "intro": intro_source,
        "outro": outro_source,
    }
    ctx.repo.update_episode(episode_id, assembly=assembly, audio_key=key)
    log.info(
        "episode_assembled",
        episode_id=str(episode_id),
        seconds=round(after["duration_s"], 1),
        lufs=round(after["lufs"], 1),
        checks_pass=assembly["checks_pass"],
    )
    return Stage.PUBLISH

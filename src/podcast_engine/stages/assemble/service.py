"""Assemble: stitch audio together and normalise loudness."""

import random
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
from podcast_engine.stages.assemble.music import (
    SPEECH_RMS,
    add_bed,
    apply_host_effects,
    load_show_tracks,
)

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


EDGE_DB = -40.0  # quieter than this, relative to the clip's peak, counts as silence at its edges
EDGE_PAD_S = 0.04  # kept around the speech after trimming, so words are not clipped


def tighten(clip: np.ndarray) -> np.ndarray:
    """The clip without the silence a voice model leaves before and after the words, at the
    common speech level. Gaps between lines then come only from ``pause_after``."""
    if not clip.size:
        return clip
    peak = float(np.abs(clip).max())
    if peak == 0.0:
        return clip
    loud = np.flatnonzero(np.abs(clip) > peak * 10 ** (EDGE_DB / 20))
    pad = int(SR * EDGE_PAD_S)
    words = clip[max(loud[0] - pad, 0) : loud[-1] + pad + 1]
    rms = float(np.sqrt(np.mean(words**2)))
    gain = min(SPEECH_RMS / rms, 0.95 / peak) if rms > 0 else 1.0
    return (words * gain).astype(np.float32)


def pause_after(line: dict[str, Any], following: dict[str, Any] | None) -> float:
    """Seconds of quiet between one line and the next, the way people take turns.

    A quick reaction or an answer comes in fast, the same speaker carrying on pauses briefly, and
    a fact gets a moment to land. Lines voiced together in one clip are paced by the voice itself.
    """
    if line["kind"] == "disclosure":
        return 0.7
    if following is None or following["kind"] != line["kind"]:
        return 0.25  # the part ends; the transition (or the outro) adds its own pause
    if following["speaker"] == line["speaker"]:
        return 0.2
    if len(following["text"].split()) <= 4 or line["text"].rstrip().endswith("?"):
        return 0.18  # "Right." or the answer to a question: no dead air before it
    if line.get("claim"):
        return 0.45
    if line.get("delivery") == "thoughtful" or following.get("delivery") == "serious":
        return 0.4
    return 0.28


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

    A line without a clip was voiced together with the lines before it, in their clip. Each
    clip is trimmed and levelled (``tighten``), and the pause after it fits the turn
    (``pause_after``).
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
    for index, (line, clip) in enumerate(zip(lines, clips, strict=True)):
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
        add(tighten(clip))
        # The clip ends with the last line voiced in it; the pause depends on who speaks next.
        end = next((n for n in range(index + 1, len(lines)) if clips[n] is not None), len(lines))
        add(silence(pause_after(lines[end - 1], lines[end] if end < len(lines) else None)))
    add(silence(0.3))
    add(outro)
    return np.concatenate(parts), chapters


ROOM_TONE_DBFS = -58.0  # a quiet room under everything, in place of digital silence
PAUSE_JITTER = (0.8, 1.25)  # each pause from pause_after, stretched or shortened at random
OVERLAP_S = (0.08, 0.2)  # a quick reply starts this long before the line it answers ends


def room_tone(samples: int, rng: np.random.Generator) -> np.ndarray:
    """Soft, warm background noise at ROOM_TONE_DBFS: white noise smoothed so it has no hiss."""
    white = rng.standard_normal(samples).astype(np.float32)
    warm = np.convolve(white, np.ones(48, dtype=np.float32) / 48, mode="same")  # about 2 ms
    rms = float(np.sqrt(np.mean(warm**2))) or 1.0
    return (warm * (10 ** (ROOM_TONE_DBFS / 20) / rms)).astype(np.float32)


def is_quick_reply(line: dict[str, Any], previous: dict[str, Any] | None) -> bool:
    """A short answer from the other host ("Right.", "Wait, really?"), which people start before
    the speaker has quite finished."""
    return (
        previous is not None
        and line["kind"] == previous["kind"] == "segment"
        and line["speaker"] != previous["speaker"]
        and len(line["text"].split()) <= 4
    )


def mix_natural(
    lines: list[dict[str, Any]],
    clips: list[np.ndarray | None],
    titles: dict[int, str],
    *,
    intro: np.ndarray,
    outro: np.ndarray,
    transition: np.ndarray,
    seed: int = 0,
) -> tuple[np.ndarray, list[tuple[float, str]]]:
    """``mix``, post-produced to sound like people in one room: quiet room tone instead of
    digital silence between lines, each pause varied a little (a fixed gap after every line is a
    giveaway of synthetic speech), and quick replies overlapping the end of the line they answer.
    The same lines, levels and order as ``mix``; the seed makes it reproducible."""
    rng = random.Random(seed)  # noqa: S311 - timing variation, not security
    placed: list[tuple[int, np.ndarray]] = []
    chapters: list[tuple[float, str]] = []

    def at(seconds: float) -> int:
        return int(seconds * SR)

    placed.append((0, intro))
    cursor = len(intro) + at(0.4)  # where the next line may start
    current: int | None = None
    previous_kind = "disclosure"
    last: tuple[int, int, dict[str, Any]] | None = None  # (start, length, line) of the last clip
    for index, (line, clip) in enumerate(zip(lines, clips, strict=True)):
        if line["kind"] == "segment" and line["position"] != current:
            if current is not None:
                placed.append((cursor + at(0.3), transition))
                cursor += at(0.3) + len(transition)
            cursor += at(0.5)
            chapters.append((cursor / SR, titles[line["position"]]))
            current = line["position"]
        elif line["kind"] == "closing" and previous_kind == "segment":
            placed.append((cursor + at(0.3), transition))
            cursor += at(0.3) + len(transition) + at(0.5)
        previous_kind = line["kind"]
        if clip is None:
            continue
        speech = tighten(clip)
        start = cursor
        if last is not None and is_quick_reply(line, last[2]):
            last_start, last_length, _ = last
            start = max(
                last_start + last_length // 2,
                last_start + last_length - at(rng.uniform(*OVERLAP_S)),
            )
        placed.append((start, speech))
        # The clip ends with the last line voiced in it; the pause depends on who speaks next.
        end = next((n for n in range(index + 1, len(lines)) if clips[n] is not None), len(lines))
        gap = pause_after(lines[end - 1], lines[end] if end < len(lines) else None)
        cursor = start + len(speech) + at(gap * rng.uniform(*PAUSE_JITTER))
        last = (start, len(speech), lines[end - 1])
    placed.append((cursor + at(0.3), outro))
    out = np.zeros(max(start + len(signal) for start, signal in placed), dtype=np.float32)
    for start, signal in placed:
        out[start : start + len(signal)] += signal
    out += room_tone(len(out), np.random.default_rng(seed))
    return np.clip(out, -1.0, 1.0), chapters


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
    show = ctx.repo.get_show(episode.show_id)
    clips, effects = apply_host_effects(lines, clips, show.host_effects)
    uploaded = {t for t in show.music.track_ids() if not t.startswith("builtin:")}
    tracks = load_show_tracks(show.music, ctx.repo.get_music_tracks(uploaded), ctx.store)
    # The show's own music first, then a deployment-wide asset, then the synthetic chime.
    intro, intro_source = (
        (tracks.intro, f"music:{show.music.intro}")
        if tracks.intro is not None
        else load_asset(
            ctx.settings.assets_dir, "intro", chime((523.25, 659.25, 783.99, 1046.5), 2.4)
        )
    )
    outro, outro_source = (
        (tracks.outro, f"music:{show.music.outro}")
        if tracks.outro is not None
        else load_asset(
            ctx.settings.assets_dir, "outro", chime((1046.5, 783.99, 659.25, 523.25), 2.4)
        )
    )
    # Between segments: the show's sting if it has one, otherwise nothing but the pause around it.
    # The synthetic two-note chime made the conversation sound like separate clips.
    transition = tracks.sting if tracks.sting is not None else np.zeros(0, dtype=np.float32)
    combine = mix_natural if ctx.settings.assembly_style == "natural" else mix
    raw, chapters = combine(lines, clips, titles, intro=intro, outro=outro, transition=transition)
    if tracks.bed is not None:
        raw = add_bed(
            raw,
            tracks.bed,
            start=len(intro),
            end=len(raw) - len(outro),
            level_db=show.music.bed_level_db,
            seamless=tracks.bed_seamless,
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
        "between_segments": f"music:{show.music.sting}" if tracks.sting is not None else "pause",
        "effects": effects,
        "music": {**tracks.report, "credits": tracks.credits},
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

"""Music and voice effects for the assemble stage.

- Host effects (``shows.host_effects``) are applied to each clip before it is levelled and mixed.
- The show's intro, outro and sting (``shows.music``) take the place of the default chimes, cut to
  length and brought to a level just under the voices.
- The bed loops under the conversation and ducks while people talk: it sits ``bed_level_db``
  below the voices during speech and comes up in longer pauses and between segments.

Everything works on 24 kHz mono float32, after the voices are mixed and before loudness is
normalised, so the -16 LUFS target and the silence and clipping checks apply to the full mix.
"""

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from podcast_engine.common.audio import SR, read_wav_bytes
from podcast_engine.common.logging import get_logger
from podcast_engine.common.music import BUILTIN_TRACKS, ShowMusic, builtin_audio, is_builtin
from podcast_engine.common.repository import MusicTrackRecord
from podcast_engine.common.storage import ObjectStore
from podcast_engine.common.voice_fx import VoiceEffects, apply_effects

log = get_logger("assemble")

SPEECH_RMS = 0.08  # the level voices are mixed at (service.tighten)
SLOT_RMS = SPEECH_RMS * 0.8  # intro, outro and sting: about 2 dB under the voices
SLOT_SECONDS = {"intro": 10.0, "outro": 15.0, "sting": 4.0}
SLOT_FADE_OUT_S = {"intro": 1.5, "outro": 2.0, "sting": 0.3}
OUTRO_FADE_IN_S = 0.3

FRAME_S = 0.02  # speech is detected in frames this long
ACTIVE_RMS = 0.01  # a frame louder than this has someone talking (room tone is ~0.0013)
GAP_S = 0.6  # a pause at least this long lets the bed come up
GAP_LIFT_DB = 8.0
ATTACK_S = 0.06  # the bed ducks this fast when someone starts talking
RELEASE_S = 0.5  # and comes back up this slowly
BED_FADE_S = 1.0
LOOP_CROSSFADE_S = 1.0  # an uploaded bed is joined to itself with this crossfade


# ---- voice effects ---------------------------------------------------------------------------


def apply_host_effects(
    lines: list[dict[str, Any]],
    clips: list[np.ndarray | None],
    host_effects: dict[str, VoiceEffects],
) -> tuple[list[np.ndarray | None], dict[str, Any]]:
    """Each clip processed with its speaker's effects, and a report of what was done.

    A clip may hold several lines (voiced together; the lines after it have no clip of their
    own). It is processed only when every speaker in it has the same effects, since one clip
    cannot be split by speaker.
    """
    active = {host: fx for host, fx in host_effects.items() if fx.active}
    report: dict[str, Any] = {
        "hosts": {host: fx.model_dump() for host, fx in active.items()},
        "clips": 0,
        "skipped_mixed_clips": 0,
    }
    if not active:
        return clips, report
    out: list[np.ndarray | None] = list(clips)
    for index, clip in enumerate(clips):
        if clip is None:
            continue
        end = next((n for n in range(index + 1, len(lines)) if clips[n] is not None), len(lines))
        speakers = {lines[n]["speaker"] for n in range(index, end)}
        chosen = {active.get(speaker) for speaker in speakers}
        if len(chosen) > 1:
            report["skipped_mixed_clips"] += 1
            continue
        fx = chosen.pop()
        if fx is not None:
            out[index] = apply_effects(clip, fx)
            report["clips"] += 1
    return out, report


# ---- tracks ----------------------------------------------------------------------------------


@dataclass
class ShowTracks:
    """The show's music, loaded and fitted. A slot is None when the default should play."""

    intro: np.ndarray | None = None
    outro: np.ndarray | None = None
    sting: np.ndarray | None = None
    bed: np.ndarray | None = None
    bed_seamless: bool = False
    report: dict[str, Any] = field(default_factory=dict)
    credits: list[str] = field(default_factory=list)


def _level(audio: np.ndarray, rms: float) -> np.ndarray:
    current = float(np.sqrt(np.mean(audio**2))) if len(audio) else 0.0
    if current == 0.0:
        return audio.astype(np.float32)
    out = audio * (rms / current)
    peak = float(np.max(np.abs(out)))
    if peak > 0.95:
        out *= 0.95 / peak
    return out.astype(np.float32)


def fit_slot(audio: np.ndarray, slot: str) -> np.ndarray:
    """An intro, outro or sting cut to its longest length, faded, at the slot level."""
    longest = int(SLOT_SECONDS[slot] * SR)
    out = np.array(audio[:longest], dtype=np.float32)
    fade = min(int(SLOT_FADE_OUT_S[slot] * SR), len(out) // 2)
    if len(audio) > longest or slot != "intro":
        out[len(out) - fade :] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)
    else:
        tail = min(int(0.05 * SR), len(out))  # a built-in intro ends on its own; avoid a click
        out[len(out) - tail :] *= np.linspace(1.0, 0.0, tail, dtype=np.float32)
    if slot == "outro":
        rise = min(int(OUTRO_FADE_IN_S * SR), len(out) // 2)
        out[:rise] *= np.linspace(0.0, 1.0, rise, dtype=np.float32)
    return _level(out, SLOT_RMS)


def load_show_tracks(
    music: ShowMusic, uploaded: dict[str, MusicTrackRecord], store: ObjectStore
) -> ShowTracks:
    """The show's tracks, built-in or uploaded. A track that is gone (deleted since it was
    chosen) or unreadable is reported and left out, so the default plays in its place."""
    tracks = ShowTracks()
    for slot in ("intro", "outro", "sting", "bed"):
        track_id: str | None = getattr(music, slot)
        if not track_id:
            continue
        audio: np.ndarray | None = None
        label = track_id
        seamless = False
        try:
            if is_builtin(track_id):
                audio = np.array(builtin_audio(track_id), dtype=np.float32)
                label = BUILTIN_TRACKS[track_id].name
                seamless = BUILTIN_TRACKS[track_id].seamless
            elif track_id in uploaded:
                record = uploaded[track_id]
                audio = read_wav_bytes(store.get(record.object_key), name=record.object_key)
                label = record.name
                if record.credit and record.credit not in tracks.credits:
                    tracks.credits.append(record.credit)
        except (KeyError, ValueError, OSError) as error:
            log.warning("music_unreadable", slot=slot, track=track_id, reason=str(error))
            audio = None
        if audio is None or not len(audio):
            tracks.report[slot] = {"track": track_id, "missing": True}
            log.warning("music_missing", slot=slot, track=track_id)
            continue
        tracks.report[slot] = {"track": track_id, "name": label}
        if slot == "bed":
            tracks.bed, tracks.bed_seamless = audio, seamless
        else:
            setattr(tracks, slot, fit_slot(audio, slot))
    if tracks.bed is not None:
        tracks.report["bed_level_db"] = music.bed_level_db
    return tracks


# ---- the bed ---------------------------------------------------------------------------------


def loop_to(bed: np.ndarray, samples: int, *, seamless: bool) -> np.ndarray:
    """``bed`` repeated to ``samples`` long. A track made to loop is tiled end to start; any
    other is joined to itself with an equal-power crossfade, so the seam is not heard."""
    if len(bed) >= samples:
        return np.array(bed[:samples], dtype=np.float32)
    if seamless:
        return np.tile(bed, -(-samples // len(bed)))[:samples].astype(np.float32)
    overlap = min(int(LOOP_CROSSFADE_S * SR), len(bed) // 4)
    fade_in = np.sqrt(np.linspace(0.0, 1.0, overlap, dtype=np.float32))
    fade_out = np.sqrt(np.linspace(1.0, 0.0, overlap, dtype=np.float32))
    pieces = [np.array(bed, dtype=np.float32)]
    total = len(bed)
    while total < samples:
        pieces[-1][-overlap:] = pieces[-1][-overlap:] * fade_out + bed[:overlap] * fade_in
        pieces.append(np.array(bed[overlap:], dtype=np.float32))
        total += len(bed) - overlap
    return np.concatenate(pieces)[:samples]


def duck_gains(region: np.ndarray, level_db: float) -> np.ndarray:
    """A per-sample gain for the bed under ``region`` of the mix: ``level_db`` while people talk
    (speech within GAP_S / 2 either side), GAP_LIFT_DB more in longer pauses. It ducks quickly
    and recovers slowly, and since it looks a little ahead, it is already down when a line
    starts."""
    frame = int(FRAME_S * SR)
    count = max(-(-len(region) // frame), 1)
    padded = np.zeros(count * frame, dtype=np.float32)
    padded[: len(region)] = region
    rms = np.sqrt(np.mean(padded.reshape(count, frame) ** 2, axis=1))
    talking = rms > ACTIVE_RMS
    reach = int(GAP_S / 2 / FRAME_S)
    near = np.convolve(talking.astype(np.float32), np.ones(2 * reach + 1), mode="same") > 0
    target = np.where(near, level_db, level_db + GAP_LIFT_DB)
    down = 1 - np.exp(-FRAME_S / ATTACK_S)
    up = 1 - np.exp(-FRAME_S / RELEASE_S)
    smooth = np.empty(count)
    current = float(target[0])
    for n, wanted in enumerate(target):
        current += (down if wanted < current else up) * (wanted - current)
        smooth[n] = current
    centres = (np.arange(count) + 0.5) * frame
    db = np.interp(np.arange(len(region)), centres, smooth)
    return (10 ** (db / 20)).astype(np.float32)


def add_bed(
    mix: np.ndarray,
    bed: np.ndarray,
    *,
    start: int,
    end: int,
    level_db: float,
    seamless: bool,
) -> np.ndarray:
    """``mix`` with ``bed`` under it from sample ``start`` to ``end``, ducked under speech and
    faded in and out."""
    start, end = max(start, 0), min(end, len(mix))
    if end - start < SR:  # under a second: nothing to put a bed under
        return mix
    under = _level(loop_to(bed, end - start, seamless=seamless), SPEECH_RMS)
    under *= duck_gains(mix[start:end], level_db)
    fade = min(int(BED_FADE_S * SR), len(under) // 2)
    under[:fade] *= np.linspace(0.0, 1.0, fade, dtype=np.float32)
    under[len(under) - fade :] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)
    out = mix.astype(np.float32, copy=True)
    out[start:end] += under
    return out

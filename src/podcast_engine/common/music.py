"""Music for episodes: a show's music settings, and the built-in tracks, made in code.

Built-in tracks are synthesised with numpy from a fixed seed, so the API (which plays them in the
web app) and the assemble worker (which mixes them into episodes) make the same audio, and no
music files live in the repository. They are original, so there is nothing to license. Uploaded
tracks are stored like voices; see the API's music service.

Every track is 24 kHz mono float32, like the rest of the pipeline.
"""

from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from podcast_engine.common.audio import SR

Role = Literal["bed", "intro", "outro", "sting", "any"]
BUILTIN_PREFIX = "builtin:"
TrackId = Annotated[
    str,
    Field(
        pattern=r"^(builtin:[a-z0-9-]{1,40}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$",
        description="A built-in track (`builtin:calm-pad`) or the id of a track you uploaded",
        examples=["builtin:calm-pad"],
    ),
]
BED_LEVEL_DEFAULT_DB = -22


class ShowMusic(BaseModel):
    """A show's music. An empty slot keeps the default chime (intro, outro, sting) or no bed."""

    model_config = ConfigDict(extra="forbid")

    intro: TrackId | None = Field(None, description="Plays before the first line (up to 10 s)")
    outro: TrackId | None = Field(None, description="Plays after the last line (up to 15 s)")
    sting: TrackId | None = Field(None, description="Plays between segments (up to 4 s)")
    bed: TrackId | None = Field(None, description="Loops quietly under the whole conversation")
    bed_level_db: int = Field(
        BED_LEVEL_DEFAULT_DB,
        ge=-30,
        le=-12,
        description="How far the bed sits below the voices while they talk, in dB",
    )

    def track_ids(self) -> set[str]:
        return {t for t in (self.intro, self.outro, self.sting, self.bed) if t}


# ---- synthesis ------------------------------------------------------------------------------


def _hz(midi: float) -> float:
    return float(440.0 * 2 ** ((midi - 69) / 12))


def _time(seconds: float) -> np.ndarray:
    return np.arange(int(SR * seconds), dtype=np.float64) / SR


def _envelope(t: np.ndarray, attack: float, release: float) -> np.ndarray:
    """Rise over ``attack`` seconds and fall (exponentially) over the last ``release`` seconds."""
    length = t[-1] if len(t) else 0.0
    rise = np.clip(t / max(attack, 1e-3), 0.0, 1.0)
    fall_start = max(length - release, 0.0)
    fall = np.where(t > fall_start, np.exp(-(t - fall_start) * 5.0 / max(release, 1e-3)), 1.0)
    return rise * fall


def _pad_note(midi: float, seconds: float, attack: float = 1.8, release: float = 2.5) -> np.ndarray:
    """A soft, slightly detuned pad voice: a fundamental with two quiet overtones."""
    t = _time(seconds)
    f = _hz(midi)
    tone = np.zeros_like(t)
    for harmonic, level in ((1, 1.0), (2, 0.3), (3, 0.1)):
        for cents in (-6.0, 6.0):
            detuned = f * harmonic * 2 ** (cents / 1200)
            tone += level * np.sin(2 * np.pi * detuned * t + harmonic * cents)
    shimmer = 1.0 + 0.04 * np.sin(2 * np.pi * 0.23 * t + midi)  # a slow drift in level
    return np.asarray(tone * shimmer * _envelope(t, attack, release) / 2.8)


def _keys_note(midi: float, seconds: float, velocity: float = 1.0) -> np.ndarray:
    """An electric-piano tone: a little FM bite at the start that mellows as it decays."""
    t = _time(seconds)
    f = _hz(midi)
    index = 1.1 * np.exp(-3.5 * t)
    tone = np.sin(2 * np.pi * f * t + index * np.sin(2 * np.pi * f * t))
    tone += 0.15 * np.sin(2 * np.pi * 2 * f * t) * np.exp(-6 * t)
    return np.asarray(
        velocity * tone * _envelope(t, 0.004, min(0.6, seconds / 2)) * np.exp(-1.3 * t)
    )


def _bell(midi: float, seconds: float, velocity: float = 1.0) -> np.ndarray:
    t = _time(seconds)
    f = _hz(midi)
    tone = np.sin(2 * np.pi * f * t) * np.exp(-2.8 * t)
    tone += 0.35 * np.sin(2 * np.pi * 2.76 * f * t) * np.exp(-6.0 * t)  # the bell's bright partial
    tone += 0.2 * np.sin(2 * np.pi * 2 * f * t) * np.exp(-4.0 * t)
    return np.asarray(velocity * tone * _envelope(t, 0.003, 0.2))


def _bass_note(midi: float, seconds: float, velocity: float = 1.0) -> np.ndarray:
    t = _time(seconds)
    f = _hz(midi)
    tone = np.sin(2 * np.pi * f * t) + 0.25 * np.sin(2 * np.pi * 2 * f * t)
    return np.asarray(velocity * tone * _envelope(t, 0.01, 0.15) * np.exp(-0.9 * t))


def _kick() -> np.ndarray:
    t = _time(0.35)
    freq = 45.0 + 70.0 * np.exp(-t * 28.0)
    phase = 2 * np.pi * np.cumsum(freq) / SR
    return np.sin(phase) * np.exp(-t * 9.0)


def _noise_hit(rng: np.random.Generator, seconds: float, decay: float, bright: bool) -> np.ndarray:
    t = _time(seconds)
    noise = rng.standard_normal(len(t))
    if bright:
        noise = np.diff(noise, prepend=0.0)  # tilt toward the highs: a hat
    else:
        noise = np.convolve(noise, np.ones(4) / 4, mode="same")  # duller: a soft snare
    return noise * np.exp(-t * decay)


def _reverb(signal: np.ndarray, seconds: float, wet: float, seed: int) -> np.ndarray:
    """A plain algorithmic room: the signal convolved with smoothed, decaying noise."""
    rng = np.random.default_rng(seed)
    t = _time(seconds)
    impulse = rng.standard_normal(len(t)) * np.exp(-t * 6.0 / seconds)
    impulse = np.convolve(impulse, np.ones(6) / 6, mode="same")  # darker tail
    impulse /= np.sqrt(np.sum(impulse**2)) or 1.0
    size = 1 << int(np.ceil(np.log2(len(signal) + len(impulse))))
    tail = np.fft.irfft(np.fft.rfft(signal, size) * np.fft.rfft(impulse, size), size)
    return signal + wet * tail[: len(signal)]


def _add(buffer: np.ndarray, seconds: float, signal: np.ndarray) -> None:
    start = int(seconds * SR)
    end = min(start + len(signal), len(buffer))
    if end > start:
        buffer[start:end] += signal[: end - start]


def _loop(rendered: np.ndarray, loop_seconds: float) -> np.ndarray:
    """Fold everything past ``loop_seconds`` (the tails of the last notes) back onto the start,
    so the track repeats without a seam."""
    n = int(loop_seconds * SR)
    out = rendered[:n].copy()
    tail = rendered[n:]
    out[: len(tail)] += tail[:n]
    return out


def _finish(signal: np.ndarray, rms: float = 0.1) -> np.ndarray:
    level = float(np.sqrt(np.mean(signal**2))) or 1.0
    out = signal * (rms / level)
    peak = float(np.max(np.abs(out))) or 1.0
    if peak > 0.9:
        out *= 0.9 / peak
    return out.astype(np.float32)


def _fade_out(signal: np.ndarray, seconds: float) -> np.ndarray:
    n = min(int(seconds * SR), len(signal))
    signal[len(signal) - n :] *= np.linspace(1.0, 0.0, n)
    return signal


def _calm_pad() -> np.ndarray:
    """32 s of slow, warm chords (C, Am, F, G), made to loop."""
    chords = ([48, 55, 64, 71], [45, 52, 60, 67], [41, 48, 57, 64], [43, 50, 59, 62])
    hold = 8.0
    out = np.zeros(int(SR * (hold * len(chords) + 4.0)))
    for n, chord in enumerate(chords):
        for midi in chord:
            _add(out, n * hold, _pad_note(midi, hold + 2.5))
        _add(out, n * hold, 0.6 * _pad_note(chord[0] - 12, hold + 2.5, attack=2.5))
    return _finish(_loop(_reverb(out, 1.8, 0.35, seed=11), hold * len(chords)))


def _lofi_loop() -> np.ndarray:
    """8 bars of a mellow lo-fi groove at 80 bpm (Fmaj7, Em7, Dm7, Cmaj7), made to loop."""
    rng = np.random.default_rng(7)
    beat = 60.0 / 80
    bar = 4 * beat
    chords = ([53, 57, 60, 64], [52, 55, 59, 62], [50, 53, 57, 60], [48, 52, 55, 59])
    length = 8 * bar
    keys = np.zeros(int(SR * (length + 3.0)))
    drums = np.zeros_like(keys)
    for n in range(8):
        start = n * bar
        chord = chords[n // 2]
        for midi in chord:
            _add(keys, start, _keys_note(midi, bar * 0.95, 0.55))
            _add(keys, start + 2.5 * beat, _keys_note(midi + 12, beat, 0.12))
        _add(keys, start, _bass_note(chord[0] - 12, 1.6 * beat, 0.9))
        _add(keys, start + 2.5 * beat, _bass_note(chord[0] - 12, 1.2 * beat, 0.6))
        for at, level in ((0.0, 1.0), (1.5, 0.6), (2.0, 0.8)):
            _add(drums, start + at * beat, level * _kick())
        for at in (1.0, 3.0):
            _add(drums, start + at * beat, 0.35 * _noise_hit(rng, 0.2, 22.0, bright=False))
        for eighth in range(8):
            swing = 0.08 * beat if eighth % 2 else 0.0  # lazy off-beats
            level = 0.12 if eighth % 2 else 0.18
            _add(
                drums, start + eighth * beat / 2 + swing, level * _noise_hit(rng, 0.06, 70.0, True)
            )
    mixed = _reverb(keys, 0.8, 0.25, seed=13) + 0.55 * drums
    return _finish(_loop(mixed, length))


def _bright_intro() -> np.ndarray:
    """About 7 s: a pad swells, a bright arpeggio climbs and lands on a bell chord."""
    out = np.zeros(int(SR * 7.0))
    for midi in (48, 55, 64, 67):
        _add(out, 0.0, 0.8 * _pad_note(midi, 6.8, attack=1.2, release=2.8))
    for n, midi in enumerate((72, 76, 79, 84, 86, 88)):
        _add(out, 0.5 + 0.2 * n, _bell(midi, 2.0, 0.45))
    for midi in (72, 76, 79, 84):
        _add(out, 1.9, _bell(midi, 4.5, 0.4))
    return _finish(_fade_out(_reverb(out, 1.6, 0.3, seed=17), 0.6), rms=0.09)


def _soft_outro() -> np.ndarray:
    """About 9 s: a falling arpeggio over Fmaj7 that resolves to C, then fades."""
    out = np.zeros(int(SR * 9.0))
    for n, midi in enumerate((79, 76, 72, 69, 67, 64)):
        _add(out, 0.2 + 0.32 * n, _keys_note(midi, 2.5, 0.5))
    for midi in (53, 57, 60, 64):
        _add(out, 0.0, 0.7 * _pad_note(midi, 4.4, attack=0.8, release=1.8))
    for midi in (48, 55, 64, 72):
        _add(out, 3.6, 0.8 * _pad_note(midi, 5.4, attack=1.2, release=3.5))
    _add(out, 3.6, _bell(72, 4.0, 0.3))
    return _finish(_fade_out(_reverb(out, 2.0, 0.35, seed=19), 2.0), rms=0.08)


def _two_note_sting() -> np.ndarray:
    """1.6 s: two bell notes over a short, soft chord, between segments."""
    out = np.zeros(int(SR * 1.6))
    for midi in (60, 67, 76):
        _add(out, 0.0, 0.35 * _pad_note(midi, 1.6, attack=0.15, release=0.9))
    _add(out, 0.0, _bell(79, 1.5, 0.5))
    _add(out, 0.2, _bell(84, 1.4, 0.55))
    return _finish(_fade_out(_reverb(out, 1.0, 0.3, seed=23), 0.3), rms=0.09)


@dataclass(frozen=True)
class BuiltinTrack:
    track_id: str
    name: str
    role: Role
    description: str
    seamless: bool  # made to loop: repeated end to start without a crossfade
    render: Callable[[], np.ndarray]


BUILTIN_TRACKS: dict[str, BuiltinTrack] = {
    track.track_id: track
    for track in (
        BuiltinTrack(
            "builtin:calm-pad",
            "Calm pad",
            "bed",
            "Slow, warm chords; sits well under talk.",
            True,
            _calm_pad,
        ),
        BuiltinTrack(
            "builtin:lofi-loop",
            "Lo-fi loop",
            "bed",
            "A mellow 80 bpm groove with soft drums.",
            True,
            _lofi_loop,
        ),
        BuiltinTrack(
            "builtin:bright-intro",
            "Bright intro",
            "intro",
            "A pad swell and a climbing bell arpeggio.",
            False,
            _bright_intro,
        ),
        BuiltinTrack(
            "builtin:soft-outro",
            "Soft outro",
            "outro",
            "A falling arpeggio that resolves and fades.",
            False,
            _soft_outro,
        ),
        BuiltinTrack(
            "builtin:two-note-sting",
            "Two-note sting",
            "sting",
            "Two bell notes between segments.",
            False,
            _two_note_sting,
        ),
    )
}


def is_builtin(track_id: str) -> bool:
    return track_id.startswith(BUILTIN_PREFIX)


@lru_cache(maxsize=len(BUILTIN_TRACKS))
def _rendered(track_id: str) -> np.ndarray:
    audio = BUILTIN_TRACKS[track_id].render()
    audio.setflags(write=False)
    return audio


def builtin_audio(track_id: str) -> np.ndarray:
    """A built-in track's audio (read-only; copy it before changing it). KeyError if unknown."""
    if track_id not in BUILTIN_TRACKS:
        raise KeyError(track_id)
    return _rendered(track_id)

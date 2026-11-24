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
        """Return the ids of every track the show uses.

        Returns:
            The ids of the filled slots.
        """
        return {t for t in (self.intro, self.outro, self.sting, self.bed) if t}


def _hz(midi: float) -> float:
    """Convert a MIDI note number to a frequency.

    Args:
        midi: The note; 69 is A4.

    Returns:
        The frequency in Hz.
    """
    return float(440.0 * 2 ** ((midi - 69) / 12))


def _time(seconds: float) -> np.ndarray:
    """Return the sample times for a stretch of audio.

    Args:
        seconds: Its length.

    Returns:
        Each sample's time, in seconds.
    """
    return np.arange(int(SR * seconds), dtype=np.float64) / SR


def _envelope(t: np.ndarray, attack: float, release: float) -> np.ndarray:
    """Rise over ``attack`` seconds and fall (exponentially) over the last ``release`` seconds.

    Args:
        t: The sample times.
        attack: The rise's length.
        release: The fall's length.

    Returns:
        The gain at each sample.
    """
    length = t[-1] if len(t) else 0.0
    rise = np.clip(t / max(attack, 1e-3), 0.0, 1.0)
    fall_start = max(length - release, 0.0)
    fall = np.where(t > fall_start, np.exp(-(t - fall_start) * 5.0 / max(release, 1e-3)), 1.0)
    return rise * fall


def _pad_note(midi: float, seconds: float, attack: float = 1.8, release: float = 2.5) -> np.ndarray:
    """Play a soft, slightly detuned pad note: a fundamental with two quiet overtones.

    Its level drifts slowly, so a held chord does not sound static.

    Args:
        midi: The note, as a MIDI number.
        seconds: Its length.
        attack: Seconds to swell in.
        release: Seconds to fade out.

    Returns:
        The note's samples.
    """
    t = _time(seconds)
    f = _hz(midi)
    tone = np.zeros_like(t)
    for harmonic, level in ((1, 1.0), (2, 0.3), (3, 0.1)):
        for cents in (-6.0, 6.0):
            detuned = f * harmonic * 2 ** (cents / 1200)
            tone += level * np.sin(2 * np.pi * detuned * t + harmonic * cents)
    shimmer = 1.0 + 0.04 * np.sin(2 * np.pi * 0.23 * t + midi)
    return np.asarray(tone * shimmer * _envelope(t, attack, release) / 2.8)


def _keys_note(midi: float, seconds: float, velocity: float = 1.0) -> np.ndarray:
    """Play an electric-piano note: a little FM bite at the start that mellows as it decays.

    Args:
        midi: The note, as a MIDI number.
        seconds: Its length.
        velocity: How hard it is played.

    Returns:
        The note's samples.
    """
    t = _time(seconds)
    f = _hz(midi)
    index = 1.1 * np.exp(-3.5 * t)
    tone = np.sin(2 * np.pi * f * t + index * np.sin(2 * np.pi * f * t))
    tone += 0.15 * np.sin(2 * np.pi * 2 * f * t) * np.exp(-6 * t)
    return np.asarray(
        velocity * tone * _envelope(t, 0.004, min(0.6, seconds / 2)) * np.exp(-1.3 * t)
    )


def _bell(midi: float, seconds: float, velocity: float = 1.0) -> np.ndarray:
    """Play a bell note, with the bright inharmonic partial that makes it a bell.

    Args:
        midi: The note, as a MIDI number.
        seconds: Its length.
        velocity: How hard it is struck.

    Returns:
        The note's samples.
    """
    t = _time(seconds)
    f = _hz(midi)
    tone = np.sin(2 * np.pi * f * t) * np.exp(-2.8 * t)
    tone += 0.35 * np.sin(2 * np.pi * 2.76 * f * t) * np.exp(-6.0 * t)
    tone += 0.2 * np.sin(2 * np.pi * 2 * f * t) * np.exp(-4.0 * t)
    return np.asarray(velocity * tone * _envelope(t, 0.003, 0.2))


def _bass_note(midi: float, seconds: float, velocity: float = 1.0) -> np.ndarray:
    """Play a round bass note.

    Args:
        midi: The note, as a MIDI number.
        seconds: Its length.
        velocity: How hard it is played.

    Returns:
        The note's samples.
    """
    t = _time(seconds)
    f = _hz(midi)
    tone = np.sin(2 * np.pi * f * t) + 0.25 * np.sin(2 * np.pi * 2 * f * t)
    return np.asarray(velocity * tone * _envelope(t, 0.01, 0.15) * np.exp(-0.9 * t))


def _kick() -> np.ndarray:
    """Make a soft kick drum: a falling sine.

    Returns:
        The drum's samples.
    """
    t = _time(0.35)
    freq = 45.0 + 70.0 * np.exp(-t * 28.0)
    phase = 2 * np.pi * np.cumsum(freq) / SR
    return np.sin(phase) * np.exp(-t * 9.0)


def _noise_hit(rng: np.random.Generator, seconds: float, decay: float, bright: bool) -> np.ndarray:
    """Make a noise drum: a hat when bright, a soft snare when dull.

    Args:
        rng: The seeded random generator.
        seconds: Its length.
        decay: How fast it dies away.
        bright: True tilts the noise toward the highs (a hat); False smooths it (a snare).

    Returns:
        The drum's samples.
    """
    t = _time(seconds)
    noise = rng.standard_normal(len(t))
    if bright:
        noise = np.diff(noise, prepend=0.0)
    else:
        noise = np.convolve(noise, np.ones(4) / 4, mode="same")
    return noise * np.exp(-t * decay)


def _reverb(signal: np.ndarray, seconds: float, wet: float, seed: int) -> np.ndarray:
    """Add a plain algorithmic room: the signal convolved with smoothed, decaying noise.

    The noise is smoothed for a darker tail.

    Args:
        signal: The dry audio.
        seconds: The room's decay time.
        wet: How much of the room to add.
        seed: Seeds the room's noise, so it is the same every time.

    Returns:
        The audio with the room added.
    """
    rng = np.random.default_rng(seed)
    t = _time(seconds)
    impulse = rng.standard_normal(len(t)) * np.exp(-t * 6.0 / seconds)
    impulse = np.convolve(impulse, np.ones(6) / 6, mode="same")
    impulse /= np.sqrt(np.sum(impulse**2)) or 1.0
    size = 1 << int(np.ceil(np.log2(len(signal) + len(impulse))))
    tail = np.fft.irfft(np.fft.rfft(signal, size) * np.fft.rfft(impulse, size), size)
    return signal + wet * tail[: len(signal)]


def _add(buffer: np.ndarray, seconds: float, signal: np.ndarray) -> None:
    """Mix a signal into a buffer at a time, cutting off what runs past its end.

    Args:
        buffer: The track being built; changed in place.
        seconds: Where the signal starts.
        signal: The audio to add.
    """
    start = int(seconds * SR)
    end = min(start + len(signal), len(buffer))
    if end > start:
        buffer[start:end] += signal[: end - start]


def _loop(rendered: np.ndarray, loop_seconds: float) -> np.ndarray:
    """Fold the tails of the last notes back onto the start, so the track repeats without a seam.

    Args:
        rendered: The rendered audio, longer than the loop.
        loop_seconds: The loop's length.

    Returns:
        The loop, exactly ``loop_seconds`` long.
    """
    n = int(loop_seconds * SR)
    out = rendered[:n].copy()
    tail = rendered[n:]
    out[: len(tail)] += tail[:n]
    return out


def _finish(signal: np.ndarray, rms: float = 0.1) -> np.ndarray:
    """Level a track and keep its peaks under 0.9.

    Args:
        signal: The track.
        rms: The level to reach.

    Returns:
        The track as float32.
    """
    level = float(np.sqrt(np.mean(signal**2))) or 1.0
    out = signal * (rms / level)
    peak = float(np.max(np.abs(out))) or 1.0
    if peak > 0.9:
        out *= 0.9 / peak
    return out.astype(np.float32)


def _fade_out(signal: np.ndarray, seconds: float) -> np.ndarray:
    """Fade the end of a signal to silence.

    Args:
        signal: The audio; changed in place.
        seconds: The fade's length.

    Returns:
        The same array.
    """
    n = min(int(seconds * SR), len(signal))
    signal[len(signal) - n :] *= np.linspace(1.0, 0.0, n)
    return signal


def _calm_pad() -> np.ndarray:
    """Make 32 s of slow, warm chords (C, Am, F, G), made to loop.

    Returns:
        The track.
    """
    chords = ([48, 55, 64, 71], [45, 52, 60, 67], [41, 48, 57, 64], [43, 50, 59, 62])
    hold = 8.0
    out = np.zeros(int(SR * (hold * len(chords) + 4.0)))
    for n, chord in enumerate(chords):
        for midi in chord:
            _add(out, n * hold, _pad_note(midi, hold + 2.5))
        _add(out, n * hold, 0.6 * _pad_note(chord[0] - 12, hold + 2.5, attack=2.5))
    return _finish(_loop(_reverb(out, 1.8, 0.35, seed=11), hold * len(chords)))


def _lofi_loop() -> np.ndarray:
    """Make 8 bars of a mellow lo-fi groove at 80 bpm (Fmaj7, Em7, Dm7, Cmaj7), made to loop.

    Keys hold each chord with a lazy off-beat note, over bass, a soft kick, snare and swung hats.

    Returns:
        The track.
    """
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
            swing = 0.08 * beat if eighth % 2 else 0.0
            level = 0.12 if eighth % 2 else 0.18
            _add(
                drums, start + eighth * beat / 2 + swing, level * _noise_hit(rng, 0.06, 70.0, True)
            )
    mixed = _reverb(keys, 0.8, 0.25, seed=13) + 0.55 * drums
    return _finish(_loop(mixed, length))


def _bright_intro() -> np.ndarray:
    """Make about 7 s of intro: a pad swells, a bright arpeggio climbs and lands on a bell chord.

    Returns:
        The track.
    """
    out = np.zeros(int(SR * 7.0))
    for midi in (48, 55, 64, 67):
        _add(out, 0.0, 0.8 * _pad_note(midi, 6.8, attack=1.2, release=2.8))
    for n, midi in enumerate((72, 76, 79, 84, 86, 88)):
        _add(out, 0.5 + 0.2 * n, _bell(midi, 2.0, 0.45))
    for midi in (72, 76, 79, 84):
        _add(out, 1.9, _bell(midi, 4.5, 0.4))
    return _finish(_fade_out(_reverb(out, 1.6, 0.3, seed=17), 0.6), rms=0.09)


def _soft_outro() -> np.ndarray:
    """Make about 9 s of outro: a falling arpeggio over Fmaj7 that resolves to C, then fades.

    Returns:
        The track.
    """
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
    """Make a 1.6 s sting between segments: two bell notes over a short, soft chord.

    Returns:
        The track.
    """
    out = np.zeros(int(SR * 1.6))
    for midi in (60, 67, 76):
        _add(out, 0.0, 0.35 * _pad_note(midi, 1.6, attack=0.15, release=0.9))
    _add(out, 0.0, _bell(79, 1.5, 0.5))
    _add(out, 0.2, _bell(84, 1.4, 0.55))
    return _finish(_fade_out(_reverb(out, 1.0, 0.3, seed=23), 0.3), rms=0.09)


@dataclass(frozen=True)
class BuiltinTrack:
    """A built-in track, made in code.

    Built-in tracks are synthesised with numpy from a fixed seed, so the API (which plays them in
    the web app) and the assemble worker (which mixes them into episodes) make the same audio, and
    no music files live in the repository. They are original, so there is nothing to license. A
    ``seamless`` track is made to loop: repeated end to start without a crossfade.
    """

    track_id: str
    name: str
    role: Role
    description: str
    seamless: bool
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
    """Tell whether a track id names a built-in track.

    Args:
        track_id: The track's id.

    Returns:
        True for ``builtin:...``.
    """
    return track_id.startswith(BUILTIN_PREFIX)


@lru_cache(maxsize=len(BUILTIN_TRACKS))
def _rendered(track_id: str) -> np.ndarray:
    """Render a built-in track once per process, read-only.

    Args:
        track_id: The track's id.

    Returns:
        The track's audio.
    """
    audio = BUILTIN_TRACKS[track_id].render()
    audio.setflags(write=False)
    return audio


def builtin_audio(track_id: str) -> np.ndarray:
    """Return a built-in track's audio, 24 kHz mono float32 like the rest of the pipeline.

    The array is read-only; copy it before changing it.

    Args:
        track_id: The track's id.

    Returns:
        The track's audio.

    Raises:
        KeyError: There is no such built-in track.
    """
    if track_id not in BUILTIN_TRACKS:
        raise KeyError(track_id)
    return _rendered(track_id)

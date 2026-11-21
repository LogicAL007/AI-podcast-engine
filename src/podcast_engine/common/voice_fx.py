"""Voice effects for a show's hosts: deepen, warmth and a broadcast ("radio voice") chain.

The settings live on the show (``shows.host_effects``), per host. They are applied when an episode
is assembled and when a type-to-speech clip is made, never at synthesis, so the TTS cache keeps
the raw voices and changing an effect never voices anything again.

pedalboard (Spotify) is imported only when audio is processed, so the API, which only validates
the settings, does not need it.
"""

from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from podcast_engine.common.audio import SR

DEEPEN_SEMITONES = 5.0  # deepen=100 lowers the pitch this much
DEEPEN_BODY_DB = 3.0  # and adds this much low end, so a lower voice also sounds bigger
WARMTH_LOW_DB = 4.0  # warmth=100: low shelf boost at 250 Hz
WARMTH_HIGH_DB = -3.0  # and a gentle high shelf cut at 7 kHz


class VoiceEffects(BaseModel):
    """How one host's voice is processed. All off by default. Frozen, so equal settings compare
    (and hash) equal: a clip shared by two hosts is processed only if theirs are the same."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    deepen: int = Field(0, ge=0, le=100, description="0 = natural, 100 = 5 semitones lower")
    warmth: int = Field(0, ge=0, le=100, description="0 = natural, 100 = fullest low end")
    broadcast: bool = Field(False, description="High-pass, compression, presence and de-ess")

    @property
    def active(self) -> bool:
        return self.deepen > 0 or self.warmth > 0 or self.broadcast


Preset = Literal["natural", "deeper", "warm", "broadcast", "deep_broadcast"]

PRESETS: dict[str, VoiceEffects] = {
    "natural": VoiceEffects(),
    "deeper": VoiceEffects(deepen=40, warmth=20),
    "warm": VoiceEffects(warmth=60),
    "broadcast": VoiceEffects(warmth=30, broadcast=True),
    "deep_broadcast": VoiceEffects(deepen=40, warmth=40, broadcast=True),
}


def _chain(fx: VoiceEffects) -> list[object]:
    from pedalboard import (
        Compressor,
        HighpassFilter,
        HighShelfFilter,
        Limiter,
        LowShelfFilter,
        PeakFilter,
        PitchShift,
    )

    plugins: list[object] = []
    if fx.deepen:
        plugins.append(PitchShift(semitones=-DEEPEN_SEMITONES * fx.deepen / 100))
        plugins.append(
            LowShelfFilter(cutoff_frequency_hz=150, gain_db=DEEPEN_BODY_DB * fx.deepen / 100)
        )
    if fx.warmth:
        plugins.append(
            LowShelfFilter(cutoff_frequency_hz=250, gain_db=WARMTH_LOW_DB * fx.warmth / 100)
        )
        plugins.append(
            HighShelfFilter(cutoff_frequency_hz=7000, gain_db=WARMTH_HIGH_DB * fx.warmth / 100)
        )
    if fx.broadcast:
        plugins += [
            HighpassFilter(cutoff_frequency_hz=80),
            Compressor(threshold_db=-18, ratio=3, attack_ms=3, release_ms=60),
            PeakFilter(cutoff_frequency_hz=3000, gain_db=2, q=0.9),  # presence
            PeakFilter(cutoff_frequency_hz=6500, gain_db=-3, q=2.0),  # de-ess
            Limiter(threshold_db=-1, release_ms=50),
        ]
    return plugins


def apply_effects(audio: np.ndarray, fx: VoiceEffects | None) -> np.ndarray:
    """``audio`` (mono, float32, at SR) with ``fx`` applied; the same array when all are off."""
    if fx is None or not fx.active or len(audio) == 0:
        return audio
    from pedalboard import Pedalboard  # type: ignore[attr-defined]

    board = Pedalboard(_chain(fx))  # type: ignore[arg-type]
    out = board(np.ascontiguousarray(audio, dtype=np.float32).reshape(1, -1), SR)
    return np.asarray(out, dtype=np.float32).reshape(-1)[: len(audio)]

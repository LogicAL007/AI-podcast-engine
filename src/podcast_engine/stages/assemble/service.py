"""Assemble: stitch audio together and normalise loudness."""

from uuid import UUID

from podcast_engine.common.queue import Stage

TARGET_LUFS = -16.0
LOUDNESS_TOLERANCE_LU = 1.0
MIN_SAMPLE_RATE_HZ = 24_000


def needs_normalisation(measured_lufs: float) -> bool:
    """True when integrated loudness is outside the NFR target of about -16 LUFS."""
    return abs(measured_lufs - TARGET_LUFS) > LOUDNESS_TOLERANCE_LU


def assemble_episode(episode_id: UUID) -> Stage | None:
    """FR6: add intro, outro and transitions, normalise loudness, run silence/clipping checks."""
    raise NotImplementedError("assemble_episode: FFmpeg/pydub assembly plus pyloudnorm check")

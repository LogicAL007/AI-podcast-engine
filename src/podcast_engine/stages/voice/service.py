"""Voice: per-host text-to-speech with a segment cache."""

import hashlib
from uuid import UUID

from podcast_engine.common.queue import Stage


def segment_cache_key(provider: str, voice_id: str, text: str) -> str:
    """Key for a synthesised line. Unchanged lines hit the cache on regeneration.

    Includes the provider and voice, so switching either never serves stale audio.
    """
    digest = hashlib.sha256(f"{provider}\x00{voice_id}\x00{text}".encode()).hexdigest()
    return f"tts/{digest}.wav"


def synthesise_voices(episode_id: UUID) -> Stage | None:
    """FR6: voice each script line with its host's stock voice (never a cloned real person)."""
    raise NotImplementedError("synthesise_voices: call the TTS provider, cache by segment key")

"""How type-to-speech text is split and where its audio is stored, kept apart from the voice
worker so the API can find a voice's clips when the voice is withdrawn."""

import re
from uuid import UUID

from podcast_engine.stages.voice.backends import ChatterboxBackend
from podcast_engine.stages.voice.service import segment_cache_key

MAX_PIECE_CHARS = 250  # Chatterbox reads a sentence or two well; longer text is split


def speech_key(owner: UUID, clip_id: UUID) -> str:
    """Object key of a type-to-speech clip. Private: only its owner, through the API, plays it."""
    return f"speech/{owner}/{clip_id}.wav"


def pieces(text: str, limit: int = MAX_PIECE_CHARS) -> list[str]:
    """``text`` as sentences, joined while they fit in ``limit`` characters; a longer sentence is
    split at commas, then between words."""
    units: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", " ".join(text.split())):
        parts = [sentence]
        if len(sentence) > limit:
            parts = re.split(r"(?<=[,;:])\s+", sentence)
        for part in parts:
            while len(part) > limit:
                cut = part.rfind(" ", 0, limit)
                cut = cut if cut > 0 else limit
                units.append(part[:cut].strip())
                part = part[cut:].strip()
            if part:
                units.append(part)
    out: list[str] = []
    for unit in units:
        if out and len(out[-1]) + 1 + len(unit) <= limit:
            out[-1] = f"{out[-1]} {unit}"
        else:
            out.append(unit)
    return out


def raw_speech_keys(sha256: str, text: str, delivery: str) -> list[str]:
    """The cached raw speech of a clip read by Chatterbox in the recording with this checksum,
    to delete when that voice is withdrawn (the same keys the voice worker wrote)."""
    voice_id = f"chatterbox:{sha256[:12]}:styles{ChatterboxBackend.STYLES_VERSION}"
    return [
        segment_cache_key(ChatterboxBackend.provider, voice_id, piece, delivery)
        for piece in pieces(text)
    ]

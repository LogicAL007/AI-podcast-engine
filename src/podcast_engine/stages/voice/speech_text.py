import re
from uuid import UUID

from podcast_engine.stages.voice.backends import ChatterboxBackend
from podcast_engine.stages.voice.service import segment_cache_key

MAX_PIECE_CHARS = 250


def speech_key(owner: UUID, clip_id: UUID) -> str:
    """Return the object key of a type-to-speech clip.

    Kept apart from the voice worker so the API can find a voice's clips when the voice is
    withdrawn. The clip is private: only its owner, through the API, plays it.

    Args:
        owner: The user who made the clip.
        clip_id: The clip's id.

    Returns:
        The clip's key in object storage.
    """
    return f"speech/{owner}/{clip_id}.wav"


def pieces(text: str, limit: int = MAX_PIECE_CHARS) -> list[str]:
    """Split text into pieces short enough for the voice model to read well.

    Chatterbox reads a sentence or two well, so longer text is split: sentences are joined while
    they fit in ``limit`` characters, and a longer sentence is split at commas, then between words.

    Args:
        text: The text to split; runs of whitespace count as one space.
        limit: Most characters in a piece.

    Returns:
        The pieces, in reading order.
    """
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
    """Return the cache keys of a clip's raw speech in one recorded voice.

    These are the keys the voice worker wrote when Chatterbox read the clip in the recording with
    this checksum, to delete when that voice is withdrawn.

    Args:
        sha256: The checksum of the voice's recording.
        text: The clip's text.
        delivery: The delivery it was read with, such as ``neutral``.

    Returns:
        One object key per piece of the text.
    """
    voice_id = f"chatterbox:{sha256[:12]}:styles{ChatterboxBackend.STYLES_VERSION}"
    return [
        segment_cache_key(ChatterboxBackend.provider, voice_id, piece, delivery)
        for piece in pieces(text)
    ]

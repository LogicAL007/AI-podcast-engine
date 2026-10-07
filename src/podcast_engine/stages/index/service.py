"""Index: clean, chunk and embed ingested items."""

from uuid import UUID

from podcast_engine.common.queue import Stage


def chunk_words(text: str, *, max_words: int = 200, overlap: int = 40) -> list[str]:
    """Split text into overlapping word windows for embedding.

    Overlap keeps a claim that straddles a boundary retrievable from either chunk.
    """
    if max_words <= 0:
        raise ValueError("max_words must be positive")
    if not 0 <= overlap < max_words:
        raise ValueError("overlap must be in [0, max_words)")
    words = text.split()
    step = max_words - overlap
    return [
        " ".join(words[start : start + max_words])
        for start in range(0, max(len(words) - overlap, 1), step)
    ]


def index_items(episode_id: UUID) -> Stage | None:
    """Embed new or changed items into pgvector with source, date and reliability metadata."""
    raise NotImplementedError("index_items: embed chunks with the configured model")

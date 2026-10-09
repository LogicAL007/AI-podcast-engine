"""Index: clean, chunk and embed ingested items."""

from uuid import UUID

from podcast_engine.common.context import PipelineContext, get_context
from podcast_engine.common.logging import get_logger
from podcast_engine.common.queue import Stage

# The overlap must be at least as long as the longest sentence, so every sentence sits whole inside
# at least one chunk (the offline writer quotes whole sentences and cites the chunk they came from).
CHUNK_WORDS, CHUNK_OVERLAP = 80, 40

log = get_logger("index")


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


def index_items(episode_id: UUID, ctx: PipelineContext | None = None) -> Stage | None:
    """Embed new or changed items into pgvector with source, date and reliability metadata.

    Chunks whose text is unchanged keep their stored vectors, so a refresh embeds only what changed.
    """
    ctx = ctx or get_context()
    episode = ctx.repo.get_episode(episode_id)
    embedded = reused = 0
    for item in ctx.repo.list_items(episode.show_id):
        pieces = chunk_words(item.text, max_words=CHUNK_WORDS, overlap=CHUNK_OVERLAP)
        new, kept = ctx.repo.replace_chunks(item.item_id, pieces, ctx.embedder.encode)
        embedded += new
        reused += kept
    log.info(
        "items_indexed",
        episode_id=str(episode_id),
        embedder=ctx.embedder.name,
        embedded=embedded,
        reused=reused,
    )
    return Stage.RETRIEVE_PLAN

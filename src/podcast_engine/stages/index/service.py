from uuid import UUID

from podcast_engine.common.context import PipelineContext, get_context
from podcast_engine.common.logging import get_logger
from podcast_engine.common.queue import Stage

CHUNK_WORDS, CHUNK_OVERLAP = 80, 40

log = get_logger("index")


def chunk_words(text: str, *, max_words: int = 200, overlap: int = 40) -> list[str]:
    """Split text into overlapping word windows for embedding.

    Overlap keeps a claim that straddles a boundary retrievable from either chunk.

    Args:
        text: The text to split.
        max_words: Most words in a chunk.
        overlap: Words each chunk shares with the one before it.

    Returns:
        The chunks, in order; a text shorter than one window gives a single chunk.

    Raises:
        ValueError: ``max_words`` is not positive, or ``overlap`` is not in ``[0, max_words)``.
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
    """Embed the show's new or changed items into pgvector (stage 2, index).

    Items are chunked into 80-word windows with a 40-word overlap. The overlap must be at least as
    long as the longest sentence, so every sentence sits whole inside at least one chunk: the
    offline writer quotes whole sentences and cites the chunk they came from. Chunks whose text is
    unchanged keep their stored vectors, so a refresh embeds only what changed. Each chunk keeps its
    source, date and reliability metadata.

    Args:
        episode_id: The episode being made.
        ctx: Shared clients (database, embedder); built from settings when omitted.

    Returns:
        The next stage, retrieve and plan.
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

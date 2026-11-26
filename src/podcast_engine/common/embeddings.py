import hashlib
from collections.abc import Sequence
from typing import Protocol

import numpy as np

from podcast_engine.common.config import Settings
from podcast_engine.common.text import content_tokens

HASHING = "hashing"


class Embedder(Protocol):
    """Turns text into vectors for the vector store and the topic matching.

    Every embedder returns L2-normalised rows, so a dot product is a cosine similarity, which is
    what the vector store's ``<=>`` operator and the topic matching rely on. ``name`` identifies the
    model and ``dim`` is the vector length.
    """

    name: str
    dim: int

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        """Embed texts as normalised rows.

        Args:
            texts: The texts to embed.

        Returns:
            An array of shape ``(len(texts), dim)``, one unit-length row per text.
        """
        ...


class HashingEmbedder:
    """Signed hashing of stemmed words: the offline default.

    Deterministic, dependency-free, and needs no download. It matches on shared vocabulary only, so
    it cannot tell that two different words mean the same thing. Use a sentence-transformers model
    when meaning matters more than offline convenience.
    """

    def __init__(self, dim: int = 384) -> None:
        """Create the embedder.

        Args:
            dim: The vector length; it must match the database column.
        """
        self.name = f"hashing-bow-{dim}"
        self.dim = dim

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        """Hash each text's content words into a signed bag-of-words vector.

        Args:
            texts: The texts to embed.

        Returns:
            An array of shape ``(len(texts), dim)``; a text with no content words gives a zero row.
        """
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            for token in content_tokens(text):
                digest = hashlib.md5(token.encode(), usedforsecurity=False).digest()
                slot = int.from_bytes(digest[:4], "big") % self.dim
                out[row, slot] += 1.0 if digest[4] % 2 == 0 else -1.0
            norm = np.linalg.norm(out[row])
            if norm:
                out[row] /= norm
        return out


class SentenceTransformerEmbedder:
    """A sentence-transformers model (for example ``BAAI/bge-small-en-v1.5``, 384 dimensions)."""

    def __init__(self, model_name: str) -> None:
        """Load the model, downloading it on first use.

        Args:
            model_name: The model's name on Hugging Face.
        """
        from sentence_transformers import SentenceTransformer

        self.name = model_name
        self._model = SentenceTransformer(model_name)
        self.dim = int(self._model.get_sentence_embedding_dimension())

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        """Embed texts with the model, normalised.

        Args:
            texts: The texts to embed.

        Returns:
            An array of shape ``(len(texts), dim)``.
        """
        vectors = self._model.encode(list(texts), normalize_embeddings=True)
        return np.asarray(vectors, dtype=np.float32)


def make_embedder(settings: Settings) -> Embedder:
    """Return the embedder named by the settings.

    Args:
        settings: The embedding model and the database column's vector size.

    Returns:
        The hashing embedder or a sentence-transformers model.

    Raises:
        ValueError: The model's vectors do not fit the database column.
    """
    if settings.embedding_model == HASHING:
        return HashingEmbedder(settings.embedding_dimensions)
    embedder = SentenceTransformerEmbedder(settings.embedding_model)
    if embedder.dim != settings.embedding_dimensions:
        raise ValueError(
            f"{settings.embedding_model} produces {embedder.dim}-dimensional vectors, but the "
            f"database column holds {settings.embedding_dimensions}. Change both together."
        )
    return embedder


def to_pgvector(vector: np.ndarray) -> str:
    """Write a vector in the text form pgvector accepts: ``[0.1,0.2,...]``.

    Args:
        vector: The vector.

    Returns:
        The vector as text, with six decimals per value.
    """
    return "[" + ",".join(f"{value:.6f}" for value in vector) + "]"

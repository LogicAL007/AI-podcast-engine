"""Text embedders: an offline hashing embedder (the default) and sentence-transformers models.

Both return L2-normalised rows, so a dot product is a cosine similarity, which is what the vector
store's ``<=>`` operator and the topic matching rely on.
"""

import hashlib
from collections.abc import Sequence
from typing import Protocol

import numpy as np

from podcast_engine.common.config import Settings
from podcast_engine.common.text import content_tokens

HASHING = "hashing"


class Embedder(Protocol):
    name: str
    dim: int

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        """One normalised row per text, shape ``(len(texts), dim)``."""
        ...


class HashingEmbedder:
    """Signed hashing of stemmed words. Deterministic, dependency-free, and needs no download.

    It matches on shared vocabulary only, so it cannot tell that two different words mean the same
    thing. Use a sentence-transformers model when meaning matters more than offline convenience.
    """

    def __init__(self, dim: int = 384) -> None:
        self.name = f"hashing-bow-{dim}"
        self.dim = dim

    def encode(self, texts: Sequence[str]) -> np.ndarray:
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
        from sentence_transformers import SentenceTransformer

        self.name = model_name
        self._model = SentenceTransformer(model_name)
        self.dim = int(self._model.get_sentence_embedding_dimension())

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        vectors = self._model.encode(list(texts), normalize_embeddings=True)
        return np.asarray(vectors, dtype=np.float32)


def make_embedder(settings: Settings) -> Embedder:
    """The embedder named by settings; refuses one whose size does not fit the database column."""
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
    """The text form pgvector accepts: ``[0.1,0.2,...]``."""
    return "[" + ",".join(f"{value:.6f}" for value in vector) + "]"

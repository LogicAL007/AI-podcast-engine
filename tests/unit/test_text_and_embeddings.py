import numpy as np
import pytest

from podcast_engine.common.config import Settings
from podcast_engine.common.embeddings import (
    HashingEmbedder,
    make_embedder,
    to_pgvector,
)
from podcast_engine.common.text import STOPWORDS, content_tokens, stem


def test_stop_words_come_from_the_library_and_leave_content_words() -> None:
    assert {"the", "and", "of"} <= STOPWORDS
    tokens = content_tokens("The database stores columns of data on disk")
    assert "column" in tokens  # stemmed
    assert "the" not in tokens
    assert all(len(t) > 2 for t in tokens)


def test_stem_is_conservative_with_short_words() -> None:
    assert stem("stored") == "stor"
    assert stem("sis") == "sis"  # too short to strip


def test_hashing_embedder_is_deterministic_and_normalised() -> None:
    embedder = HashingEmbedder(384)
    a, b = embedder.encode(["column stores read fewer bytes", "column stores read fewer bytes"])
    assert np.allclose(a, b)
    assert float(np.linalg.norm(a)) == pytest.approx(1.0, abs=1e-5)
    assert embedder.encode(["x"]).shape == (1, 384)


def test_related_text_scores_higher_than_unrelated_text() -> None:
    embedder = HashingEmbedder(384)
    topic, related, unrelated = embedder.encode(
        [
            "column oriented database analytics queries",
            "analytics queries run over a column oriented database",
            "sourdough starter flour water yeast bread",
        ]
    )
    assert float(topic @ related) > float(topic @ unrelated) + 0.2


def test_empty_text_gives_a_zero_row_not_nan() -> None:
    row = HashingEmbedder(384).encode([""])[0]
    assert not np.isnan(row).any()
    assert float(np.linalg.norm(row)) == 0.0


def test_make_embedder_uses_hashing_by_default_and_the_configured_size() -> None:
    embedder = make_embedder(Settings(_env_file=None, embedding_dimensions=384))
    assert embedder.name == "hashing-bow-384"
    assert embedder.dim == 384


def test_to_pgvector_text_form() -> None:
    assert to_pgvector(np.array([0.5, -1.0], dtype=np.float32)) == "[0.500000,-1.000000]"

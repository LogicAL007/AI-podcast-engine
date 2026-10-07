import pytest

from podcast_engine.stages.index.service import chunk_words


def test_chunks_overlap() -> None:
    text = " ".join(str(n) for n in range(10))
    chunks = chunk_words(text, max_words=4, overlap=1)
    assert chunks[0] == "0 1 2 3"
    assert chunks[1].startswith("3 ")


def test_short_text_is_one_chunk() -> None:
    assert chunk_words("just a few words", max_words=50, overlap=5) == ["just a few words"]


def test_invalid_window_rejected() -> None:
    with pytest.raises(ValueError, match="overlap"):
        chunk_words("a b c", max_words=2, overlap=2)

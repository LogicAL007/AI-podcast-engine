from podcast_engine.stages.ingest.service import content_hash, has_changed


def test_hash_ignores_whitespace_reflow() -> None:
    assert content_hash("a  b\n c") == content_hash("a b c")


def test_has_changed() -> None:
    previous = content_hash("same text")
    assert not has_changed(previous, "same   text")
    assert has_changed(previous, "different text")
    assert has_changed(None, "anything")

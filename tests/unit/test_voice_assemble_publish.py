from podcast_engine.stages.assemble.service import needs_normalisation
from podcast_engine.stages.publish.service import AI_DISCLOSURE, with_disclosure
from podcast_engine.stages.voice.service import segment_cache_key


def test_cache_key_depends_on_provider_voice_and_text() -> None:
    base = segment_cache_key("p", "v1", "hello")
    assert base == segment_cache_key("p", "v1", "hello")
    assert base != segment_cache_key("p", "v2", "hello")
    assert base != segment_cache_key("q", "v1", "hello")
    assert base != segment_cache_key("p", "v1", "hello!")


def test_loudness_within_tolerance_is_left_alone() -> None:
    assert not needs_normalisation(-16.5)
    assert needs_normalisation(-23.0)


def test_disclosure_added_once() -> None:
    notes = with_disclosure("Notes")
    assert notes.startswith(AI_DISCLOSURE)
    assert with_disclosure(notes) == notes

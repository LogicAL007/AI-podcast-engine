from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

from podcast_engine.common.models import ExpertiseLevel, ReliabilityTier, Tone
from podcast_engine.common.repository import ShowRecord
from podcast_engine.stages.ingest.service import content_hash, has_changed, load_docs
from tests.unit.test_pdf_and_feeds import BODY, make_pdf

FACTS = (
    "Tides are the regular rise and fall of the sea. The moon's gravity pulls the ocean toward "
    "it. Most coasts see two high tides every lunar day. Spring tides happen when the sun and moon "
    "line up."
)
PAGE = (
    "<html><head><title>Tides</title></head><body><main><article><h1>Tides</h1>"
    f"<h2>How tides work</h2><p>{FACTS}</p><p>{FACTS}</p>"
    f"<h2>Where tides are largest</h2><p>{FACTS}</p><p>{FACTS}</p></article></main></body></html>"
)


def test_hash_ignores_whitespace_reflow() -> None:
    assert content_hash("a  b\n c") == content_hash("a b c")


def test_has_changed() -> None:
    previous = content_hash("same text")
    assert not has_changed(previous, "same   text")
    assert has_changed(previous, "different text")
    assert has_changed(None, "anything")


def _show(sources: list[str]) -> ShowRecord:
    return ShowRecord(
        show_id=uuid4(), topic="Tides", tone=Tone.NEUTRAL, target_minutes=3, host_count=2,
        language="en", expertise=ExpertiseLevel.INTERMEDIATE, sources=sources, topic_keywords="",
        attribution="", max_segments=6, ranking_profile="explainer",
    )  # fmt: skip


def _ctx(uploads: list[Any], files: dict[str, bytes]) -> Any:
    return SimpleNamespace(
        settings=SimpleNamespace(
            config_dir=Path("/nonexistent"),
            feed_max_items=5,
            public_feed_base_url="https://pod.example",
        ),
        fetch=lambda url: PAGE,
        repo=SimpleNamespace(list_uploads=lambda show_id: uploads),
        store=SimpleNamespace(get=lambda key: files[key]),
    )


def test_load_docs_reads_pages_and_uploads_in_order() -> None:
    # Runs the whole of load_docs, so it also fails on Python 3.12 if an annotation names a
    # type imported only for type checking (as `Section` once did, breaking every ingest).
    upload_id = UUID(int=7)
    upload = SimpleNamespace(upload_id=upload_id, object_key="u.pdf", filename="notes.pdf")
    pdf = make_pdf([[(20, "Columns"), (11, BODY)]])
    show = _show(["https://example.org/tides"])
    docs = load_docs(show, _ctx([upload], {"u.pdf": pdf}))

    assert [d.title for d in docs[:2]] == ["How tides work", "Where tides are largest"]
    assert [d.position for d in docs] == list(range(len(docs)))
    uploaded = docs[2:]
    assert uploaded
    assert all(d.reliability is ReliabilityTier.ESTABLISHED for d in uploaded)
    assert uploaded[0].url.startswith(
        f"https://pod.example/api/v1/shows/{show.show_id}/uploads/{upload_id}/file#page="
    )

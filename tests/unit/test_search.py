"""Search results as a source (FR2): the providers, and ingest reading their results."""

from typing import Any

import pytest

from podcast_engine.common.models import ReliabilityTier
from podcast_engine.stages.ingest.extract import extract_page
from podcast_engine.stages.ingest.search import (
    BraveSearch,
    SearchHit,
    WikipediaSearch,
    article_html,
    is_wikipedia_article,
    read_page,
)
from podcast_engine.stages.ingest.service import load_docs
from tests.unit.test_ingest import FACTS, _ctx, _show

ARTICLE = f"""{FACTS}

== How tides work ==
{FACTS}
=== Spring & neap tides ===
{FACTS}
== References ==
Smith, J. (2001). Tides. A list, not prose: it is dropped. {FACTS}
== See also ==
Moon
"""


def test_wikipedia_text_becomes_sections_with_its_anchors_and_edit_date() -> None:
    page = extract_page(article_html("Tide", ARTICLE, "2026-10-20T15:15:29Z"))
    assert [(s.heading, s.anchor) for s in page.sections] == [
        ("Tide", ""),
        ("How tides work", "How_tides_work"),
        ("Spring & neap tides", "Spring_&_neap_tides"),
    ]
    assert page.published_at is not None
    assert page.published_at.year == 2026


def test_wikipedia_search_uses_the_show_language_and_identifies_itself() -> None:
    calls: list[tuple[str, dict[str, Any], dict[str, str]]] = []

    def get(url: str, params: Any, headers: Any) -> Any:
        calls.append((url, dict(params), dict(headers)))
        if url.endswith("/search/page"):
            return {"pages": [{"key": "Marée", "title": "Marée"}, {"key": "Lune", "title": "Lune"}]}
        return {
            "query": {
                "pages": [
                    {"title": "Marée", "extract": ARTICLE, "revisions": [{"timestamp": None}]}
                ]
            }
        }

    wikipedia = WikipediaSearch(get)
    hits = wikipedia.search("marées", language="fr-CA", count=1)
    assert hits == [SearchHit(url="https://fr.wikipedia.org/wiki/Mar%C3%A9e", title="Marée")]
    assert calls[0][1] == {"q": "marées", "limit": 1}
    assert "github.com" in calls[0][2]["User-Agent"]  # Wikimedia asks for contact details

    assert "How tides work" in wikipedia.page(hits[0])
    url, params, _ = calls[1]
    assert url == "https://fr.wikipedia.org/w/api.php"
    assert params["titles"] == "Marée"
    assert params["explaintext"] == 1


def test_brave_needs_a_key_and_sends_it_as_a_header() -> None:
    with pytest.raises(ValueError, match="SEARCH_API_KEY"):
        BraveSearch("")
    seen: dict[str, Any] = {}

    def get(url: str, params: Any, headers: Any) -> Any:
        seen.update(url=url, params=dict(params), headers=dict(headers))
        return {"web": {"results": [{"url": "https://a.example/x", "title": "A"}]}}

    brave = BraveSearch("k", get, fetch=lambda url: f"<html>{url}</html>")
    assert brave.search("tides", language="en", count=3) == [
        SearchHit(url="https://a.example/x", title="A")
    ]
    assert seen["headers"]["X-Subscription-Token"] == "k"
    assert seen["params"] == {"q": "tides", "count": 3, "search_lang": "en"}
    assert brave.page(SearchHit(url="https://a.example/x", title="A")).startswith("<html>")


class FakeSearch:
    def __init__(self, hits: list[SearchHit], broken: frozenset[str] = frozenset()) -> None:
        self.hits = hits
        self.broken = broken
        self.queries: list[str] = []

    def search(self, query: str, *, language: str, count: int) -> list[SearchHit]:
        self.queries.append(query)
        return self.hits[:count]

    def page(self, hit: SearchHit) -> str:
        if hit.url in self.broken:
            raise OSError("blocked")
        return article_html(hit.title, ARTICLE, "2026-10-20T15:15:29Z")


def test_ingest_reads_search_results_after_the_show_pages() -> None:
    own = "https://example.org/tides"
    search = FakeSearch(
        [
            SearchHit(url=own, title="Already a source"),  # not read twice
            SearchHit(url="https://en.wikipedia.org/wiki/Tide", title="Tide"),
            SearchHit(url="https://broken.example/tide", title="Unreadable"),  # skipped
        ],
        broken=frozenset({"https://broken.example/tide"}),
    )
    show = _show([own]).model_copy(update={"search_queries": ["ocean tides"]})
    ctx = _ctx([], {})
    ctx.search = search
    ctx.settings.search_results = 5
    docs = load_docs(show, ctx)

    assert search.queries == ["ocean tides"]
    from_search = [d for d in docs if "wikipedia.org" in d.url]
    assert [d.url for d in from_search] == [
        "https://en.wikipedia.org/wiki/Tide",
        "https://en.wikipedia.org/wiki/Tide#How_tides_work",
        "https://en.wikipedia.org/wiki/Tide#Spring_&_neap_tides",
    ]
    assert docs.index(from_search[0]) > 0  # after the show's own page
    assert not any("broken.example" in d.url for d in docs)
    assert from_search[0].published_at is not None


def test_wikipedia_ranks_as_an_established_source() -> None:
    from pathlib import Path

    import yaml

    from podcast_engine.stages.ingest.extract import source_tier

    tiers = yaml.safe_load(Path("config/source_tiers.yaml").read_text(encoding="utf-8"))
    assert source_tier("https://fr.wikipedia.org/wiki/Mar%C3%A9e", tiers) is (
        ReliabilityTier.ESTABLISHED
    )


def test_a_wikipedia_url_is_read_through_the_api() -> None:
    def get(url: str, params: Any, headers: Any) -> Any:
        assert url == "https://en.wikipedia.org/w/api.php"
        assert params["titles"] == "Lake_Superior"
        return {
            "query": {
                "pages": [
                    {
                        "title": "Lake Superior",
                        "extract": ARTICLE,
                        "revisions": [{"timestamp": "2026-10-30T09:00:00Z"}],
                    }
                ]
            }
        }

    html = read_page("https://en.wikipedia.org/wiki/Lake_Superior", wikipedia=WikipediaSearch(get))
    page = extract_page(html)
    assert page.sections[1].anchor == "How_tides_work"
    assert page.published_at is not None
    assert page.published_at.year == 2026
    assert is_wikipedia_article("https://fr.wikipedia.org/wiki/Mar%C3%A9e")
    assert not is_wikipedia_article("https://en.wikipedia.org/wiki/")
    assert not is_wikipedia_article("https://en.wikipedia.org/w/index.php?title=Tide")
    assert not is_wikipedia_article("https://example.org/wiki/Tide")

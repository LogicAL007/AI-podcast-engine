"""Search results as a source (FR2): the top results for a show's searches, read as pages.

Each time an episode is made, ingest runs the show's searches and reads the top results like the
show's own URLs, so every section is citable and change-detected; a refresh that finds new results
regenerates the segments they feed. Two providers:

- ``wikipedia`` (the default, no key): Wikipedia's search API, in the show's language. A result is
  read through the API as plain text, so it carries no menus or reference markers, and dated by
  its last edit (a page's own date is when it was created, which would rank it as stale).
- ``brave`` (needs ``SEARCH_API_KEY``, paid): Brave's web search; results are fetched as pages.
"""

import re
from collections.abc import Callable, Mapping
from html import escape
from typing import Any, Protocol
from urllib.parse import quote, unquote, urlsplit

from pydantic import BaseModel, ConfigDict

from podcast_engine.common.config import Settings
from podcast_engine.stages.ingest.extract import USER_AGENT, fetch_html

# Wikimedia asks API clients to say who they are and how to reach the project.
SEARCH_USER_AGENT = f"{USER_AGENT[:-1]}; https://github.com/LogicAL007/AI-podcast-engine)"
# Sections that list other works rather than say anything.
_SKIP = {
    "see also",
    "references",
    "notes",
    "external links",
    "further reading",
    "bibliography",
    "sources",
    "citations",
    "footnotes",
}
_HEADING = re.compile(r"^(={2,6})\s*(.*?)\s*\1\s*$")

GetJson = Callable[[str, Mapping[str, Any], Mapping[str, str]], Any]


class SearchHit(BaseModel):
    model_config = ConfigDict(frozen=True)

    url: str
    title: str


class SearchProvider(Protocol):
    def search(self, query: str, *, language: str, count: int) -> list[SearchHit]: ...

    def page(self, hit: SearchHit) -> str:
        """The result as HTML, for the page extractor."""
        ...


def get_json(url: str, params: Mapping[str, Any], headers: Mapping[str, str]) -> Any:
    """GET a JSON API. Raises for network errors and non-2xx responses."""
    import httpx

    response = httpx.get(url, params=params, headers=dict(headers), timeout=30.0)
    response.raise_for_status()
    return response.json()


class WikipediaSearch:
    def __init__(self, get: GetJson = get_json) -> None:
        self._get = get

    @staticmethod
    def _site(language: str) -> str:
        return f"https://{language.split('-')[0]}.wikipedia.org"

    def search(self, query: str, *, language: str, count: int) -> list[SearchHit]:
        site = self._site(language)
        found = self._get(
            f"{site}/w/rest.php/v1/search/page",
            {"q": query, "limit": count},
            {"User-Agent": SEARCH_USER_AGENT},
        )
        return [
            SearchHit(url=f"{site}/wiki/{quote(page['key'], safe='')}", title=page["title"])
            for page in found.get("pages", [])[:count]
        ]

    def page(self, hit: SearchHit) -> str:
        parts = urlsplit(hit.url)
        found = self._get(
            f"{parts.scheme}://{parts.netloc}/w/api.php",
            {
                "action": "query",
                "prop": "extracts|revisions",
                "explaintext": 1,
                "exsectionformat": "wiki",
                "rvprop": "timestamp",
                "titles": unquote(parts.path.removeprefix("/wiki/")),
                "redirects": 1,
                "format": "json",
                "formatversion": 2,
            },
            {"User-Agent": SEARCH_USER_AGENT},
        )
        page = found["query"]["pages"][0]
        revisions = page.get("revisions") or [{}]
        return article_html(page["title"], page.get("extract", ""), revisions[0].get("timestamp"))


def article_html(title: str, text: str, edited: str | None) -> str:
    """Wikipedia's plain text (``== Heading ==`` lines) as a page the extractor splits into
    sections, each with the anchor Wikipedia gives that heading, minus the reference lists."""
    head = f'<meta property="article:modified_time" content="{escape(edited)}">' if edited else ""
    body: list[str] = []
    skipping = False
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        heading = _HEADING.match(line)
        if heading:
            name = heading.group(2)
            skipping = name.lower() in _SKIP
            if not skipping:
                anchor = escape(name.replace(" ", "_"), quote=True)
                body.append(f'<h2 id="{anchor}">{escape(name)}</h2>')
        elif not skipping:
            body.append(f"<p>{escape(line)}</p>")
    return (
        f"<html><head><title>{escape(title)}</title>{head}</head>"
        f"<body><article>{''.join(body)}</article></body></html>"
    )


class BraveSearch:
    def __init__(
        self, api_key: str, get: GetJson = get_json, fetch: Callable[[str], str] = fetch_html
    ) -> None:
        if not api_key:
            raise ValueError("SEARCH_PROVIDER is brave, but SEARCH_API_KEY is not set")
        self._key = api_key
        self._get = get
        self._fetch = fetch

    def search(self, query: str, *, language: str, count: int) -> list[SearchHit]:
        found = self._get(
            "https://api.search.brave.com/res/v1/web/search",
            {"q": query, "count": count, "search_lang": language.split("-")[0]},
            {"Accept": "application/json", "X-Subscription-Token": self._key},
        )
        results = (found.get("web") or {}).get("results", [])
        return [SearchHit(url=r["url"], title=r.get("title", "")) for r in results[:count]]

    def page(self, hit: SearchHit) -> str:
        return self._fetch(hit.url)


def is_wikipedia_article(url: str) -> bool:
    parts = urlsplit(url)
    title = parts.path.removeprefix("/wiki/")
    return parts.netloc.endswith(".wikipedia.org") and title not in ("", parts.path)


def read_page(url: str, *, wikipedia: WikipediaSearch | None = None) -> str:
    """A show URL's HTML. A Wikipedia article is read through the API, as a search result is, so
    a page the creator pasted carries no menus or reference markers either and is dated by its
    last edit, not its creation."""
    if is_wikipedia_article(url):
        return (wikipedia or WikipediaSearch()).page(SearchHit(url=url, title=""))
    return fetch_html(url)


def make_search(settings: Settings) -> SearchProvider | None:
    """The configured provider, or None when searches are off."""
    if settings.search_provider == "wikipedia":
        return WikipediaSearch()
    if settings.search_provider == "brave":
        return BraveSearch(settings.search_api_key.get_secret_value())
    return None

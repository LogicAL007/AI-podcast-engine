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
    """One search result: its URL and title."""

    model_config = ConfigDict(frozen=True)

    url: str
    title: str


class SearchProvider(Protocol):
    """Search results as a source (FR2): the top results for a show's searches.

    Each time an episode is made, ingest runs the show's searches and reads the top results like the
    show's own URLs, so every section is citable and change-detected; a refresh that finds new
    results regenerates the segments they feed. Two providers:

    - ``wikipedia`` (the default, no key): Wikipedia's search API, in the show's language.
    - ``brave`` (needs ``SEARCH_API_KEY``, paid): Brave's web search; results are fetched as pages.
    """

    def search(self, query: str, *, language: str, count: int) -> list[SearchHit]:
        """Return the top results for a query.

        Args:
            query: What to search for.
            language: The show's language, such as ``en`` or ``fr-CA``.
            count: Most results to return.

        Returns:
            The results, best first.
        """
        ...

    def page(self, hit: SearchHit) -> str:
        """Return a result as HTML, for the page extractor.

        Args:
            hit: The result.

        Returns:
            The result's HTML.
        """
        ...


def get_json(url: str, params: Mapping[str, Any], headers: Mapping[str, str]) -> Any:
    """GET a JSON API.

    Args:
        url: The endpoint.
        params: The query parameters.
        headers: The request headers.

    Returns:
        The decoded JSON.

    Raises:
        httpx.HTTPError: A network error or a non-2xx response.
    """
    import httpx

    response = httpx.get(url, params=params, headers=dict(headers), timeout=30.0)
    response.raise_for_status()
    return response.json()


class WikipediaSearch:
    """Wikipedia's search, with articles read through its API.

    A result is read as plain text, so it carries no menus or reference markers, and is dated by its
    last edit (a page's own date is when it was created, which would rank it as stale). Wikimedia
    asks API clients to say who they are, so requests carry a descriptive User-Agent.
    """

    def __init__(self, get: GetJson = get_json) -> None:
        """Create the provider.

        Args:
            get: Fetches JSON; replaced in tests.
        """
        self._get = get

    @staticmethod
    def _site(language: str) -> str:
        """Return the Wikipedia for a language.

        Args:
            language: A language code, such as ``en`` or ``fr-CA``.

        Returns:
            The site's base URL.
        """
        return f"https://{language.split('-')[0]}.wikipedia.org"

    def search(self, query: str, *, language: str, count: int) -> list[SearchHit]:
        """Search Wikipedia in the show's language.

        Args:
            query: What to search for.
            language: The show's language.
            count: Most results to return.

        Returns:
            The matching articles, best first.
        """
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
        """Read an article through the API, as plain text with its headings and last edit.

        Args:
            hit: The article.

        Returns:
            The article as HTML, from ``article_html``.
        """
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
    """Turn Wikipedia's plain text into a page the extractor splits into sections.

    Each ``== Heading ==`` line becomes a heading with the anchor Wikipedia gives it. Sections that
    list other works rather than say anything (references, further reading) are left out.

    Args:
        title: The article's title.
        text: The article's plain text.
        edited: When it was last edited, or None.

    Returns:
        The article as HTML, with its edit date as a meta tag.
    """
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
    """Brave's web search (paid, needs ``SEARCH_API_KEY``); results are fetched as pages."""

    def __init__(
        self, api_key: str, get: GetJson = get_json, fetch: Callable[[str], str] = fetch_html
    ) -> None:
        """Create the provider.

        Args:
            api_key: The Brave Search API key.
            get: Fetches JSON; replaced in tests.
            fetch: Fetches a page's HTML; replaced in tests.

        Raises:
            ValueError: No API key is set.
        """
        if not api_key:
            raise ValueError("SEARCH_PROVIDER is brave, but SEARCH_API_KEY is not set")
        self._key = api_key
        self._get = get
        self._fetch = fetch

    def search(self, query: str, *, language: str, count: int) -> list[SearchHit]:
        """Search the web with Brave.

        Args:
            query: What to search for.
            language: The show's language; only its primary subtag is sent.
            count: Most results to return.

        Returns:
            The results, best first.
        """
        found = self._get(
            "https://api.search.brave.com/res/v1/web/search",
            {"q": query, "count": count, "search_lang": language.split("-")[0]},
            {"Accept": "application/json", "X-Subscription-Token": self._key},
        )
        results = (found.get("web") or {}).get("results", [])
        return [SearchHit(url=r["url"], title=r.get("title", "")) for r in results[:count]]

    def page(self, hit: SearchHit) -> str:
        """Fetch a result's page.

        Args:
            hit: The result.

        Returns:
            The page's HTML.
        """
        return self._fetch(hit.url)


def is_wikipedia_article(url: str) -> bool:
    """Tell whether a URL is a Wikipedia article.

    Args:
        url: The URL.

    Returns:
        True for ``https://<lang>.wikipedia.org/wiki/<title>``.
    """
    parts = urlsplit(url)
    title = parts.path.removeprefix("/wiki/")
    return parts.netloc.endswith(".wikipedia.org") and title not in ("", parts.path)


def read_page(url: str, *, wikipedia: WikipediaSearch | None = None) -> str:
    """Fetch a show URL's HTML.

    A Wikipedia article is read through the API, as a search result is, so a page the creator pasted
    carries no menus or reference markers either and is dated by its last edit, not its creation.

    Args:
        url: The page.
        wikipedia: The Wikipedia reader to use; a new one when None.

    Returns:
        The page's HTML.
    """
    if is_wikipedia_article(url):
        return (wikipedia or WikipediaSearch()).page(SearchHit(url=url, title=""))
    return fetch_html(url)


def make_search(settings: Settings) -> SearchProvider | None:
    """Return the configured search provider.

    Args:
        settings: The search provider setting and its API key.

    Returns:
        The provider, or None when searches are off.
    """
    if settings.search_provider == "wikipedia":
        return WikipediaSearch()
    if settings.search_provider == "brave":
        return BraveSearch(settings.search_api_key.get_secret_value())
    return None

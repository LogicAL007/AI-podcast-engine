import re
from collections.abc import Mapping
from datetime import UTC, datetime
from urllib.parse import urlsplit

from lxml import html
from pydantic import BaseModel, ConfigDict

from podcast_engine.common.models import ReliabilityTier
from podcast_engine.common.text import speakable_sentences

USER_AGENT = "podcast-engine/0.1 (research prototype)"
MIN_SECTION_SENTENCES = 2

# Containers that never hold the article's prose.
_DROP = (
    ".//script|.//style|.//nav|.//aside|.//footer|.//svg|.//pre|.//button|.//table|.//noscript"
    "|.//form|.//img"
)
# Innermost blocks of prose: paragraphs, list items, and the span-based paragraphs some sites use.
_BLOCK = (
    "self::h1 or self::h2 or self::h3 or self::h4 or self::p or self::li"
    " or @data-as='p' or @data-as='li'"
)
_HEADING = re.compile(r"h[1-4]")
__all__ = ["extract_page", "fetch_html", "source_tier", "speakable_sentences"]

_SKIP_HEADINGS = {
    "documentation index",
    "on this page",
    "was this page helpful?",
    "table of contents",
}
_META_DATES = (
    "article:modified_time",
    "og:updated_time",
    "article:published_time",
)


class Section(BaseModel):
    """One titled part of a source: the unit that is cited and change-detected.

    Each section becomes its own source: it has its own content hash, so a change on the page
    re-runs only the segment built from that section, and its own anchor (the heading's id on the
    page, or empty for the lead-in), so a citation can link to it. ``text`` holds paragraphs
    separated by blank lines.
    """

    model_config = ConfigDict(frozen=True)

    heading: str
    anchor: str
    text: str

    @property
    def words(self) -> int:
        """The section's length in words."""
        return len(self.text.split())


class ExtractedPage(BaseModel):
    """A page split into sections, with its title and date.

    ``dropped`` lists the headings whose sections had too little speakable text, so omissions are
    visible.
    """

    model_config = ConfigDict(frozen=True)

    title: str
    published_at: datetime | None
    sections: tuple[Section, ...]
    dropped: tuple[str, ...] = ()


def fetch_html(url: str, *, timeout: float = 30.0) -> str:
    """Download a page, following redirects.

    Args:
        url: The page's address.
        timeout: Seconds to wait before giving up.

    Returns:
        The page's HTML.

    Raises:
        httpx.HTTPError: A network error or a non-2xx response.
    """
    import httpx

    response = httpx.get(
        url, timeout=timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT}
    )
    response.raise_for_status()
    return response.text


def _parse_date(value: str) -> datetime | None:
    """Parse an ISO 8601 date, assuming UTC when it has no timezone.

    Args:
        value: The date as written on the page.

    Returns:
        The date, or None when it cannot be parsed.
    """
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _published(doc: html.HtmlElement, page_html: str) -> datetime | None:
    """Find when a page was last modified.

    Looks in the date meta tags first, else in an embedded ``"dateModified"`` or ``"datePublished"``
    field.

    Args:
        doc: The parsed page.
        page_html: The page's HTML, searched for embedded fields.

    Returns:
        The date in UTC, or None when the page gives none.
    """
    for name in _META_DATES:
        for value in doc.xpath(f"//meta[@property='{name}' or @name='{name}']/@content"):
            if (parsed := _parse_date(str(value))) is not None:
                return parsed
    match = re.search(r'"date(?:Modified|Published)"\s*:\s*"([^"]{8,40})"', page_html)
    return _parse_date(match.group(1)) if match else None


def _clean(text: str) -> str:
    """Tidy a block's text for speaking.

    Removes zero-width spaces, trademark signs and the "¶" heading permalink that Sphinx and MkDocs
    sites print (it is read aloud otherwise), drops "Direct link to ..." labels and collapses
    whitespace.

    Args:
        text: The block's text.

    Returns:
        The cleaned text.
    """
    text = text.replace("​", " ").replace("®", "").replace("™", "").replace("¶", "")
    text = re.sub(r"Direct link to .*$", "", " ".join(text.split()))
    return text.strip()


def extract_page(page_html: str) -> ExtractedPage:
    """Split a web page into sections at its h1 to h3 headings, keeping speakable ones (FR2).

    Documentation sites differ in markup (some use ``<p>``, others ``<span data-as="p">``), and a
    generic article extractor can silently drop most of a page. So this keeps every heading,
    paragraph and list item inside ``<article>`` or ``<main>`` (else ``<body>``), counting only
    innermost blocks so nothing is counted twice. Navigation and other boilerplate are removed
    first, and headings that are boilerplate themselves (such as "On this page") are skipped as
    whole sections, so their text cannot leak into the one before. Callers should treat "headings
    but little text" as a failure.

    Args:
        page_html: The page's HTML.

    Returns:
        The page's title, date and sections, and the headings dropped for too little text.
    """
    doc = html.fromstring(page_html)
    title = " ".join((doc.findtext(".//title") or "").split())
    roots = doc.xpath("//article") or doc.xpath("//main") or doc.xpath("//body")
    if not roots:
        return ExtractedPage(title=title, published_at=None, sections=())
    root = roots[0]
    for node in root.xpath(_DROP):
        node.drop_tree()

    raw: list[tuple[str, str, list[str]]] = []
    heading, anchor, paragraphs = title, "", list[str]()
    for element in root.xpath(f".//*[{_BLOCK}]"):
        if element.xpath(f".//*[{_BLOCK}]"):
            continue
        text = _clean(element.text_content())
        if not text:
            continue
        if _HEADING.fullmatch(element.tag) and element.tag != "h4":
            raw.append((heading, anchor, paragraphs))
            heading, anchor, paragraphs = text, element.get("id", ""), []
        else:
            paragraphs.append(text)
    raw.append((heading, anchor, paragraphs))

    sections = []
    dropped = []
    for head, anchor_id, paras in raw:
        if head.lower() in _SKIP_HEADINGS:
            continue
        body = "\n\n".join(paras)
        if len(speakable_sentences(body)) >= MIN_SECTION_SENTENCES:
            sections.append(Section(heading=head, anchor=anchor_id, text=body))
        elif paras:
            dropped.append(head)
    return ExtractedPage(
        title=title,
        published_at=_published(doc, page_html),
        sections=tuple(sections),
        dropped=tuple(dropped),
    )


def source_tier(url: str, tiers: Mapping[str, object]) -> ReliabilityTier:
    """Look up a URL's reliability tier.

    Uses the domain lists in ``config/source_tiers.yaml``; a subdomain counts as its domain.

    Args:
        url: The source's address.
        tiers: The tiers file: domain lists for ``primary`` and ``established``, and a ``default``.

    Returns:
        The tier, else the file's default, else ``unverified``.
    """
    host = (urlsplit(url).hostname or "").lower()
    for tier in (ReliabilityTier.PRIMARY, ReliabilityTier.ESTABLISHED):
        domains = tiers.get(tier.value) or []
        if isinstance(domains, list) and any(
            host == str(d) or host.endswith("." + str(d)) for d in domains
        ):
            return tier
    return ReliabilityTier(str(tiers.get("default", ReliabilityTier.UNVERIFIED.value)))

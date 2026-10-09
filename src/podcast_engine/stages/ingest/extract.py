"""Turn a web page into titled sections of text that can be spoken aloud (FR2, URL sources).

Each section becomes its own source: it has its own content hash, so a change on the page re-runs
only the segment built from that section, and its own anchor, so a citation can link to it.

Documentation sites differ in markup (some use ``<p>``, others ``<span data-as="p">``), and a
generic article extractor can silently drop most of a page. So this keeps every heading,
paragraph and list item inside ``<article>``/``<main>``. Callers should treat "headings but little
text" as a failure.
"""

import re
from collections.abc import Mapping
from datetime import UTC, datetime
from urllib.parse import urlsplit

from lxml import html
from pydantic import BaseModel, ConfigDict

from podcast_engine.common.models import ReliabilityTier

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
_SKIP_HEADINGS = {
    "documentation index",
    "on this page",
    "was this page helpful?",
    "table of contents",
}
# Sentences that only make sense with the picture, link or page in front of you.
_VISUAL = re.compile(
    r"\b(diagram|screenshot|figure|the above|the following|shown below|as shown|see below|click"
    r"|see the|learn more|read more|refer to)\b",
    re.IGNORECASE,
)
# A section cannot open on a sentence that leans on the text before it ("Such a level of ...").
_DANGLING_OPENER = re.compile(
    r"^(such|this|these|those|that|it|they|here|however|additionally|also|moreover|then)\b",
    re.IGNORECASE,
)
_META_DATES = (
    "article:modified_time",
    "og:updated_time",
    "article:published_time",
)


class Section(BaseModel):
    model_config = ConfigDict(frozen=True)

    heading: str
    anchor: str  # the heading's id on the page, or "" for the lead-in
    text: str  # paragraphs separated by blank lines

    @property
    def words(self) -> int:
        return len(self.text.split())


class ExtractedPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str
    published_at: datetime | None
    sections: tuple[Section, ...]
    dropped: tuple[
        str, ...
    ] = ()  # headings with too little speakable text, so omissions are visible


def fetch_html(url: str, *, timeout: float = 30.0) -> str:
    """Download a page. Raises for network errors and non-2xx responses."""
    import httpx

    response = httpx.get(
        url, timeout=timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT}
    )
    response.raise_for_status()
    return response.text


def _words(sentence: str) -> frozenset[str]:
    return frozenset(re.findall(r"[a-z0-9]+", sentence.lower()))


def _repeats(sentence: str, kept: list[frozenset[str]]) -> bool:
    """True if almost the same sentence was already kept (pages often repeat their tagline)."""
    words = _words(sentence)
    return any(len(words & other) / len(words | other) >= 0.8 for other in kept)


def speakable_sentences(text: str) -> list[str]:
    """Whole sentences that read naturally aloud, in order.

    Drops labels and lead-ins (a paragraph must end in a full stop), code-like fragments, and
    sentences that point at a diagram or link, near-repeats of a sentence already kept, and an
    opening sentence that depends on text before the section ("Such a level of ...").
    This is a heuristic: it errs toward dropping.
    """
    sentences: list[str] = []
    kept: list[frozenset[str]] = []
    for paragraph in re.split(r"\n\s*\n", text):
        paragraph = " ".join(paragraph.split())
        if len(paragraph.split()) < 6 or paragraph[-1] not in ".!?":
            continue
        # Split only before a capital, so "e.g. aggregations" is not cut in two.
        for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z“\"'(])", paragraph):
            sentence = sentence.strip()
            if (
                len(sentence.split()) >= 5
                and sentence[0].isupper()
                and sentence[-1] in ".!?"
                and not _VISUAL.search(sentence)
                and not any(char in sentence for char in "{}|`<>")
                and not _repeats(sentence, kept)
                and not (not sentences and _DANGLING_OPENER.match(sentence))
            ):
                sentences.append(sentence)
                kept.append(_words(sentence))
    return sentences


def _parse_date(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _published(doc: html.HtmlElement, page_html: str) -> datetime | None:
    """The page's modified date: from meta tags, else from an embedded ``"dateModified"`` field."""
    for name in _META_DATES:
        for value in doc.xpath(f"//meta[@property='{name}' or @name='{name}']/@content"):
            if (parsed := _parse_date(str(value))) is not None:
                return parsed
    match = re.search(r'"date(?:Modified|Published)"\s*:\s*"([^"]{8,40})"', page_html)
    return _parse_date(match.group(1)) if match else None


def _clean(text: str) -> str:
    text = text.replace("​", " ").replace("®", "").replace("™", "")
    text = re.sub(r"Direct link to .*$", "", " ".join(text.split()))
    return text.strip()


def extract_page(page_html: str) -> ExtractedPage:
    """Split a page into sections at its h1 to h3 headings, keeping only speakable ones."""
    doc = html.fromstring(page_html)
    title = " ".join((doc.findtext(".//title") or "").split())
    roots = doc.xpath("//article") or doc.xpath("//main") or doc.xpath("//body")
    if not roots:
        return ExtractedPage(title=title, published_at=None, sections=())
    root = roots[0]
    for node in root.xpath(_DROP):
        node.drop_tree()

    raw: list[tuple[str, str, list[str]]] = []  # (heading, anchor, paragraphs)
    heading, anchor, paragraphs = title, "", list[str]()
    for element in root.xpath(f".//*[{_BLOCK}]"):
        if element.xpath(f".//*[{_BLOCK}]"):  # only innermost blocks, so nothing is counted twice
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
        if (
            head.lower() in _SKIP_HEADINGS
        ):  # its own section, so its text cannot leak into the previous one
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
    """Reliability tier for a URL, from the domain lists in config/source_tiers.yaml."""
    host = (urlsplit(url).hostname or "").lower()
    for tier in (ReliabilityTier.PRIMARY, ReliabilityTier.ESTABLISHED):
        domains = tiers.get(tier.value) or []
        if isinstance(domains, list) and any(
            host == str(d) or host.endswith("." + str(d)) for d in domains
        ):
            return tier
    return ReliabilityTier(str(tiers.get("default", ReliabilityTier.UNVERIFIED.value)))

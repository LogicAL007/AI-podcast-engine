"""Word-level text helpers shared by the embedder and the offline fact-check."""

import hashlib
import re

from stop_words import get_stop_words

# The `stop_words` package's English list. It is large, so what remains is the content words.
STOPWORDS: frozenset[str] = frozenset(get_stop_words("en"))

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


def stem(token: str) -> str:
    """A crude stemmer: enough to match "stored" with "storing" and "columns" with "column"."""
    for suffix in ("ing", "ed", "es", "s"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            return token[: -len(suffix)]
    return token


def content_tokens(text: str) -> list[str]:
    """Lower-cased, stemmed words with stop words and very short words removed."""
    return [
        stem(token)
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if token not in STOPWORDS and len(token) > 2
    ]


def content_hash(text: str) -> str:
    """Hash of whitespace-normalised text, so reflowed but identical content is unchanged."""
    normalised = " ".join(text.split())
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


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

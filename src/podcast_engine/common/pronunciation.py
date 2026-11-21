"""Spoken forms for written terms a voice model would misread.

The entries are in ``config/pronunciation_lexicon.yaml``.

Applied only to the text a voice speaks, and to its cache key, never to the script: the script
page, transcripts and the fact-check keep the written form ("SQL", "e.g."), while the voice says
"sequel" and "for example". Changing an entry re-voices only the lines it changes.

Matching rules:
- Longest entries first, so "Sault Ste. Marie" wins over shorter entries inside it.
- An entry with a capital letter (an acronym or a name) matches only in that case: "SQL", not
  "sql". An all-lowercase entry ("e.g.", "vs.") matches in any case.
- Words match whole, never inside another word. An entry that starts with a symbol ("%", "°C",
  "km²") also matches right after a number ("40%", "35°C").
"""

import re
from functools import lru_cache, partial
from pathlib import Path

import yaml

LEXICON_FILE = "pronunciation_lexicon.yaml"

Rule = tuple[re.Pattern[str], str]


def compile_rules(entries: dict[str, str]) -> tuple[Rule, ...]:
    rules = []
    for written in sorted(entries, key=len, reverse=True):
        said = str(entries[written])
        before = r"(?<![\w-])" if re.match(r"\w", written) else ""
        after = r"(?![\w-])" if re.search(r"\w$", written) else r"(?!\w)"
        flags = 0 if any(c.isupper() for c in written) else re.IGNORECASE
        rules.append((re.compile(before + re.escape(written) + after, flags), said.strip()))
    return tuple(rules)


@lru_cache(maxsize=8)
def load_rules(path: Path) -> tuple[Rule, ...]:
    """The lexicon's rules; an absent or empty file gives none (the text is spoken as written)."""
    if not path.is_file():
        return ()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = raw.get("lexicon") or {}
    if not isinstance(entries, dict):
        raise ValueError(f"{path}: 'lexicon' must map written forms to spoken forms")
    return compile_rules({str(k): str(v) for k, v in entries.items()})


def spoken(text: str, rules: tuple[Rule, ...]) -> str:
    """``text`` with each lexicon entry replaced by its spoken form."""
    if not rules:
        return text
    out = text
    for pattern, said in rules:
        out = pattern.sub(partial(_say, said=said), out)
    out = re.sub(r"\s+([,.;:!?])", r"\1", out)  # no space before punctuation
    return " ".join(out.split())


def _say(match: re.Match[str], *, said: str) -> str:
    """The spoken form, spaced from its neighbours ("40%" -> "40 percent"). A term ending in a
    full stop that also ended the sentence ("in the U.S.") keeps the stop."""
    ends = match.group(0).endswith(".") and match.string[match.end() :].strip() == ""
    return f" {said}{'.' if ends else ''} "


def rules_for(config_dir: Path) -> tuple[Rule, ...]:
    return load_rules(config_dir / LEXICON_FILE)

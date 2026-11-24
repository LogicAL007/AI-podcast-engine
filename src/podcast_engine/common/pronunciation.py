import re
from functools import lru_cache, partial
from pathlib import Path

import yaml

LEXICON_FILE = "pronunciation_lexicon.yaml"

Rule = tuple[re.Pattern[str], str]


def compile_rules(entries: dict[str, str]) -> tuple[Rule, ...]:
    """Turn lexicon entries into ordered replacement rules.

    Matching rules:

    - Longest entries first, so "Sault Ste. Marie" wins over shorter entries inside it.
    - An entry with a capital letter (an acronym or a name) matches only in that case: "SQL", not
      "sql". An all-lowercase entry ("e.g.", "vs.") matches in any case.
    - Words match whole, never inside another word. An entry that starts with a symbol ("%", "°C",
      "km²") also matches right after a number ("40%", "35°C").

    Args:
        entries: Each written form and the way it should be said.

    Returns:
        (pattern, spoken form) pairs, longest written form first.
    """
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
    """Load the rules of a pronunciation lexicon file.

    The file maps written forms to spoken ones under a ``lexicon`` key. Results are cached per path.

    Args:
        path: The lexicon YAML file.

    Returns:
        The compiled rules; none when the file is absent or empty, so text is spoken as written.

    Raises:
        ValueError: ``lexicon`` is not a mapping of written forms to spoken forms.
    """
    if not path.is_file():
        return ()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = raw.get("lexicon") or {}
    if not isinstance(entries, dict):
        raise ValueError(f"{path}: 'lexicon' must map written forms to spoken forms")
    return compile_rules({str(k): str(v) for k, v in entries.items()})


def spoken(text: str, rules: tuple[Rule, ...]) -> str:
    """Replace each lexicon entry in a line with its spoken form.

    Applied only to the text a voice speaks, and to its cache key, never to the script: the script
    page, transcripts and the fact-check keep the written form ("SQL", "e.g."), while the voice says
    "sequel" and "for example". Changing an entry re-voices only the lines it changes. Spaces left
    before punctuation are removed and runs of whitespace collapsed.

    Args:
        text: The line as written.
        rules: The lexicon's rules, from ``rules_for``.

    Returns:
        The line as the voice should say it.
    """
    if not rules:
        return text
    out = text
    for pattern, said in rules:
        out = pattern.sub(partial(_say, said=said), out)
    out = re.sub(r"\s+([,.;:!?])", r"\1", out)
    return " ".join(out.split())


def _say(match: re.Match[str], *, said: str) -> str:
    """Return the spoken form, spaced from its neighbours.

    "40%" becomes "40 percent". A term ending in a full stop that also ended the sentence ("in the
    U.S.") keeps the stop.

    Args:
        match: Where the written form was found.
        said: Its spoken form.

    Returns:
        The spoken form with a space on each side.
    """
    ends = match.group(0).endswith(".") and match.string[match.end() :].strip() == ""
    return f" {said}{'.' if ends else ''} "


def rules_for(config_dir: Path) -> tuple[Rule, ...]:
    """Return the pronunciation rules from a config folder's lexicon.

    The entries are in ``config/pronunciation_lexicon.yaml``.

    Args:
        config_dir: The folder holding ``pronunciation_lexicon.yaml``.

    Returns:
        The compiled rules; none when the file is missing.
    """
    return load_rules(config_dir / LEXICON_FILE)

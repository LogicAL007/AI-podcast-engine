"""The pronunciation lexicon: what a voice says in place of written terms it would misread."""

from pathlib import Path

import pytest

from podcast_engine.common.pronunciation import compile_rules, load_rules, spoken

CONFIG = Path(__file__).resolve().parents[2] / "config"
RULES = load_rules(CONFIG / "pronunciation_lexicon.yaml")


@pytest.mark.parametrize(
    ("written", "said"),
    [
        (
            "It stores data by column, e.g. in SQL tables.",
            "It stores data by column, for example in sequel tables.",
        ),
        ("Superior vs. Huron", "Superior versus Huron"),
        ("About 40% of it, at 35°C.", "About 40 percent of it, at 35 degrees Celsius."),
        ("It covers 82,000 km² in total.", "It covers 82,000 square kilometres in total."),
        ("The JWST sits at L2.", "The J W S T sits at L two."),
        ("It drains through Sault Ste. Marie.", "It drains through Soo Saint Marie."),
        ("It runs in the U.S.", "It runs in the U S."),
        ("An OLAP database, not OLTP.", "An oh-lap database, not O L T P."),
    ],
)
def test_written_terms_are_said_aloud(written: str, said: str) -> None:
    assert spoken(written, RULES) == said


def test_only_whole_words_and_acronyms_in_their_own_case() -> None:
    rules = compile_rules({"AI": "A I", "etc.": "and so on"})
    assert spoken("OpenAI said hair and AI-ready", rules) == "OpenAI said hair and AI-ready"
    assert spoken("Use ai tools, AI tools, ETC.", rules) == "Use ai tools, A I tools, and so on."


def test_plain_text_and_a_missing_lexicon_pass_through(tmp_path: Path) -> None:
    assert spoken("Lake Superior is deep.", RULES) == "Lake Superior is deep."
    assert load_rules(tmp_path / "absent.yaml") == ()
    assert spoken("e.g. SQL", ()) == "e.g. SQL"

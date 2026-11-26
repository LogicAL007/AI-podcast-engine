"""The prompt files: every version in use exists and has the shared sections, and the experiment
conditions differ only where they are meant to (prompts/README.md)."""

import re
from pathlib import Path

import pytest

from podcast_engine.common.context import PROMPT_VERSIONS
from podcast_engine.stages.script.service import load_prompt

PROMPTS = Path(__file__).resolve().parents[2] / "prompts"
UNGROUNDED = ("script_ungrounded", 3)  # research/evaluation/rq1_claim_audit/generate.py


def sections(text: str) -> dict[str, str]:
    parts = re.split(r"^# (.+)$", text, flags=re.MULTILINE)
    return {
        title.strip(): body.strip() for title, body in zip(parts[1::2], parts[2::2], strict=True)
    }


@pytest.mark.parametrize("name", sorted(PROMPT_VERSIONS))
def test_each_prompt_in_use_has_the_shared_sections(name: str) -> None:
    found = sections(load_prompt(PROMPTS, name, PROMPT_VERSIONS[name]))
    assert {"Task", "What you receive"} <= set(found)
    examples = [body for title, body in found.items() if title.startswith("Example")]
    assert examples, f"{name} has no examples"
    assert examples[0], f"{name} has an empty examples section"


def test_only_the_prompts_in_use_are_kept() -> None:
    kept = {p.name for p in PROMPTS.glob("*.md")} - {"README.md"}
    in_use = {f"{name}.v{version}.md" for name, version in PROMPT_VERSIONS.items()}
    assert kept == in_use | {"{}.v{}.md".format(*UNGROUNDED)}


def test_rq1_conditions_differ_only_in_grounding() -> None:
    grounded = sections(load_prompt(PROMPTS, "script", PROMPT_VERSIONS["script"]))
    ungrounded = sections(load_prompt(PROMPTS, *UNGROUNDED))
    for shared in ("Sounding like people talking", "Where the segment sits", "Delivery"):
        assert grounded[shared] == ungrounded[shared], shared
    assert "no source material" in ungrounded["Task"]


def numbered(rules: str) -> dict[str, str]:
    """A section's numbered rules by number, each with its continuation lines."""
    parts = re.split(r"^(\d+)\. ", rules, flags=re.MULTILINE)
    return {n: " ".join(body.split()) for n, body in zip(parts[1::2], parts[2::2], strict=True)}


def test_rq2_conditions_differ_only_in_format() -> None:
    dialogue = sections(load_prompt(PROMPTS, "script", PROMPT_VERSIONS["script"]))
    narration = sections(
        load_prompt(PROMPTS, "script_narrator", PROMPT_VERSIONS["script_narrator"])
    )
    assert dialogue["Delivery"] == narration["Delivery"]
    two, one = numbered(dialogue["Facts and citations"]), numbered(narration["Facts and citations"])
    # Rule 6 differs only in its example: a narrator has no one to react to.
    assert {n: r for n, r in two.items() if n != "6"} == {n: r for n, r in one.items() if n != "6"}


def test_source_passages_are_marked_as_data_not_instructions() -> None:
    for name in ("outline", "script", "script_narrator", "factcheck"):
        text = load_prompt(PROMPTS, name, PROMPT_VERSIONS[name])
        assert "not instructions" in text, name

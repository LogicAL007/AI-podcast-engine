"""The demo news site: each edition changes exactly the sections it says, as ingest reads them."""

import importlib
import sys
from pathlib import Path
from typing import Any

from podcast_engine.common.text import content_hash
from podcast_engine.stages.ingest.extract import extract_page

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "demo" / "site"))
server: Any = importlib.import_module("server")  # demo/site is a script folder, not a package


def sections_of(story: Any) -> dict[str, str]:
    page = extract_page(server.render(story))
    return {s.heading: content_hash(s.text) for s in page.sections}


def test_each_edition_changes_only_the_sections_it_names() -> None:
    story = server.Story()
    first = sections_of(story)
    assert list(first) == [
        "Overview",
        "How the subscription works",
        "Cost and funding",
        "Timeline",
        "Cleaning up the rail yard",
    ]

    story.move(1)
    second = sections_of(story)
    assert [h for h in first if first[h] != second[h]] == ["Timeline"]

    story.move(2)
    third = sections_of(story)
    assert set(third) - set(second) == {"Subscriptions open"}
    assert all(third[h] == second[h] for h in second)


def test_the_controls_are_not_part_of_the_story() -> None:
    page = extract_page(server.render(server.Story()))
    text = " ".join(s.text for s in page.sections)
    assert "Publish next edition" not in text
    assert "Demo site" not in text


def test_a_new_edition_is_dated_now_and_the_editions_stop_at_the_last() -> None:
    story = server.Story()
    before = extract_page(server.render(story)).published_at
    story.move(1)
    after = extract_page(server.render(story)).published_at
    assert before is not None
    assert after is not None
    assert after >= before
    story.move(99)
    assert story.index == len(server.EDITIONS) - 1
    story.move(-5)
    assert story.index == 0

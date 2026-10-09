"""Rule-based answers shared by the fake `anthropic` and fake `google.genai` test stand-ins.

They read the prompts the notebook builds and return canned structured output, so the notebook's
prompt building, id mapping, validation and rewrite loop can run without a network or a key. This
tests our plumbing, not any model's behaviour.
"""

import re
from typing import Any


def _passages(user: str) -> list[tuple[str, str, str]]:
    found = []
    for line in user.splitlines():
        match = re.match(r"^\[(P\d+)\] \((.*?)\)\s+(.*)$", line)
        if match:
            title = re.sub(r",\s*\d{4}-\d{2}-\d{2}$", "", match.group(2))
            found.append((match.group(1), title, match.group(3)))
    return found


def _sentences(text: str) -> list[str]:
    """Whole sentences only: chunk edges are mid-sentence and a real model would not quote them."""
    parts = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    return [s for s in parts if s[0].isupper() and s[-1] in ".!?" and len(s.split()) >= 4]


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 3}


def _outline(user: str) -> dict[str, Any]:
    segments: dict[str, list[str]] = {}
    for pid, title, _ in _passages(user):
        segments.setdefault(title, []).append(pid)
    return {"segments": [{"title": t, "passage_ids": ids} for t, ids in segments.items()]}


def _required(pattern: str, text: str) -> str:
    match = re.search(pattern, text)
    if match is None:
        raise ValueError(f"prompt does not contain {pattern!r}")
    return match.group(1)


def _segment(system: str, user: str) -> dict[str, Any]:
    hosts = [h.strip() for h in _required(r"Hosts: ([^.]*)\.", system).split(",")]
    passages = _passages(user)
    title = _required(r"Segment title: (.*)", user)
    lines: list[dict[str, Any]] = [
        {
            "speaker": hosts[0],
            "text": f"Let's talk about {title.lower()}.",
            "is_claim": False,
            "passage_ids": [],
        }
    ]
    seen: set[str] = set()
    for pid, _, text in passages:
        for sentence in _sentences(text):
            if sentence not in seen:
                seen.add(sentence)
                speaker = hosts[len(lines) % len(hosts)]
                lines.append(
                    {"speaker": speaker, "text": sentence, "is_claim": True, "passage_ids": [pid]}
                )
    is_redo = "reviewer found" in user
    if title.startswith("Citing") and not is_redo:  # a hallucinating first draft
        lines.append(
            {
                "speaker": hosts[0],
                "text": "The first such system was built in 1952 in Vienna.",
                "is_claim": True,
                "passage_ids": ["P1"],
            }
        )
        lines.append(
            {
                "speaker": hosts[-1],
                "text": "Models always check an encyclopedia first.",
                "is_claim": True,
                "passage_ids": ["P99"],
            }
        )
    return {"lines": lines}


def _verdicts(user: str) -> dict[str, Any]:
    verdicts: list[dict[str, Any]] = []
    for match in re.finditer(r"Claim (\d+): (.*?)\nCited passages:\n((?:- .*\n?)+)", user + "\n"):
        number, claim, cited = int(match.group(1)), match.group(2), match.group(3)
        overlap = len(_words(claim) & _words(cited)) / max(len(_words(claim)), 1)
        ok = overlap >= 0.5
        verdicts.append(
            {"claim_number": number, "supported": ok, "reason": f"overlap {overlap:.0%}"}
        )
    return {"verdicts": verdicts}


def respond(schema_name: str, system: str, user: str) -> dict[str, Any]:
    """The canned reply for the structured type a prompt asks for."""
    handlers = {
        "Outline": lambda: _outline(user),
        "DraftSegment": lambda: _segment(system, user),
        "Verdicts": lambda: _verdicts(user),
    }
    return handlers[schema_name]()

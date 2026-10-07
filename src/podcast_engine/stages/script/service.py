"""Script: grounded multi-speaker dialogue generation."""

from pathlib import Path
from uuid import UUID

from podcast_engine.common.queue import Stage


def load_prompt(prompts_dir: Path, name: str, version: int) -> str:
    """Read a versioned prompt (``<name>.v<version>.md``).

    Prompts are versioned files, never inline strings, so each episode can log exactly which
    prompt produced it and experiments can be rerun.
    """
    path = prompts_dir / f"{name}.v{version}.md"
    return path.read_text(encoding="utf-8")


def write_script(episode_id: UUID) -> Stage | None:
    """FR4/FR5: write the dialogue from retrieved passages; every claim carries a citation."""
    raise NotImplementedError("write_script: structured-output LLM call with passages in context")

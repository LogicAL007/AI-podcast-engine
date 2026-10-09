"""What a stage needs besides the episode id: settings, the database, object storage and models.

Workers build one context per process with ``get_context``; tests build their own with fakes. Models
(embedder, LLM client) are created on first use, so a stage that never needs one never imports it.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import cached_property, lru_cache
from pathlib import Path

from podcast_engine.common.config import Settings, get_settings
from podcast_engine.common.embeddings import Embedder, make_embedder
from podcast_engine.common.llm import LlmClient, make_llm
from podcast_engine.common.repository import PipelineRepository
from podcast_engine.common.storage import ObjectStore

# Host names, in speaking order; a show with host_count N uses the first N.
HOST_NAMES = ("Alex", "Sam", "Jordan", "Riley")

# Prompt file versions in use (prompts/<name>.v<N>.md), recorded in each episode's manifest.
PROMPT_VERSIONS = {"outline": 1, "script": 2, "factcheck": 1}


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class PipelineContext:
    settings: Settings
    repo: PipelineRepository
    store: ObjectStore
    fetch: Callable[[str], str] | None = None  # URL -> HTML; None uses the real HTTP fetch
    now: Callable[[], datetime] = field(default=_utc_now)
    llm_override: LlmClient | None = None  # tests inject a client here

    @cached_property
    def embedder(self) -> Embedder:
        return make_embedder(self.settings)

    @cached_property
    def llm(self) -> LlmClient | None:
        if self.llm_override is not None:
            return self.llm_override
        return make_llm(self.settings)

    @property
    def voices_file(self) -> Path:
        return self.settings.voices_file or self.settings.config_dir / "voices.yaml"

    def hosts(self, host_count: int) -> list[str]:
        return list(HOST_NAMES[: max(1, min(host_count, len(HOST_NAMES)))])


@lru_cache
def get_context() -> PipelineContext:
    """The worker process's context, built from the environment on first use."""
    from podcast_engine.common.db import get_engine
    from podcast_engine.common.storage import S3ObjectStore

    settings = get_settings()
    return PipelineContext(
        settings=settings, repo=PipelineRepository(get_engine()), store=S3ObjectStore(settings)
    )

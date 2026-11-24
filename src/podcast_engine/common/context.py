from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import cached_property, lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from podcast_engine.common.config import Settings, get_settings
from podcast_engine.common.embeddings import Embedder, make_embedder
from podcast_engine.common.llm import LlmClient, make_llm
from podcast_engine.common.quota import DailyBudget, make_budget
from podcast_engine.common.repository import PipelineRepository
from podcast_engine.common.storage import ObjectStore

if TYPE_CHECKING:
    from podcast_engine.stages.ingest.search import SearchProvider

# Host names, in speaking order; a show with host_count N uses the first N.
HOST_NAMES = ("Alex", "Sam", "Jordan", "Riley")

# Prompt file versions in use (prompts/<name>.v<N>.md), recorded in each episode's manifest.
PROMPT_VERSIONS = {"outline": 2, "script": 8, "script_narrator": 3, "factcheck": 2}


def script_prompt(host_count: int) -> str:
    """Return the script prompt for a show.

    Args:
        host_count: How many hosts the show has.

    Returns:
        ``script`` (a conversation) for two or more hosts, else ``script_narrator``.
    """
    return "script" if host_count > 1 else "script_narrator"


def _utc_now() -> datetime:
    """Return the current time in UTC.

    Returns:
        The current time, timezone-aware.
    """
    return datetime.now(UTC)


@dataclass
class PipelineContext:
    """What a stage needs besides the episode id: settings, database, object storage and models.

    Workers build one context per process with ``get_context``; tests build their own with fakes.
    Models (embedder, LLM client) are created on first use, so a stage that never needs one never
    imports it.

    - ``fetch`` turns a URL into HTML; None uses the real HTTP fetch.
    - ``search`` is the web search provider; None uses ``SEARCH_PROVIDER``.
    - ``llm_override`` and ``budget_override`` let tests inject an LLM client and a daily budget.
    """

    settings: Settings
    repo: PipelineRepository
    store: ObjectStore
    fetch: Callable[[str], str] | None = None
    search: "SearchProvider | None" = None
    now: Callable[[], datetime] = field(default=_utc_now)
    llm_override: LlmClient | None = None
    budget_override: DailyBudget | None = None

    @cached_property
    def embedder(self) -> Embedder:
        """The text embedder named by the settings, created on first use."""
        return make_embedder(self.settings)

    @cached_property
    def budget(self) -> DailyBudget | None:
        """Gemini requests each model may still take today; None when no limit is set."""
        if self.budget_override is not None:
            return self.budget_override
        return make_budget(self.settings)

    @cached_property
    def llm(self) -> LlmClient | None:
        """The LLM client, or None when the LLM is off; created on first use."""
        if self.llm_override is not None:
            return self.llm_override
        return make_llm(self.settings, self.budget)

    @property
    def voices_file(self) -> Path:
        """The voices config file: ``VOICES_FILE``, else ``voices.yaml`` in the config folder."""
        return self.settings.voices_file or self.settings.config_dir / "voices.yaml"

    def hosts(self, host_count: int) -> list[str]:
        """Return the host names for a show, in speaking order.

        Args:
            host_count: How many hosts the show has; kept between 1 and 4.

        Returns:
            The first N of Alex, Sam, Jordan and Riley.
        """
        return list(HOST_NAMES[: max(1, min(host_count, len(HOST_NAMES)))])


@lru_cache
def get_context() -> PipelineContext:
    """Return the worker process's context, built from the environment on first use.

    Returns:
        The process-wide context with the real database and object store.
    """
    from podcast_engine.common.db import get_engine
    from podcast_engine.common.storage import S3ObjectStore

    settings = get_settings()
    return PipelineContext(
        settings=settings, repo=PipelineRepository(get_engine()), store=S3ObjectStore(settings)
    )

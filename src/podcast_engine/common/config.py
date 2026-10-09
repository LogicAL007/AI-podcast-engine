"""Runtime settings, read from the environment and Docker secrets."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process-wide configuration.

    Secrets are never read from plain environment variables in deployment: for each
    ``<name>_file`` field the file's contents populate the matching secret (NFR: API keys
    are held outside the image and the compose file).
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    log_level: str = "INFO"

    # Infrastructure
    database_url: str = "postgresql+psycopg://podcast:change-me@postgres:5432/podcast"
    redis_url: str = "redis://redis:6379/0"
    s3_endpoint_url: str = "http://s3:9000"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "podcast-episodes"
    s3_region: str = "us-east-1"

    # Local volumes (mounted by docker compose)
    data_dir: Path = Path("/data")
    config_dir: Path = Path("/app/config")
    prompts_dir: Path = Path("/app/prompts")
    assets_dir: Path = Path("/app/assets")

    # Models and providers
    embedding_model: str = "hashing"  # "hashing" (offline) or a sentence-transformers model id
    embedding_dimensions: int = 384  # must match chunks.embedding, vector(384), in the database
    llm_enabled: bool = False  # False: the offline writer and word-overlap judge, no model calls
    llm_provider: str = "gemini"  # "gemini" or "anthropic"
    llm_model: str = "gemini-3.8-flash"
    llm_fallback_model: str = ""  # opt-in: another model if llm_model stays overloaded
    tts_backend: str = "placeholder"  # "placeholder", "say", "chatterbox" or "gemini"
    tts_model: str = "gemini-3.8-flash-tts"  # used by the "gemini" backend
    voices_file: Path | None = None  # defaults to <config_dir>/voices.yaml
    llm_api_key: SecretStr = SecretStr("")
    llm_api_key_file: Path | None = None
    tts_api_key: SecretStr = SecretStr("")
    tts_api_key_file: Path | None = None

    # Pipeline behaviour
    worker_concurrency: int = Field(default=2, ge=1)
    worker_pool: str = "prefork"  # "solo" for a host worker on Python 3.14 or with a GPU model
    metrics_port: int = Field(default=9100, ge=1, le=65535)  # workers serve /metrics here
    max_rewrites: int = Field(default=2, ge=0)
    seed: int = 7  # recorded per episode so a run can be repeated
    topic_threshold: float = Field(default=0.0, ge=0.0, le=1.0)  # below this: off-topic
    facts_per_segment: int = Field(default=8, ge=1)  # most sentences quoted per segment
    passages_per_segment: int = Field(default=0, ge=0)  # 0: 3 offline, 6 with an LLM
    migrations_dir: Path = Path("/app/db/migrations")
    # Scheduler (FR8): hours between automatic refreshes of each published show; 0 turns it off.
    refresh_interval_hours: float = Field(default=0.0, ge=0.0)
    episode_cost_cap_usd: float = Field(default=1.0, gt=0)
    public_feed_base_url: str = "http://localhost:8080"

    @model_validator(mode="after")
    def _load_secret_files(self) -> "Settings":
        if self.llm_api_key_file is not None:
            self.llm_api_key = _read_secret(self.llm_api_key_file)
        if self.tts_api_key_file is not None:
            self.tts_api_key = _read_secret(self.tts_api_key_file)
        return self


def _read_secret(path: Path) -> SecretStr:
    return SecretStr(path.read_text(encoding="utf-8").strip())


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance."""
    return Settings()

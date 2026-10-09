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
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dimensions: int = 384
    llm_provider: str = "gemini"  # "gemini" or "anthropic"
    llm_model: str = "gemini-3.8-flash"
    tts_provider: str = "hosted"
    llm_api_key: SecretStr = SecretStr("")
    llm_api_key_file: Path | None = None
    tts_api_key: SecretStr = SecretStr("")
    tts_api_key_file: Path | None = None

    # Pipeline behaviour
    worker_concurrency: int = Field(default=2, ge=1)
    metrics_port: int = Field(default=9100, ge=1, le=65535)  # workers serve /metrics here
    max_rewrites: int = Field(default=2, ge=0)
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

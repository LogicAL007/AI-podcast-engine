"""Runtime settings, read from the environment, HashiCorp Vault and secret files."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process-wide configuration.

    Secrets are never read from plain environment variables in deployment. With ``vault_addr``
    set, they come from Vault (KV v2 at ``secret/<vault_kv_path>``), read once at start with the
    token in ``vault_token_file``. Without Vault, each ``<name>_file`` field's contents populate
    the matching secret (for host runs and tests). A secret set in Vault wins over its file.
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

    # Secrets store: HashiCorp Vault
    vault_addr: str = ""  # e.g. http://vault:8200; blank: no Vault, read the *_file secrets
    vault_token_file: Path | None = None  # the read-only token issued by vault_init
    vault_kv_path: str = "podcast"
    vault_ca_file: Path | None = None  # the CA that signed Vault's TLS certificate (vault-certs)

    # Login
    auth_token_key: SecretStr = SecretStr("")  # HMAC key for stored tokens; from Vault
    auth_token_key_file: Path | None = None
    auth_token_days: int = Field(default=180, ge=1, le=366)  # sessions and API keys: six months
    # Failed logins: this many on one account within the window locks it for the lockout time;
    # this many from one address within the window slows that address (HTTP 429).
    login_max_failures: int = Field(default=5, ge=1)
    login_ip_max_failures: int = Field(default=50, ge=1)
    login_window_minutes: int = Field(default=15, ge=1)
    login_lockout_minutes: int = Field(default=15, ge=1)
    password_reset_minutes: int = Field(default=30, ge=5, le=1440)
    password_reset_max_requests: int = Field(default=3, ge=1)  # per account per hour

    # Email (password reset). The compose stack sends to Mailpit, a local inbox on :8025.
    smtp_host: str = ""  # blank: email is not sent (reset links are not delivered)
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")  # from Vault
    smtp_password_file: Path | None = None
    smtp_starttls: bool = True
    mail_from: str = "Podcast Engine <no-reply@localhost>"
    # Where people use the service. Links in emails are built from this, never from a request's
    # Host header (which a client controls).
    public_web_url: str = "http://localhost:8080"

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
    feed_max_items: int = Field(default=10, ge=1, le=100)  # newest entries read from each feed
    max_upload_mb: int = Field(default=25, ge=1)  # largest PDF a creator may upload
    # Scheduler (FR8): hours between automatic refreshes of each published show; 0 turns it off.
    refresh_interval_hours: float = Field(default=0.0, ge=0.0)
    episode_cost_cap_usd: float = Field(default=1.0, gt=0)
    public_feed_base_url: str = "http://localhost:8080"

    @model_validator(mode="after")
    def _load_secrets(self) -> "Settings":
        for name in VAULT_SECRETS:
            path: Path | None = getattr(self, f"{name}_file")
            if path is not None:
                setattr(self, name, _read_secret(path))
        if self.vault_addr:
            from podcast_engine.common.vault import read_kv

            if self.vault_token_file is None:
                raise ValueError("VAULT_ADDR is set but VAULT_TOKEN_FILE is not")
            token = self.vault_token_file.read_text(encoding="utf-8").strip()
            stored = read_kv(self.vault_addr, token, self.vault_kv_path, ca_file=self.vault_ca_file)
            for name in VAULT_SECRETS:
                if stored.get(name):
                    setattr(self, name, SecretStr(stored[name]))
        return self


# Secrets kept in Vault under these keys (and the *_file fallbacks with the same names).
VAULT_SECRETS = ("llm_api_key", "tts_api_key", "auth_token_key", "smtp_password")


def _read_secret(path: Path) -> SecretStr:
    return SecretStr(path.read_text(encoding="utf-8").strip())


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance."""
    return Settings()

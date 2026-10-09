from pathlib import Path

import pytest

from podcast_engine.common.config import Settings


def test_secret_file_populates_secret(tmp_path: Path) -> None:
    secret = tmp_path / "llm_api_key"
    secret.write_text("sk-test\n", encoding="utf-8")
    settings = Settings(llm_api_key_file=secret)
    assert settings.llm_api_key.get_secret_value() == "sk-test"
    assert "sk-test" not in repr(settings)


def test_cost_cap_must_be_positive() -> None:
    with pytest.raises(ValueError, match="episode_cost_cap_usd"):
        Settings(episode_cost_cap_usd=0)


def test_s3_defaults_point_at_the_compose_service() -> None:
    settings = Settings()
    assert settings.s3_endpoint_url == "http://s3:9000"
    assert settings.s3_region == "us-east-1"


def test_llm_defaults_to_gemini_and_can_be_switched(monkeypatch: pytest.MonkeyPatch) -> None:
    defaults = Settings(_env_file=None)  # ignore a developer's local .env
    assert (defaults.llm_provider, defaults.llm_model) == ("gemini", "gemini-3.8-flash")
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_MODEL", "claude-sonnet-5-5")
    switched = Settings(_env_file=None)
    assert (switched.llm_provider, switched.llm_model) == ("anthropic", "claude-sonnet-5-5")

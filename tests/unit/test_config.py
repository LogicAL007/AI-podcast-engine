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

"""The Claude client's request: structured output, and the optional thinking effort.

A fake ``messages.parse`` stands in for the SDK's, so nothing touches the network.
"""

from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel

pytest.importorskip("anthropic")

from podcast_engine.common.config import Settings
from podcast_engine.common.llm import ClaudeClient, make_llm


class Answer(BaseModel):
    title: str


def fake(client: ClaudeClient) -> list[dict[str, Any]]:
    sent: list[dict[str, Any]] = []

    def parse(**kwargs: Any) -> Any:
        sent.append(kwargs)
        return SimpleNamespace(
            usage=SimpleNamespace(input_tokens=1200, output_tokens=300),
            stop_reason="end_turn",
            parsed_output=Answer(title="Tides"),
        )

    client.client = SimpleNamespace(messages=SimpleNamespace(parse=parse))  # type: ignore[assignment]
    return sent


def test_effort_is_sent_beside_the_output_format_and_usage_is_counted() -> None:
    client = ClaudeClient("test-key", "claude-sonnet-5-5", seed=1, effort="medium")
    sent = fake(client)
    assert client.parse(system="s", user="u", output_format=Answer).title == "Tides"
    assert sent[0]["output_config"] == {"effort": "medium"}
    assert sent[0]["output_format"] is Answer
    assert dict(client.usage) == {"input_tokens": 1200, "output_tokens": 300}


def test_without_an_effort_the_request_is_unchanged() -> None:
    client = ClaudeClient("test-key", "claude-sonnet-5-5", seed=1)
    sent = fake(client)
    client.parse(system="s", user="u", output_format=Answer)
    assert "output_config" not in sent[0]


def test_the_setting_reaches_the_client() -> None:
    settings = Settings(
        _env_file=None, llm_enabled=True, llm_provider="anthropic",
        llm_model="claude-haiku-5-5", llm_effort="low", llm_api_key="test-key",
    )  # fmt: skip
    client = make_llm(settings)
    assert isinstance(client, ClaudeClient)
    assert client.effort == "low"

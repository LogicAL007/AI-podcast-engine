"""A stand-in for the `anthropic` package, used to test the notebook's Claude code path offline.

Put this directory first on PYTHONPATH and `import anthropic` resolves here instead of the real
SDK. It answers `client.messages.parse(...)` with canned, rule-based structured outputs, so the
notebook's prompt building, id mapping, validation and rewrite loop run without a network or an API
key. It tests our plumbing, not Claude's behaviour.
"""

from types import SimpleNamespace
from typing import Any

from fake_llm_rules import respond
from pydantic import BaseModel


class _Messages:
    def parse(
        self,
        *,
        model: str,
        max_tokens: int,
        system: str,
        messages: list[dict[str, Any]],
        output_format: type[BaseModel],
    ) -> SimpleNamespace:
        del model, max_tokens
        user = messages[0]["content"]
        payload = respond(output_format.__name__, system, user)
        return SimpleNamespace(
            parsed_output=output_format.model_validate(payload),
            usage=SimpleNamespace(input_tokens=1000, output_tokens=400),
            stop_reason="end_turn",
            stop_details=None,
        )


class AuthenticationError(Exception):
    pass


class NotFoundError(Exception):
    pass


class APIConnectionError(Exception):
    pass


class _Models:
    def retrieve(self, model: str) -> SimpleNamespace:
        return SimpleNamespace(id=model)


class Anthropic:
    def __init__(self, api_key: str | None = None, **_: Any) -> None:
        self.messages = _Messages()
        self.models = _Models()

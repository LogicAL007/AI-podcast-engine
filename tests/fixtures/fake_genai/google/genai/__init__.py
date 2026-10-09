"""A stand-in for `google.genai`, used to test the notebook's Gemini code path offline.

Put this directory (and tests/fixtures/fake_llm) first on PYTHONPATH. `google` is a namespace
package, so `from google import genai` then resolves here instead of the real SDK. It tests our
plumbing, not Gemini's behaviour.
"""

import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fake_llm_rules import respond

from . import errors, types

__all__ = ["Client", "errors", "types"]


def _log(event: str) -> None:
    """Append to the file named by FAKE_GENAI_LOG, so a test can prove whether the SDK was used."""
    if path := os.environ.get("FAKE_GENAI_LOG"):
        with Path(path).open("a", encoding="utf-8") as handle:
            handle.write(event + "\n")


class _Models:
    def get(self, *, model: str) -> SimpleNamespace:
        _log(f"models.get {model}")
        return SimpleNamespace(name=f"models/{model}")

    def generate_content(self, *, model: str, contents: str, config: Any) -> SimpleNamespace:
        _log(f"generate_content {model}")
        if model in os.environ.get("FAKE_GENAI_BUSY_MODELS", "").split(","):
            raise errors.ServerError(503, "This model is currently experiencing high demand.")
        payload = respond(config.response_json_schema["title"], config.system_instruction, contents)
        return SimpleNamespace(
            text=json.dumps(payload),
            candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name="STOP"))],
            usage_metadata=SimpleNamespace(
                prompt_token_count=1000, candidates_token_count=300, thoughts_token_count=100
            ),
            prompt_feedback=None,
        )


class Client:
    def __init__(self, api_key: str | None = None, **_: Any) -> None:
        _log("Client()")
        self.models = _Models()

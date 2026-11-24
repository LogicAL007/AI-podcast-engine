import json
import random
import re
import time
from collections import Counter
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeVar

from pydantic import BaseModel, ValidationError

from podcast_engine.common.config import Settings
from podcast_engine.common.logging import get_logger

if TYPE_CHECKING:
    from podcast_engine.common.quota import DailyBudget

T = TypeVar("T", bound=BaseModel)
log = get_logger("llm")

KEY_HELP = {
    "gemini": "Put a Gemini key in the llm_api_key secret (secrets/llm_api_key.txt).",
    "anthropic": "Put an Anthropic key in the llm_api_key secret (secrets/llm_api_key.txt).",
}


class LlmError(RuntimeError):
    """The model could not produce a usable answer; the stage fails and Celery retries it."""


class GeminiQuotaError(LlmError):
    """Gemini's quota for today is used up; waiting minutes will not help, so nothing retries."""


def retry_after_seconds(error: Any) -> float | None:
    """Return the wait Gemini asks for on a 429, from its RetryInfo detail or its message.

    Args:
        error: The SDK's error.

    Returns:
        The wait in seconds, or None when Gemini gave none.
    """
    body = getattr(error, "details", None) or {}
    for detail in (body.get("error") or {}).get("details") or []:
        delay = str(detail.get("retryDelay", ""))
        if delay.endswith("s"):
            try:
                return float(delay[:-1])
            except ValueError:
                pass
    found = re.search(r"retry in ([\d.]+)s", str(error))
    return float(found.group(1)) if found else None


def is_refused(error: BaseException) -> bool:
    """Tell whether Gemini rejected the request itself.

    A bad request, key or model, but not a rate limit: sending it again fails the same way, so the
    stage should not be retried. An image without the Gemini SDK never makes Gemini calls.

    Args:
        error: The error the stage raised.

    Returns:
        True for a 4xx other than 429.
    """
    try:
        from google.genai import errors
    except ImportError:
        return False
    return isinstance(error, errors.ClientError) and error.code != 429


def is_daily_quota(error: Any) -> bool:
    """Tell whether the exhausted quota is a per-day one, such as the free tier's daily cap.

    Args:
        error: The SDK's 429 error.

    Returns:
        True for a daily quota.
    """
    return "PerDay" in str(getattr(error, "details", "") or error)


class LlmClient:
    """Common shape of the model clients: a schema in, a validated object out, usage counted.

    Used by the outline, script and fact-check stages, with Gemini or Claude. ``usage`` counts
    tokens in and out, and ``models_used`` which model actually answered each call.
    """

    provider = ""

    def __init__(self, model: str, seed: int) -> None:
        """Create the client.

        Args:
            model: The model to ask.
            seed: The sampling seed, for reproducible runs.
        """
        self.model = model
        self.seed = seed
        self.usage: Counter[str] = Counter()
        self.models_used: Counter[str] = Counter()

    def _record(self, model: str, tokens_in: int, tokens_out: int) -> None:
        """Count one answered call and its tokens.

        Args:
            model: The model that answered.
            tokens_in: Prompt tokens.
            tokens_out: Answer tokens, thinking included.
        """
        self.models_used[model] += 1
        self.usage["input_tokens"] += tokens_in
        self.usage["output_tokens"] += tokens_out

    def parse(
        self, *, system: str, user: str, output_format: type[T], max_tokens: int = 16000
    ) -> T:
        """Ask the model and return its answer as a validated object.

        Args:
            system: The system prompt.
            user: The user message.
            output_format: The Pydantic class the answer must match.
            max_tokens: Most tokens the answer may use.

        Returns:
            The answer, validated as ``output_format``.

        Raises:
            NotImplementedError: Always; each client implements it.
        """
        raise NotImplementedError


class GeminiClient(LlmClient):
    """Gemini through the ``google-genai`` SDK, asking for JSON matching a Pydantic schema."""

    provider = "gemini"
    RETRIES = 8  # waits of about 2, 4, 8, 16, 32, 32 and 32 seconds: about two minutes per call
    RETRIES_BEFORE_FALLBACK = (
        3  # with a fallback configured: waits of about 2 and 4 seconds, then switch
    )

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        seed: int,
        fallback: str = "",
        sleep: Callable[[float], None] = time.sleep,
        budget: "DailyBudget | None" = None,
        reserve: int = 0,
        timeout: float = 180.0,
    ) -> None:
        """Create the client.

        Requests time out, because without a timeout a request Gemini never answers holds the stage
        forever.

        Args:
            api_key: The Gemini API key, or empty to use the environment's.
            model: The main model.
            seed: The sampling seed.
            fallback: Another model to switch to while the main one stays busy, or empty.
            sleep: Waits between retries; replaced in tests.
            budget: The shared daily budget, or None.
            reserve: Requests of each day's budget this client leaves to others.
            timeout: Seconds to wait for one answer.

        Raises:
            LlmError: No Gemini credentials were found.
        """
        super().__init__(model, seed)
        from google import genai
        from google.genai import types

        self.sleep = sleep
        self.budget = budget
        self.reserve = reserve
        self.fallback = fallback if fallback != model else ""
        self.active = model
        self.busy_retries = 0
        try:
            options = types.HttpOptions(timeout=int(timeout * 1000))
            self.client = genai.Client(api_key=api_key or None, http_options=options)
        except ValueError as error:
            raise LlmError(f"No Gemini credentials were found. {KEY_HELP['gemini']}") from error

    def _call(self, model: str, user: str, config: Any, tries: int) -> Any:
        """Send one request, patiently retried.

        503 "high demand", 429 rate limits and network blips are brief, so they are retried with
        backoff (or the wait Gemini asks for). A used-up daily quota is not, so it fails at once,
        and with a daily budget the call stops before it would pass it. Only a request Gemini read
        and rejected (a 4xx other than 429) counts against the budget: an overloaded 503, a 429 and
        a network failure did no work; if Google counts them anyway, its own 429 daily-quota error
        stops us.

        Args:
            model: The model to ask.
            user: The user message.
            config: The request's configuration.
            tries: How many attempts to make.

        Returns:
            Gemini's response.

        Raises:
            GeminiQuotaError: Today's quota for the model is used up, or the budget would be passed.
            google.genai.errors.APIError: Gemini refused the request, or stayed busy for every
                attempt.
        """
        import httpx
        from google.genai import errors

        for attempt in range(tries):
            if self.budget is not None:
                self.budget.require({model: 1}, f"another {model} request", reserve=self.reserve)
            try:
                response = self.client.models.generate_content(
                    model=model, contents=user, config=config
                )
            except (errors.ServerError, errors.ClientError, httpx.TransportError) as error:
                limited = isinstance(error, errors.ClientError) and error.code == 429
                reached = isinstance(error, errors.ClientError) and not limited
                if self.budget is not None and reached:
                    self.budget.spend(model)
                if limited and is_daily_quota(error):
                    raise GeminiQuotaError(
                        f"Gemini's daily quota for {model} is used up. Try again tomorrow, "
                        "enable billing on the key, or set LLM_ENABLED=false to plan and write "
                        "offline."
                    ) from error
                busy = limited or not isinstance(error, errors.ClientError)
                if not busy or attempt == tries - 1:
                    raise
                self.busy_retries += 1
                asked = retry_after_seconds(error) if limited else None
                wait = (asked + 1) if asked else min(2 ** (attempt + 1), 32) + random.random()  # noqa: S311 - jitter, not security
                code = getattr(error, "code", None) or type(error).__name__
                log.warning("llm_busy", model=model, code=code, retry_in_s=round(wait))
                self.sleep(wait)
            else:
                if self.budget is not None:
                    self.budget.spend(model)
                return response
        raise AssertionError("unreachable")

    def parse(
        self, *, system: str, user: str, output_format: type[T], max_tokens: int = 16000
    ) -> T:
        """Ask Gemini for JSON matching a Pydantic schema, and validate it.

        The schema is sent with the request; if the API refuses the schema, it is put in the prompt
        instead. The model in use is tried first, then the other one: once on the fallback, a
        fallback that is out of quota (or busy too) sends the request back to the main model rather
        than failing. A model that is busy, timing out, rate-limited or out of quota for today hands
        over to the other, which has its own quota, and the busy one is not waited on again.
        Thinking tokens are counted as output, as they are billed.

        Args:
            system: The system prompt.
            user: The user message.
            output_format: The Pydantic class the answer must match.
            max_tokens: Most tokens the answer may use.

        Returns:
            The answer, validated as ``output_format``.

        Raises:
            LlmError: Gemini declined the request, its answer was cut off or empty, or its JSON does
                not match.
            GeminiQuotaError: Every model's quota is used up.
        """
        import httpx
        from google.genai import errors, types

        schema = output_format.model_json_schema()
        with_schema = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_json_schema=schema,
            max_output_tokens=max_tokens,
            seed=self.seed,
        )
        plain_json = types.GenerateContentConfig(
            system_instruction=(
                f"{system}\n\nReply with JSON matching this JSON Schema:\n{json.dumps(schema)}"
            ),
            response_mime_type="application/json",
            max_output_tokens=max_tokens,
            seed=self.seed,
        )
        candidates = [
            self.active,
            *(m for m in (self.model, self.fallback) if m and m != self.active),
        ]
        response: Any = None
        model = self.active
        for position, model in enumerate(candidates):
            has_next = position < len(candidates) - 1
            tries = self.RETRIES_BEFORE_FALLBACK if has_next else self.RETRIES
            try:
                try:
                    response = self._call(model, user, with_schema, tries)
                except errors.ClientError as error:
                    if error.code != 400 or "schema" not in str(error).lower():
                        raise
                    response = self._call(model, user, plain_json, tries)
                break
            except (
                errors.ServerError,
                errors.ClientError,
                GeminiQuotaError,
                httpx.TransportError,
            ) as error:
                still_busy = not isinstance(error, errors.ClientError) or error.code == 429
                if not still_busy or not has_next:
                    raise
                self.active = candidates[position + 1]
                log.warning("llm_fallback", busy_model=model, now_using=self.active)
        meta = response.usage_metadata
        self._record(
            model,
            (meta.prompt_token_count or 0) if meta else 0,
            ((meta.candidates_token_count or 0) + (meta.thoughts_token_count or 0)) if meta else 0,
        )
        candidate = response.candidates[0] if response.candidates else None
        reason = (
            candidate.finish_reason.name
            if candidate and candidate.finish_reason
            else "NO_CANDIDATE"
        )
        if reason in {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION"}:
            raise LlmError(f"Gemini declined this request (finish_reason={reason}).")
        if reason == "MAX_TOKENS":
            raise LlmError(f"Gemini's answer was cut off at {max_tokens} tokens.")
        text = response.text
        if not text:
            raise LlmError(f"Gemini returned no text (finish_reason={reason}).")
        try:
            return output_format.model_validate_json(text)
        except ValidationError as error:
            raise LlmError(
                f"Gemini's JSON does not match {output_format.__name__}: {error}"
            ) from error


class ClaudeClient(LlmClient):
    """Anthropic Claude through the ``anthropic`` SDK, using structured outputs."""

    provider = "anthropic"

    def __init__(self, api_key: str, model: str, *, seed: int, effort: str = "") -> None:
        """Create the client.

        Args:
            api_key: The Anthropic API key, or empty to use the environment's.
            model: The Claude model.
            seed: The seed, recorded for the run (Claude does not take one).
            effort: Thinking effort (low, medium, high, xhigh or max), or empty for the model's
                default.
        """
        super().__init__(model, seed)
        import anthropic

        self.client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        self.effort = effort

    def parse(
        self, *, system: str, user: str, output_format: type[T], max_tokens: int = 16000
    ) -> T:
        """Ask Claude for a structured answer.

        The SDK merges the output format into ``output_config`` with the effort.

        Args:
            system: The system prompt.
            user: The user message.
            output_format: The Pydantic class the answer must match.
            max_tokens: Most tokens the answer may use.

        Returns:
            The answer, validated as ``output_format``.

        Raises:
            LlmError: The model declined the request or returned no structured output.
        """
        extra: dict[str, Any] = {"output_config": {"effort": self.effort}} if self.effort else {}
        response = self.client.messages.parse(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_format=output_format,
            **extra,
        )
        self._record(self.model, response.usage.input_tokens, response.usage.output_tokens)
        if response.stop_reason == "refusal":
            raise LlmError("The model declined this request.")
        if response.parsed_output is None:
            raise LlmError(f"No structured output returned (stop_reason={response.stop_reason})")
        parsed: T = response.parsed_output
        return parsed


def make_llm(
    settings: Settings, budget: "DailyBudget | None" = None, reserve: int = 0
) -> LlmClient | None:
    """Return the configured model client.

    With ``LLM_ENABLED=false`` (the default) the stages use their offline stand-ins, and no SDK is
    even imported. With a ``budget``, Gemini calls stop before passing the day's request limit;
    ``reserve`` requests of it are left for others (the assistant leaves half the day to the
    pipeline).

    Args:
        settings: The provider, model, keys and fallback.
        budget: The shared daily budget, or None.
        reserve: Requests of each day's budget to leave to others.

    Returns:
        A Gemini or Claude client, or None when the LLM is off.
    """
    if not settings.llm_enabled:
        return None
    key = settings.llm_api_key.get_secret_value()
    if settings.llm_provider == "gemini":
        return GeminiClient(
            key,
            settings.llm_model,
            seed=settings.seed,
            fallback=settings.llm_fallback_model,
            budget=budget,
            reserve=reserve,
            timeout=settings.llm_timeout_seconds,
        )
    if settings.llm_provider == "anthropic":
        return ClaudeClient(key, settings.llm_model, seed=settings.seed, effort=settings.llm_effort)
    raise ValueError(f"LLM_PROVIDER must be gemini or anthropic, not {settings.llm_provider!r}")

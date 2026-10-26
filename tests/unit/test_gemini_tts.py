"""Gemini TTS under rate limits: it waits as asked, paces itself, and stops on a daily cap.

The real SDK's error class is used with a fake client, so nothing touches the network.
"""

from types import SimpleNamespace
from typing import Any

import pytest

errors = pytest.importorskip("google.genai.errors")

from podcast_engine.common.llm import GeminiQuotaError, retry_after_seconds  # noqa: E402
from podcast_engine.stages.voice.backends import GeminiTtsBackend  # noqa: E402

AUDIO = SimpleNamespace(
    candidates=[
        SimpleNamespace(
            content=SimpleNamespace(
                parts=[SimpleNamespace(inline_data=SimpleNamespace(data=b"\x00\x10" * 240))]
            )
        )
    ]
)


def quota_error(quota_id: str, delay: str = "10s") -> Any:
    return errors.ClientError(
        429,
        {
            "error": {
                "code": 429,
                "message": f"Quota exceeded. Please retry in {delay[:-1]}.4s.",
                "status": "RESOURCE_EXHAUSTED",
                "details": [
                    {
                        "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                        "violations": [{"quotaId": quota_id}],
                    },
                    {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": delay},
                ],
            }
        },
    )


class FakeModels:
    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = outcomes
        self.calls = 0

    def generate_content(self, **_: Any) -> Any:
        self.calls += 1
        outcome = self.outcomes.pop(0) if self.outcomes else AUDIO
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.waits: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.waits.append(round(seconds, 1))
        self.now += seconds

    def time(self) -> float:
        return self.now


def backend(outcomes: list[Any], per_minute: int = 0) -> tuple[GeminiTtsBackend, FakeModels, Clock]:
    clock = Clock()
    tts = GeminiTtsBackend(
        "test-key", "gemini-3.8-flash-tts", per_minute, sleep=clock.sleep, clock=clock.time
    )
    models = FakeModels(outcomes)
    tts.client = SimpleNamespace(models=models)  # type: ignore[assignment]
    return tts, models, clock


def test_waits_as_long_as_gemini_asks_then_succeeds() -> None:
    per_minute = "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"
    tts, models, clock = backend([quota_error(per_minute), quota_error(per_minute)])
    samples = tts.synthesise("Alex", "Hello there.")
    assert len(samples) == 240
    assert models.calls == 3
    assert clock.waits == [11.0, 11.0]  # the asked-for 10 s, plus a second's margin


def test_a_used_up_daily_quota_fails_at_once_with_a_plain_message() -> None:
    tts, models, clock = backend([quota_error("GenerateRequestsPerDayPerProjectPerModel-FreeTier")])
    with pytest.raises(GeminiQuotaError, match="daily quota"):
        tts.synthesise("Alex", "Hello there.")
    assert models.calls == 1
    assert clock.waits == []


def test_paces_requests_to_the_configured_rate() -> None:
    tts, models, clock = backend([], per_minute=3)
    for _ in range(3):
        tts.synthesise("Sam", "One line.")
    assert models.calls == 3
    assert clock.waits == [20.0, 20.0]  # 3 a minute: one every 20 s, the first at once


def test_other_client_errors_are_not_retried() -> None:
    tts, models, _ = backend([errors.ClientError(400, {"error": {"message": "bad request"}})])
    with pytest.raises(errors.ClientError):
        tts.synthesise("Alex", "Hello.")
    assert models.calls == 1


def test_reads_the_delay_from_the_message_when_retry_info_is_missing() -> None:
    error = errors.ClientError(429, {"error": {"message": "Please retry in 7.5s."}})
    assert retry_after_seconds(error) == 7.5


class Recorder(FakeModels):
    def __init__(self) -> None:
        super().__init__([])
        self.requests: list[dict[str, Any]] = []

    def generate_content(self, **request: Any) -> Any:
        self.requests.append(request)
        return super().generate_content(**request)


def test_a_two_host_conversation_is_one_multi_speaker_request() -> None:
    tts, _, _ = backend([])
    recorder = Recorder()
    tts.client = SimpleNamespace(models=recorder)  # type: ignore[assignment]
    samples = tts.synthesise_dialogue([("Alex", "Hi Sam."), ("Sam", "Hi Alex."), ("Alex", "Go.")])
    assert len(samples) == 240
    assert len(recorder.requests) == 1
    request = recorder.requests[0]
    assert request["contents"].endswith("Alex: Hi Sam.\nSam: Hi Alex.\nAlex: Go.")
    speakers = request["config"].speech_config.multi_speaker_voice_config.speaker_voice_configs
    assert [(s.speaker, s.voice_config.prebuilt_voice_config.voice_name) for s in speakers] == [
        ("Alex", "Kore"),
        ("Sam", "Puck"),
    ]


def test_one_speakers_lines_are_one_single_voice_request() -> None:
    tts, _, _ = backend([])
    recorder = Recorder()
    tts.client = SimpleNamespace(models=recorder)  # type: ignore[assignment]
    tts.synthesise_dialogue([("Sam", "That's all."), ("Sam", "Bye.")])
    (request,) = recorder.requests
    assert request["contents"] == "That's all.\nBye."
    assert request["config"].speech_config.voice_config.prebuilt_voice_config.voice_name == "Puck"


def test_more_than_two_speakers_in_one_request_is_refused() -> None:
    tts, models, _ = backend([])
    with pytest.raises(ValueError, match="at most two speakers"):
        tts.synthesise_dialogue([("Alex", "A."), ("Sam", "B."), ("Jordan", "C.")])
    assert models.calls == 0

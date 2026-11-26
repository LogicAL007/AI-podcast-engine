"""Chatterbox as the second engine (TTS_RECORDED_BACKEND): Gemini servers speak recorded voices."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from podcast_engine.common.config import Settings
from podcast_engine.common.context import PipelineContext
from podcast_engine.common.quota import DailyBudget, MemoryCounter
from podcast_engine.common.repository import SpeechClipRecord
from podcast_engine.stages.voice import service, speak
from podcast_engine.stages.voice.backends import PlaceholderBackend, speaks_recorded_voices
from podcast_engine.stages.voice.registry import ClonedVoice

CONFIG = Path(__file__).resolve().parents[2] / "config"


def pipeline_ctx(tmp_path: Path, settings: Settings, **parts: Any) -> PipelineContext:
    return PipelineContext(
        settings=settings,
        repo=parts.get("repo"),  # type: ignore[arg-type]
        store=parts.get("store"),  # type: ignore[arg-type]
        budget_override=DailyBudget(MemoryCounter(), {}),  # no Redis
    )


def test_only_a_recorded_voice_job_switches_to_chatterbox(tmp_path: Path) -> None:
    hybrid = Settings(tts_backend="gemini", tts_recorded_backend="chatterbox")
    ctx = pipeline_ctx(tmp_path, hybrid)
    switched = service.recorded_voice_context(ctx)
    assert switched.settings.tts_backend == "chatterbox"
    assert ctx.settings.tts_backend == "gemini"  # the worker's own context is unchanged
    assert speaks_recorded_voices(hybrid)

    plain = pipeline_ctx(tmp_path, Settings(tts_backend="gemini"))
    assert service.recorded_voice_context(plain) is plain
    assert not speaks_recorded_voices(plain.settings)


def test_a_recorded_clip_on_a_gemini_server_is_voiced_by_chatterbox(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    voice_id = str(uuid4())
    clip = SpeechClipRecord(
        clip_id=uuid4(), owner_id=uuid4(), voice={"kind": "recorded", "voice_id": voice_id},
        text="Hello there.", delivery="neutral", effects={}, status="queued",
    )  # fmt: skip
    stored: dict[str, bytes] = {}
    updates: list[dict[str, Any]] = []
    settings = Settings(tts_backend="gemini", tts_recorded_backend="chatterbox", config_dir=CONFIG)
    ctx = pipeline_ctx(
        tmp_path,
        settings,
        repo=SimpleNamespace(
            get_speech_clip=lambda _: clip,
            finish_speech_clip=lambda _, **fields: updates.append(fields),
        ),
        store=SimpleNamespace(
            exists=lambda key: key in stored,
            get=lambda key: stored[key],
            put=lambda key, data, _: stored.__setitem__(key, data),
        ),
    )
    engines: list[str] = []
    monkeypatch.setattr(speak, "backend_unavailable", lambda _: None)
    monkeypatch.setattr(speak, "prune_withdrawn_voices", lambda _: 0)
    monkeypatch.setattr(
        speak, "registered_voices", lambda c, chosen, hosts: {"Alex": ClonedVoice()}
    )

    def backend(c: Any, *_: Any) -> PlaceholderBackend:
        engines.append(c.settings.tts_backend)
        return PlaceholderBackend()

    monkeypatch.setattr(speak, "_backend", backend)
    assert speak.speak_clip(clip.clip_id, ctx) == "done", updates
    assert engines == ["chatterbox"]


def test_hosts_without_a_usable_voice_get_the_default_one(tmp_path: Path) -> None:
    # voices.yaml names a recording for Alex that a server does not have.
    voices = tmp_path / "voices.yaml"
    voices.write_text(
        "chatterbox:\n  Alex:\n    reference_audio: assets/voices/missing.wav\n"
        "    speaker: A\n    consent: c\n    license: l\n  Sam:\n    reference_audio: null\n",
        encoding="utf-8",
    )
    settings = Settings(
        tts_backend="chatterbox", voices_file=voices, assets_dir=tmp_path / "assets"
    )
    ctx = pipeline_ctx(tmp_path, settings)
    recorded = ClonedVoice(
        reference_audio=str(tmp_path / "sam.wav"), speaker="S", consent="c", license="l"
    )
    filled = service.default_voices_for_the_rest(ctx, ["Alex", "Sam"], {"Sam": recorded})
    assert filled == {"Sam": recorded, "Alex": ClonedVoice()}
    # A host the file can voice keeps the file's voice.
    assert service.default_voices_for_the_rest(ctx, ["Sam"], {}) == {}


def episode_ctx(host_voices: dict[str, str]) -> tuple[PipelineContext, dict[str, Any]]:
    script = {"segments": {"1": [{"speaker": "Alex", "text": "Hi.", "claims": []},
                                 {"speaker": "Sam", "text": "Hello.", "claims": []}]}}  # fmt: skip
    episode = SimpleNamespace(show_id=uuid4(), script=script, manifest={})
    saved: dict[str, Any] = {}
    stored: dict[str, bytes] = {}
    settings = Settings(tts_backend="gemini", tts_recorded_backend="chatterbox", config_dir=CONFIG)
    ctx = pipeline_ctx(
        Path(),
        settings,
        repo=SimpleNamespace(
            get_episode=lambda _: episode,
            get_show=lambda _: SimpleNamespace(
                topic="Tides", host_count=2, host_voices=host_voices
            ),
            update_episode=lambda _, **fields: saved.update(fields),
        ),
        store=SimpleNamespace(
            exists=lambda key: key in stored,
            put=lambda key, data, _: stored.__setitem__(key, data),
        ),
    )
    return ctx, saved


@pytest.mark.parametrize(("host_voices", "engine"), [({}, "gemini"), ({"Sam": "v1"}, "chatterbox")])
def test_an_episode_with_a_recorded_host_voice_is_voiced_by_chatterbox(
    host_voices: dict[str, str], engine: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx, saved = episode_ctx(host_voices)
    recorded = ClonedVoice(reference_audio="/v1.wav", speaker="S", consent="c", license="l")
    seen: dict[str, Any] = {}
    monkeypatch.setattr(service, "backend_unavailable", lambda _: None)
    monkeypatch.setattr(service, "prune_withdrawn_voices", lambda _: 0)
    monkeypatch.setattr(
        service,
        "registered_voices",
        lambda c, chosen, hosts: (
            {"Sam": recorded} if c.settings.tts_backend == "chatterbox" else {}
        ),
    )
    monkeypatch.setattr(
        service, "default_voices_for_the_rest", lambda c, hosts, o: {**o, "Alex": ClonedVoice()}
    )

    def backend(c: Any, hosts: tuple[str, ...], overrides: dict[str, ClonedVoice]) -> Any:
        seen.update(engine=c.settings.tts_backend, overrides=overrides)
        return PlaceholderBackend()

    monkeypatch.setattr(service, "_backend", backend)
    service.synthesise_voices(uuid4(), ctx)
    assert seen["engine"] == engine
    if engine == "chatterbox":
        assert seen["overrides"] == {"Sam": recorded, "Alex": ClonedVoice()}
    assert saved["voice_lines"]


def test_an_episode_fails_plainly_when_chatterbox_is_not_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx, _ = episode_ctx({"Sam": "v1"})
    monkeypatch.setattr(service, "backend_unavailable", lambda _: "Chatterbox is not installed.")
    with pytest.raises(RuntimeError, match="recorded voices, but Chatterbox is not installed"):
        service.synthesise_voices(uuid4(), ctx)

"""Voices registered in the web app reach Chatterbox as consented registry entries."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from podcast_engine.common.repository import VoiceRecord
from podcast_engine.stages.voice.registry import (
    ClonedVoice,
    VoiceRegistry,
    problems_with,
    with_overrides,
)
from podcast_engine.stages.voice.service import registered_voices


def context(tmp_path: Path, backend: str, records: dict[str, VoiceRecord]) -> Any:
    stored = {record.object_key: b"RIFF-recording" for record in records.values()}
    return SimpleNamespace(
        settings=SimpleNamespace(tts_backend=backend, data_dir=tmp_path),
        repo=SimpleNamespace(get_voices=lambda ids: {i: records[i] for i in ids if i in records}),
        store=SimpleNamespace(get=lambda key: stored[key]),
    )


def record() -> VoiceRecord:
    return VoiceRecord(
        voice_id=uuid4(),
        speaker="Ada Lovelace",
        license="Used only to voice this account's podcasts",
        consent={"signed_by": "Ada Lovelace", "agreed_at": "2026-10-25T10:00:00+00:00",
                 "relationship": "self", "version": "2026-10-25"},
        object_key="voices/owner/ada.wav",
        sha256="abc123",
    )  # fmt: skip


def test_a_hosts_registered_voice_becomes_a_consented_clone(tmp_path: Path) -> None:
    ada = record()
    ctx = context(tmp_path, "chatterbox", {str(ada.voice_id): ada})
    voices = registered_voices(ctx, {"Alex": str(ada.voice_id)}, ["Alex", "Sam"])
    voice = voices["Alex"]
    assert voice.is_clone
    assert Path(str(voice.reference_audio)).read_bytes() == b"RIFF-recording"
    assert voice.speaker == "Ada Lovelace"
    assert "signed in Podcast Engine by Ada Lovelace" in voice.consent
    # It passes the same consent check as a voice from voices.yaml.
    registry = with_overrides(VoiceRegistry(chatterbox={"Sam": ClonedVoice()}), voices)
    assert problems_with(registry, ["Alex", "Sam"], Path("/")) == []


def test_deleted_voices_unused_hosts_and_other_backends_are_skipped(tmp_path: Path) -> None:
    ada = record()
    ctx = context(tmp_path, "chatterbox", {str(ada.voice_id): ada})
    assert registered_voices(ctx, {"Alex": str(uuid4())}, ["Alex"]) == {}  # deleted since
    assert registered_voices(ctx, {"Riley": str(ada.voice_id)}, ["Alex", "Sam"]) == {}
    gemini = context(tmp_path, "gemini", {str(ada.voice_id): ada})
    assert registered_voices(gemini, {"Alex": str(ada.voice_id)}, ["Alex"]) == {}

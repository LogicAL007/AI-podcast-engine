from pathlib import Path

import pytest

from podcast_engine.stages.voice.registry import (
    ClonedVoice,
    VoiceRegistry,
    VoiceRegistryError,
    fingerprint,
    load_registry,
    resolve_voices,
)


def _reference(root: Path, name: str = "alex.wav", data: bytes = b"audio") -> str:
    path = root / "assets" / "voices" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return f"assets/voices/{name}"


def _consented(reference: str) -> ClonedVoice:
    return ClonedVoice(
        reference_audio=reference, speaker="A. Person", consent="docs/consent/a.pdf", license="CC0"
    )


def test_default_voice_needs_no_consent(tmp_path: Path) -> None:
    registry = VoiceRegistry(chatterbox={"Alex": ClonedVoice()})
    assert resolve_voices(registry, ["Alex"], tmp_path)["Alex"].is_clone is False


def test_clone_without_consent_record_is_refused(tmp_path: Path) -> None:
    reference = _reference(tmp_path)
    registry = VoiceRegistry(chatterbox={"Alex": ClonedVoice(reference_audio=reference)})
    with pytest.raises(VoiceRegistryError, match="speaker, consent, license"):
        resolve_voices(registry, ["Alex"], tmp_path)


def test_partial_consent_record_is_refused(tmp_path: Path) -> None:
    reference = _reference(tmp_path)
    voice = ClonedVoice(reference_audio=reference, speaker="A. Person", consent="  ", license="CC0")
    with pytest.raises(VoiceRegistryError, match="fill in consent"):
        resolve_voices(VoiceRegistry(chatterbox={"Alex": voice}), ["Alex"], tmp_path)


def test_missing_reference_file_is_refused(tmp_path: Path) -> None:
    registry = VoiceRegistry(chatterbox={"Alex": _consented("assets/voices/nope.wav")})
    with pytest.raises(VoiceRegistryError, match=r"nope\.wav not found"):
        resolve_voices(registry, ["Alex"], tmp_path)


def test_every_problem_is_reported_at_once(tmp_path: Path) -> None:
    registry = VoiceRegistry(
        chatterbox={"Alex": ClonedVoice(reference_audio="assets/voices/x.wav")}
    )
    with pytest.raises(VoiceRegistryError) as error:
        resolve_voices(registry, ["Alex", "Sam"], tmp_path)
    message = str(error.value)
    assert "Sam: no entry" in message
    assert "Alex: a cloned voice needs a consent record" in message
    assert "x.wav not found" in message


def test_consented_clone_with_file_is_accepted(tmp_path: Path) -> None:
    voice = _consented(_reference(tmp_path))
    resolved = resolve_voices(VoiceRegistry(chatterbox={"Alex": voice}), ["Alex"], tmp_path)
    assert resolved["Alex"] == voice


def test_fingerprint_follows_the_recording(tmp_path: Path) -> None:
    voice = _consented(_reference(tmp_path, data=b"one"))
    before = fingerprint(voice, tmp_path)
    _reference(tmp_path, data=b"two")
    assert fingerprint(voice, tmp_path) != before
    assert fingerprint(ClonedVoice(), tmp_path) == "default"


def test_shipped_registry_parses_and_refuses_until_filled_in(tmp_path: Path) -> None:
    shipped = Path(__file__).resolve().parents[2] / "config" / "voices.yaml"
    registry = load_registry(shipped)
    assert set(registry.chatterbox) == {"Alex", "Sam"}
    with pytest.raises(VoiceRegistryError):
        resolve_voices(registry, ["Alex", "Sam"], tmp_path)

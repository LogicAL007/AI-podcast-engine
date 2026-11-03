"""Registering cloned voices: the consent form, the recording's checks, privacy and withdrawal."""

from typing import Any
from uuid import UUID, uuid4

import numpy as np
import pytest

from podcast_engine.api.models.voices_model import (
    CONSENT_SECTIONS,
    CONSENT_STATEMENT,
    CONSENT_VERSION,
)
from podcast_engine.common.audio import SR, wav_bytes
from tests.unit.api.conftest import ADMIN, Harness


@pytest.fixture
def harness() -> Harness:
    return Harness()


def speech(seconds: float = 8.0, amplitude: float = 0.3, rate: int = SR) -> bytes:
    t = np.arange(int(rate * seconds)) / rate
    return wav_bytes((amplitude * np.sin(2 * np.pi * 180 * t)).astype(np.float32), rate)


CONSENT: dict[str, Any] = {
    "speaker": "Ada Lovelace",
    "signature": "ada  lovelace",
    "relationship": "self",
    "agree_clone": "true",
    "agree_ai_label": "true",
    "agree_withdraw": "true",
    "name": "My voice",
}


def register(harness: Harness, audio: bytes | None = None, /, **form: Any) -> Any:
    return harness.client.post(
        "/v1/voices",
        data={**CONSENT, **form},
        files={"audio": ("voice.wav", speech() if audio is None else audio, "audio/wav")},
    )


def test_a_signed_recording_is_registered_with_its_consent_record(harness: Harness) -> None:
    response = register(harness)
    assert response.status_code == 201
    voice = response.json()
    assert voice["speaker"] == "Ada Lovelace"
    assert voice["source"] == "recorded"
    assert voice["duration_seconds"] == pytest.approx(8.0)
    assert voice["consent"]["version"] == CONSENT_VERSION
    assert voice["consent"]["statement"] == CONSENT_STATEMENT
    assert voice["consent"]["signed_by"] == "ada lovelace"
    assert voice["consent"]["relationship"] == "self"

    played = harness.client.get(voice["audio"])
    assert played.status_code == 200
    assert played.headers["content-type"] == "audio/wav"
    assert played.headers["cache-control"] == "private, no-store"
    assert harness.client.get("/v1/voices").json()["total"] == 1


def test_the_consent_form_can_be_read_in_full_before_recording(harness: Harness) -> None:
    form = harness.client.get("/v1/voices/consent").json()
    assert form["version"] == CONSENT_VERSION
    assert form["statement"] == CONSENT_STATEMENT
    assert form["pdf"] == "/v1/voices/consent.pdf"
    headings = [section["heading"] for section in form["sections"]]
    assert headings == [heading for heading, _ in CONSENT_SECTIONS]
    # What the meaningful-consent guidance asks a form to emphasise is all there.
    for topic in ("What is collected", "What it is used for", "Risks", "Withdrawing consent"):
        assert any(topic in heading for heading in headings)
    # The stored statement is the whole form, so a signed voice keeps every word agreed to.
    for _, paragraphs in CONSENT_SECTIONS:
        for text in paragraphs:
            assert text in CONSENT_STATEMENT


def test_the_consent_form_downloads_as_a_pdf(harness: Harness) -> None:
    response = harness.client.get("/v1/voices/consent.pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF-")
    disposition = response.headers["content-disposition"]
    assert disposition == f'inline; filename="voice-consent-form-{CONSENT_VERSION}.pdf"'


def test_voices_signed_on_an_earlier_form_keep_their_record(harness: Harness) -> None:
    voice = register(harness).json()
    _, stored = next(iter(harness.voices.rows.values()))
    stored.consent.version, stored.consent.statement = "2026-10-25", "The earlier wording."
    again = harness.client.get(f"/v1/voices/{voice['voice_id']}").json()
    assert (again["consent"]["version"], again["consent"]["statement"]) == (
        "2026-10-25",
        "The earlier wording.",
    )


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        ({"agree_withdraw": "false"}, "all three consent statements"),
        ({"signature": "Someone Else"}, "sign with the speaker's name"),
        ({"relationship": "permission"}, "written permission is kept"),
        ({"speaker": "  "}, "name the person speaking"),
    ],
)
def test_an_incomplete_consent_form_is_refused(
    harness: Harness, change: dict[str, str], problem: str
) -> None:
    response = register(harness, **change)
    assert response.status_code == 422
    assert problem in response.json()["detail"]
    assert harness.store.objects == {}  # nothing stored


def test_someone_elses_voice_needs_a_note_of_their_written_permission(harness: Harness) -> None:
    response = register(
        harness,
        relationship="permission",
        signature="Charles Babbage",
        permission_record="Signed release form, shared drive /consent/ada.pdf",
    )
    assert response.status_code == 201
    consent = response.json()["consent"]
    assert consent["relationship"] == "permission"
    assert consent["permission_record"].startswith("Signed release form")


@pytest.mark.parametrize(
    ("audio", "status", "hint"),
    [
        (speech(rate=48_000), 415, "24000 Hz mono 16-bit WAV"),
        (b"ID3 not a wav", 415, "WAV"),
        (speech(seconds=2), 422, "use 5 to 90 s"),
        (speech(seconds=95), 422, "use 5 to 90 s"),
        (speech(amplitude=0.0), 422, "silent"),
    ],
)
def test_recordings_are_checked(harness: Harness, audio: bytes, status: int, hint: str) -> None:
    response = register(harness, audio)
    assert response.status_code == status
    assert hint in response.json()["detail"]


def test_voices_are_private_to_their_owner(harness: Harness) -> None:
    voice_id = register(harness).json()["voice_id"]
    owner, voice = harness.voices.rows.pop(next(iter(harness.voices.rows)))
    harness.voices.rows[voice.voice_id] = (uuid4(), voice)  # now someone else's
    assert harness.client.get(f"/v1/voices/{voice_id}").status_code == 404
    assert harness.client.get(f"/v1/voices/{voice_id}/audio.wav").status_code == 404
    assert harness.client.delete(f"/v1/voices/{voice_id}").status_code == 404
    assert owner == ADMIN.user_id


def test_at_most_ten_voices(harness: Harness) -> None:
    for _ in range(10):
        assert register(harness).status_code == 201
    assert register(harness).status_code == 409


def test_hosts_speak_with_registered_voices_and_deleting_one_withdraws_it(
    harness: Harness,
) -> None:
    voice_id = register(harness).json()["voice_id"]
    show = harness.client.post(
        "/v1/shows", json={"topic": "Tides", "host_voices": {"Alex": voice_id}}
    ).json()
    assert show["host_voices"] == {"Alex": voice_id}
    key = harness.voices.rows[next(iter(harness.voices.rows))][1].object_key
    assert key in harness.store.objects
    clip = "tts/made-with-this-voice.wav"
    harness.store.put(clip, b"RIFF", "audio/wav")
    harness.voices.clips[UUID(voice_id)] = [clip]

    assert harness.client.delete(f"/v1/voices/{voice_id}").status_code == 204
    assert key not in harness.store.objects
    assert clip not in harness.store.objects  # the speech made with it goes too
    assert harness.client.get(f"/v1/shows/{show['show_id']}").json()["host_voices"] == {}


def test_a_host_cannot_use_a_voice_that_is_not_yours_or_a_host_that_does_not_exist(
    harness: Harness,
) -> None:
    unknown = harness.client.post(
        "/v1/shows", json={"topic": "Tides", "host_voices": {"Alex": str(uuid4())}}
    )
    assert unknown.status_code == 422
    assert "no such voice" in unknown.json()["detail"]
    voice_id = register(harness).json()["voice_id"]
    wrong_host = harness.client.post(
        "/v1/shows", json={"topic": "Tides", "host_voices": {"Morgan": voice_id}}
    )
    assert wrong_host.status_code == 422

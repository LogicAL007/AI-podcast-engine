"""Business rules for cloned voices. No HTTP and no SQL in here.

The PRD forbids cloning anyone without their permission, so a voice is refused unless its consent
form is complete: the speaker signs for their own voice, or the account holder states where the
speaker's written permission is kept. The signed text is stored verbatim with the recording.
"""

import hashlib
import wave
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

import numpy as np

from podcast_engine.api.errors import (
    ConflictError,
    InvalidInputError,
    NotFoundError,
    PayloadTooLargeError,
    UnsupportedMediaTypeError,
)
from podcast_engine.api.models.pagination_model import Paged
from podcast_engine.api.models.voices_model import (
    CONSENT_STATEMENT,
    CONSENT_VERSION,
    ConsentForm,
    VoiceRead,
    VoiceSource,
)
from podcast_engine.api.repositories.voices_repository import VoiceRepository
from podcast_engine.common.audio import SR, read_wav_bytes
from podcast_engine.common.storage import ObjectStore

MAX_BYTES = 10 * 1024 * 1024
MIN_SECONDS = 5.0
MAX_SECONDS = 90.0
MAX_VOICES = 10
SILENT_RMS = 0.005  # below this the "recording" is silence or a muted microphone


def voice_key(owner: UUID, voice_id: UUID) -> str:
    """Object key of a voice recording. Private: only its owner, through the API, can play it."""
    return f"voices/{owner}/{voice_id}.wav"


def _tidy(value: str) -> str:
    return " ".join(value.split())


def check_consent(form: ConsentForm) -> list[str]:
    """Everything missing from the consent form, so one reply lists it all."""
    problems: list[str] = []
    if not (form.agree_clone and form.agree_ai_label and form.agree_withdraw):
        problems.append("all three consent statements must be agreed to")
    speaker, signature = _tidy(form.speaker), _tidy(form.signature)
    if not speaker:
        problems.append("name the person speaking")
    if not signature:
        problems.append("type your full name as a signature")
    if form.relationship == "self" and speaker and signature.casefold() != speaker.casefold():
        problems.append("for your own voice, sign with the speaker's name")
    if form.relationship == "permission" and len(_tidy(form.permission_record)) < 5:
        problems.append("say where the speaker's written permission is kept")
    if not _tidy(form.license):
        problems.append("state the terms the recording may be used under")
    if len(speaker) > 100 or len(signature) > 100 or len(_tidy(form.name)) > 60:
        problems.append("names are limited to 100 characters (the label to 60)")
    return problems


class VoiceService:
    def __init__(
        self,
        voices: VoiceRepository,
        store: ObjectStore,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._voices = voices
        self._store = store
        self._now = now

    def register(
        self, owner: UUID, form: ConsentForm, *, source: VoiceSource, data: bytes
    ) -> VoiceRead:
        """Keep a recording as a cloneable voice, with its consent record."""
        problems = check_consent(form)
        if problems:
            raise InvalidInputError("consent form: " + "; ".join(problems))
        if len(data) > MAX_BYTES:
            raise PayloadTooLargeError(f"the recording is larger than {MAX_BYTES // 2**20} MB")
        try:
            samples = read_wav_bytes(data, name="recording")
        except (ValueError, EOFError, wave.Error) as error:
            raise UnsupportedMediaTypeError(
                f"the recording must be a {SR} Hz mono 16-bit WAV (the web app converts it)"
            ) from error
        seconds = len(samples) / SR
        if not MIN_SECONDS <= seconds <= MAX_SECONDS:
            raise InvalidInputError(
                f"the recording is {seconds:.0f} s; use {MIN_SECONDS:.0f} to {MAX_SECONDS:.0f} s"
            )
        if float(np.sqrt(np.mean(samples**2))) < SILENT_RMS:
            raise InvalidInputError("the recording is silent; check the microphone and try again")
        if self._voices.count(owner) >= MAX_VOICES:
            raise ConflictError(f"you already have {MAX_VOICES} voices; delete one first")

        voice_id = uuid4()
        key = voice_key(owner, voice_id)
        self._store.put(key, data, "audio/wav")
        speaker = _tidy(form.speaker)
        consent = {
            "version": CONSENT_VERSION,
            "statement": CONSENT_STATEMENT,
            "relationship": form.relationship,
            "signed_by": _tidy(form.signature),
            "permission_record": _tidy(form.permission_record)
            if form.relationship == "permission"
            else "",
            "agreed_at": self._now().isoformat(),
        }
        return self._voices.add(
            owner,
            {
                "voice_id": voice_id,
                "name": _tidy(form.name) or f"{speaker}'s voice",
                "speaker": speaker,
                "license": _tidy(form.license),
                "source": source,
                "consent": consent,
                "object_key": key,
                "size_bytes": len(data),
                "duration_seconds": round(seconds, 2),
                "sha256": hashlib.sha256(data).hexdigest(),
            },
        )

    def list_page(self, owner: UUID, *, limit: int, offset: int) -> Paged[VoiceRead]:
        return self._voices.list_page(owner, limit=limit, offset=offset)

    def get(self, voice_id: UUID, owner: UUID) -> VoiceRead:
        voice = self._voices.get(voice_id, owner)
        if voice is None:
            raise NotFoundError("voice", voice_id)
        return voice

    def audio(self, voice_id: UUID, owner: UUID) -> bytes:
        voice = self.get(voice_id, owner)
        if not self._store.exists(voice.object_key):
            raise NotFoundError("recording of voice", voice_id)
        return self._store.get(voice.object_key)

    def delete(self, voice_id: UUID, owner: UUID) -> None:
        """Withdraw a voice: its record and recording go, and no host of a show uses it."""
        voice = self.get(voice_id, owner)
        self._voices.delete(voice_id, owner)
        self._store.delete(voice.object_key)

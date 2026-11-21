"""Business rules for the music library. No HTTP and no SQL in here.

Built-in tracks are made in code (``podcast_engine.common.music``) and belong to everyone. Uploaded
tracks belong to their owner, who confirms they have the right to use them; the web app converts
any audio file to the pipeline's 24 kHz mono WAV before it is sent.
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
from podcast_engine.api.models.music_model import MusicTrackRead
from podcast_engine.api.repositories.music_repository import MusicRepository
from podcast_engine.common.audio import SR, read_wav_bytes, wav_bytes
from podcast_engine.common.music import BUILTIN_TRACKS, Role, builtin_audio, is_builtin
from podcast_engine.common.storage import ObjectStore

MAX_BYTES = 20 * 1024 * 1024  # 6 minutes of 24 kHz mono 16-bit is about 17 MB
MIN_SECONDS = 1.0
MAX_SECONDS = 360.0
MAX_TRACKS = 20
SILENT_RMS = 0.002


def music_key(owner: UUID, track_id: UUID) -> str:
    """Object key of an uploaded track. Private: played only through the API, by its owner."""
    return f"music/{owner}/{track_id}.wav"


def builtin_tracks() -> list[MusicTrackRead]:
    return [
        MusicTrackRead(
            track_id=track.track_id,
            name=track.name,
            role=track.role,
            builtin=True,
            description=track.description,
            duration_seconds=round(len(builtin_audio(track.track_id)) / SR, 2),
        )
        for track in BUILTIN_TRACKS.values()
    ]


class MusicService:
    def __init__(
        self,
        tracks: MusicRepository,
        store: ObjectStore,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._tracks = tracks
        self._store = store
        self._now = now

    def list_all(self, owner: UUID) -> list[MusicTrackRead]:
        """The built-in tracks, then yours, newest first."""
        return builtin_tracks() + self._tracks.list_all(owner)

    def upload(
        self, owner: UUID, *, name: str, role: Role, credit: str, rights: bool, data: bytes
    ) -> MusicTrackRead:
        name, credit = " ".join(name.split()), " ".join(credit.split())
        if not rights:
            raise InvalidInputError(
                "confirm that you own this music or have a licence to use it in your podcast"
            )
        if not name or len(name) > 80:
            raise InvalidInputError("give the track a name of up to 80 characters")
        if len(credit) > 200:
            raise InvalidInputError("the credit line is limited to 200 characters")
        if len(data) > MAX_BYTES:
            raise PayloadTooLargeError(f"the track is larger than {MAX_BYTES // 2**20} MB")
        try:
            samples = read_wav_bytes(data, name="track")
        except (ValueError, EOFError, wave.Error) as error:
            raise UnsupportedMediaTypeError(
                f"the track must be a {SR} Hz mono 16-bit WAV (the web app converts it)"
            ) from error
        seconds = len(samples) / SR
        if not MIN_SECONDS <= seconds <= MAX_SECONDS:
            raise InvalidInputError(
                f"the track is {seconds:.0f} s; use {MIN_SECONDS:.0f} s to "
                f"{MAX_SECONDS / 60:.0f} minutes"
            )
        if float(np.sqrt(np.mean(samples**2))) < SILENT_RMS:
            raise InvalidInputError("the track is silent")
        if self._tracks.count(owner) >= MAX_TRACKS:
            raise ConflictError(f"you already have {MAX_TRACKS} tracks; delete one first")
        track_id = uuid4()
        key = music_key(owner, track_id)
        self._store.put(key, data, "audio/wav")
        return self._tracks.add(
            owner,
            {
                "track_id": track_id,
                "name": name,
                "role": role,
                "credit": credit,
                "object_key": key,
                "size_bytes": len(data),
                "duration_seconds": round(seconds, 2),
                "sha256": hashlib.sha256(data).hexdigest(),
                "rights_confirmed_at": self._now(),
            },
        )

    def _uploaded(self, track_id: str, owner: UUID) -> MusicTrackRead:
        try:
            track = self._tracks.get(UUID(track_id), owner)
        except ValueError:
            track = None
        if track is None:
            raise NotFoundError("music track", track_id)
        return track

    def audio(self, track_id: str, owner: UUID) -> bytes:
        if is_builtin(track_id):
            if track_id not in BUILTIN_TRACKS:
                raise NotFoundError("music track", track_id)
            return wav_bytes(np.asarray(builtin_audio(track_id)))
        track = self._uploaded(track_id, owner)
        if not track.object_key or not self._store.exists(track.object_key):
            raise NotFoundError("audio of music track", track_id)
        return self._store.get(track.object_key)

    def delete(self, track_id: str, owner: UUID) -> None:
        """Delete an uploaded track; shows that used it go back to the default for that slot.
        Episodes already made keep their audio."""
        if is_builtin(track_id):
            raise ConflictError("built-in tracks cannot be deleted")
        track = self._uploaded(track_id, owner)
        self._tracks.delete(UUID(track.track_id), owner)
        if track.object_key:
            self._store.delete(track.object_key)

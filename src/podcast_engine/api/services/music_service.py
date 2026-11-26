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
    """Return the object key of an uploaded track.

    Private: played only through the API, by its owner.

    Args:
        owner: The user who uploaded it.
        track_id: The track.

    Returns:
        The track's key in object storage.
    """
    return f"music/{owner}/{track_id}.wav"


def builtin_tracks() -> list[MusicTrackRead]:
    """List the built-in tracks, which are made in code and belong to everyone.

    Returns:
        Each built-in track with its length, rendered once per process.
    """
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
    """Business rules for the music library. No HTTP and no SQL in here.

    Built-in tracks are made in code (``podcast_engine.common.music``) and belong to everyone.
    Uploaded tracks belong to their owner, who confirms they have the right to use them; the web app
    converts any audio file to the pipeline's 24 kHz mono WAV before it is sent.
    """

    def __init__(
        self,
        tracks: MusicRepository,
        store: ObjectStore,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        """Create the service.

        Args:
            tracks: Where uploaded tracks' details are stored.
            store: Where the audio is stored.
            now: Returns the current time; replaced in tests.
        """
        self._tracks = tracks
        self._store = store
        self._now = now

    def list_all(self, owner: UUID) -> list[MusicTrackRead]:
        """Return the built-in tracks, then the owner's, newest first.

        Args:
            owner: The user asking.

        Returns:
            Every track the owner's shows can use.
        """
        return builtin_tracks() + self._tracks.list_all(owner)

    def upload(
        self, owner: UUID, *, name: str, role: Role, credit: str, rights: bool, data: bytes
    ) -> MusicTrackRead:
        """Check and store an uploaded track.

        The name (up to 80 characters) and credit (up to 200) are tidied. The audio must be 24 kHz
        mono 16-bit WAV, 1 second to 6 minutes long and not silent, and an account holds at most 20
        tracks. When the owner confirmed their rights is recorded.

        Args:
            owner: The user uploading.
            name: The track's name.
            role: What it is for: bed, intro, outro, sting or any.
            credit: Credit line for the show notes, or empty.
            rights: Whether the owner confirmed they may use the music.
            data: The track's WAV bytes.

        Returns:
            The stored track.

        Raises:
            InvalidInputError: Rights not confirmed, a bad name or credit, the wrong length, or
                silence.
            PayloadTooLargeError: The file is larger than the limit.
            UnsupportedMediaTypeError: The file is not 24 kHz mono 16-bit WAV.
            ConflictError: The account already has the most tracks allowed.
        """
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
        """Return one of the owner's uploaded tracks.

        Args:
            track_id: The track's id, as text.
            owner: The user asking.

        Returns:
            The track.

        Raises:
            NotFoundError: The id is not a UUID, or the owner has no such track.
        """
        try:
            track = self._tracks.get(UUID(track_id), owner)
        except ValueError:
            track = None
        if track is None:
            raise NotFoundError("music track", track_id)
        return track

    def audio(self, track_id: str, owner: UUID) -> bytes:
        """Return a track's audio: a built-in one, or one of the owner's.

        Args:
            track_id: ``builtin:...`` or an upload's id.
            owner: The user asking.

        Returns:
            The track as WAV bytes.

        Raises:
            NotFoundError: There is no such track, or its audio is missing from storage.
        """
        if is_builtin(track_id):
            if track_id not in BUILTIN_TRACKS:
                raise NotFoundError("music track", track_id)
            return wav_bytes(np.asarray(builtin_audio(track_id)))
        track = self._uploaded(track_id, owner)
        if not track.object_key or not self._store.exists(track.object_key):
            raise NotFoundError("audio of music track", track_id)
        return self._store.get(track.object_key)

    def delete(self, track_id: str, owner: UUID) -> None:
        """Delete an uploaded track and its audio.

        Shows that used it go back to the default for that slot; episodes already made keep their
        audio.

        Args:
            track_id: The track to delete.
            owner: The user asking.

        Raises:
            ConflictError: The track is built in.
            NotFoundError: The owner has no such track.
        """
        if is_builtin(track_id):
            raise ConflictError("built-in tracks cannot be deleted")
        track = self._uploaded(track_id, owner)
        self._tracks.delete(UUID(track.track_id), owner)
        if track.object_key:
            self._store.delete(track.object_key)

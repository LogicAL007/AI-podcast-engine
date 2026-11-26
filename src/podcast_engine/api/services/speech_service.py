from collections.abc import Callable
from uuid import UUID, uuid4

from podcast_engine.api.errors import NotFoundError, TooManyRequestsError
from podcast_engine.api.models.speech_model import (
    MAX_CHARACTERS,
    EngineVoiceOption,
    RecordedVoice,
    SpeechClipRead,
    SpeechCreate,
    SpeechEngine,
)
from podcast_engine.api.repositories.assistant_usage_repository import AssistantUsage
from podcast_engine.api.repositories.speech_repository import SpeechRepository
from podcast_engine.api.repositories.voices_repository import VoiceRepository
from podcast_engine.common.config import Settings
from podcast_engine.common.context import HOST_NAMES
from podcast_engine.common.logging import get_logger
from podcast_engine.common.models import Delivery
from podcast_engine.common.quota import DailyBudget
from podcast_engine.common.storage import ObjectStore
from podcast_engine.common.voice_fx import PRESETS
from podcast_engine.stages.voice.backends import GEMINI_VOICES, speaks_recorded_voices

log = get_logger("api.speech")

RECENT = 20  # clips listed in the studio
Enqueue = Callable[[str], str]


class SpeechService:
    """Business rules for type-to-speech. No HTTP and no SQL in here.

    A clip is a job for the voice worker: it is stored as queued, sent to the voice queue, and
    voiced by whichever worker has the voices (Chatterbox with the recordings on the Mac, or
    Gemini). The web app polls it until it is done. Each person may make ``speech_clips_per_hour``
    clips an hour, and with Gemini, clips may use only half of the day's voice budget, so episodes
    keep the rest.
    """

    def __init__(
        self,
        clips: SpeechRepository,
        voices: VoiceRepository,
        store: ObjectStore,
        usage: AssistantUsage,
        enqueue: Enqueue,
        settings: Settings,
        budget: DailyBudget | None,
    ) -> None:
        """Create the service.

        Args:
            clips: Where clips are stored.
            voices: Where registered voices are stored, to check ownership.
            store: Where the clips' audio is stored.
            usage: The per-person hourly clip counter.
            enqueue: Sends a clip id to the voice queue.
            settings: Which voice backend runs, the hourly limit and the daily TTS budget.
            budget: The shared daily Gemini budget, or None when there is no cap.
        """
        self._clips = clips
        self._voices = voices
        self._store = store
        self._usage = usage
        self._enqueue = enqueue
        self._settings = settings
        self._budget = budget

    def _reserve(self) -> int:
        """Return how many Gemini voice requests are kept back for episodes.

        Returns:
            Half the day's TTS budget, rounded up.
        """
        return (self._settings.tts_requests_per_day + 1) // 2

    def _clips_left(self) -> int | None:
        """Return how many clips today's Gemini budget still allows.

        Returns:
            The budget left after the episodes' reserve, or None when Gemini does not voice here or
            nothing is capped.
        """
        if self._settings.tts_backend != "gemini" or self._budget is None:
            return None
        left = self._budget.available(self._settings.tts_model)
        return None if left is None else max(left - self._reserve(), 0)

    def engine(self) -> SpeechEngine:
        """Describe what this server's voice engine can say.

        Returns:
            The backend, whether recorded voices work, the engine's own voices, the budget left, the
            deliveries and the effect presets.
        """
        backend = self._settings.tts_backend
        if backend == "gemini":
            options = [
                EngineVoiceOption(host=h, label=f"{GEMINI_VOICES[h]} (Gemini voice)")
                for h in HOST_NAMES
            ]
        else:
            options = [EngineVoiceOption(host=h, label=f"{h}'s default voice") for h in HOST_NAMES]
        return SpeechEngine(
            backend=backend,
            recorded_voices=speaks_recorded_voices(self._settings),
            engine_voices=options,
            uses_quota=backend == "gemini",
            clips_left_today=self._clips_left(),
            max_characters=MAX_CHARACTERS,
            deliveries=[d.value for d in Delivery],
            presets=PRESETS,
        )

    def create(self, owner: UUID, data: SpeechCreate) -> SpeechClipRead:
        """Queue a clip to be voiced.

        A recorded voice must be the caller's own. If the job queue cannot be reached, the clip is
        stored as failed with a reason, rather than lost.

        Args:
            owner: The user asking.
            data: The text, voice, delivery and effects.

        Returns:
            The clip, queued (or failed when the queue was unavailable).

        Raises:
            NotFoundError: The recorded voice is not the caller's.
            TooManyRequestsError: Today's Gemini budget for clips, or the caller's hourly limit, is
                used up.
        """
        if isinstance(data.voice, RecordedVoice) and not self._voices.owned(
            {data.voice.voice_id}, owner
        ):
            raise NotFoundError("voice", data.voice.voice_id)
        # A recorded voice is spoken by Chatterbox (as the voice engine or the second engine), which
        # uses none of Gemini's budget.
        on_gemini = self._settings.tts_backend == "gemini" and not (
            isinstance(data.voice, RecordedVoice) and speaks_recorded_voices(self._settings)
        )
        if on_gemini and self._clips_left() == 0:
            assert self._budget is not None  # noqa: S101 - _clips_left is None without one
            raise TooManyRequestsError(
                "Today's Gemini voice budget for trying voices is used up (half of the day's "
                "budget is kept for episodes). It resets at midnight Pacific time.",
                retry_after=int(self._budget.resets_in().total_seconds()),
            )
        if self._usage.take(owner, self._settings.speech_clips_per_hour) is None:
            raise TooManyRequestsError(
                f"You have made {self._settings.speech_clips_per_hour} clips this hour; try "
                "again later.",
                retry_after=self._usage.retry_after(),
            )
        clip = self._clips.add(
            owner,
            {
                "clip_id": uuid4(),
                "voice": data.voice.model_dump(mode="json"),
                "text": " ".join(data.text.split()),
                "delivery": data.delivery.value,
                "effects": data.effects.model_dump(),
            },
        )
        try:
            self._enqueue(str(clip.clip_id))
        except Exception:
            log.exception("speech_enqueue_failed", clip_id=str(clip.clip_id))
            self._clips.fail(clip.clip_id, "The job queue was unavailable; try again.")
            return self.get(clip.clip_id, owner)
        return clip

    def recent(self, owner: UUID) -> list[SpeechClipRead]:
        """Return the owner's 20 most recent clips, as listed in the studio.

        Args:
            owner: The user asking.

        Returns:
            The clips, newest first.
        """
        return self._clips.recent(owner, RECENT)

    def get(self, clip_id: UUID, owner: UUID) -> SpeechClipRead:
        """Return one of the owner's clips.

        Args:
            clip_id: The clip.
            owner: The user asking.

        Returns:
            The clip and its status.

        Raises:
            NotFoundError: The owner has no such clip.
        """
        clip = self._clips.get(clip_id, owner)
        if clip is None:
            raise NotFoundError("speech clip", clip_id)
        return clip

    def audio(self, clip_id: UUID, owner: UUID) -> bytes:
        """Return a finished clip's audio.

        Args:
            clip_id: The clip.
            owner: The user asking.

        Returns:
            The clip as WAV bytes.

        Raises:
            NotFoundError: The owner has no such clip, or it has no audio yet.
        """
        key = self._clips.object_key(clip_id, owner)
        if key is None or not self._store.exists(key):
            raise NotFoundError("audio of speech clip", clip_id)
        return self._store.get(key)

    def delete(self, clip_id: UUID, owner: UUID) -> None:
        """Delete one of the owner's clips and its audio.

        Args:
            clip_id: The clip.
            owner: The user asking.

        Raises:
            NotFoundError: The owner has no such clip.
        """
        key = self._clips.object_key(clip_id, owner)
        if not self._clips.delete(clip_id, owner):
            raise NotFoundError("speech clip", clip_id)
        if key:
            self._store.delete(key)

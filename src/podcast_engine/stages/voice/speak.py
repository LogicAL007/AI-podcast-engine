from uuid import UUID

import numpy as np

from podcast_engine.common.audio import SR, read_wav_bytes, silence, wav_bytes
from podcast_engine.common.context import PipelineContext, get_context
from podcast_engine.common.llm import GeminiQuotaError
from podcast_engine.common.logging import get_logger
from podcast_engine.common.pronunciation import rules_for, spoken
from podcast_engine.common.repository import SpeechClipRecord
from podcast_engine.common.voice_fx import VoiceEffects, apply_effects
from podcast_engine.stages.assemble.service import tighten
from podcast_engine.stages.voice.backends import backend_unavailable
from podcast_engine.stages.voice.service import (
    _backend,
    prune_withdrawn_voices,
    registered_voices,
    segment_cache_key,
)
from podcast_engine.stages.voice.speech_text import pieces, speech_key

log = get_logger("voice.speak")

PAUSE_S = 0.25  # between the pieces of one clip
SPEAKER = "Alex"  # the host a recorded voice is lent to for the clip


class SpeakError(Exception):
    """A clip that cannot be made here, with a reason to show the person who asked."""


def _voiced(clip: SpeechClipRecord, ctx: PipelineContext) -> np.ndarray:
    """Voice a clip's text, from the cache where possible.

    A recorded voice is lent to the host Alex for the clip and needs the Chatterbox engine. The text
    goes through the pronunciation lexicon first. Gemini reads the whole text in one request (one of
    the day's few); Chatterbox does best a sentence or two at a time, so its text is split. Each
    piece's raw speech is cached like an episode's lines, and the pieces are joined with short
    pauses.

    Args:
        clip: The queued clip.
        ctx: Shared clients (settings, storage, budget, TTS).

    Returns:
        The raw speech, before effects.

    Raises:
        SpeakError: The voice backend cannot run here, a recorded voice was asked for on a server
            that cannot speak it, or the voice was deleted.
        GeminiQuotaError: Today's Gemini TTS budget cannot cover the clip.
    """
    settings = ctx.settings
    problem = backend_unavailable(settings)
    if problem:
        raise SpeakError(problem)
    voice = clip.voice
    if voice.get("kind") == "recorded":
        if settings.tts_backend != "chatterbox":
            raise SpeakError(
                f"This server voices with {settings.tts_backend}, which cannot speak recorded "
                "voices. Choose one of the engine's own voices, or run the Chatterbox voice "
                "worker (make voice-host on the Mac)."
            )
        prune_withdrawn_voices(ctx)
        host = SPEAKER
        overrides = registered_voices(ctx, {host: str(voice["voice_id"])}, [host])
        if host not in overrides:
            raise SpeakError("That voice was deleted.")
    else:
        host = str(voice.get("host", SPEAKER))
        overrides = {}
    backend = _backend(ctx, (host,), overrides)
    text = spoken(clip.text, rules_for(settings.config_dir))
    texts = [text] if settings.tts_backend == "gemini" else pieces(text)
    keys = [
        segment_cache_key(backend.provider, backend.voice_id(host), text, clip.delivery)
        for text in texts
    ]
    if ctx.budget is not None and settings.tts_backend == "gemini":
        missing = sum(not ctx.store.exists(key) for key in keys)
        ctx.budget.require({settings.tts_model: missing}, "this clip")
    parts: list[np.ndarray] = []
    for text, key in zip(texts, keys, strict=True):
        if ctx.store.exists(key):
            audio = read_wav_bytes(ctx.store.get(key), name=key)
        else:
            audio = backend.synthesise(host, text, clip.delivery)
            ctx.store.put(key, wav_bytes(audio), "audio/wav")
        if parts:
            parts.append(silence(PAUSE_S))
        parts.append(tighten(audio))
    return np.concatenate(parts) if parts else silence(0.1)


def speak_clip(clip_id: UUID, ctx: PipelineContext | None = None) -> str:
    """Voice a queued type-to-speech clip and store it.

    Voices one line typed in the voice studio, in a recorded voice or the voice engine's own, with
    the host effects applied. The API stores the request (``speech_clips``) and queues
    ``SPEAK_TASK`` on the voice queue; this runs in the voice worker, which has the voices
    (Chatterbox with the recordings, or Gemini). The raw speech is cached like an episode's lines,
    so trying other effects on the same words, or using them in an episode later, voices nothing
    again.

    A clip redelivered after it finished is left as it is. A refusal is recorded with its reason;
    any other failure with a general message.

    Args:
        clip_id: The clip to voice.
        ctx: Shared clients; built from settings when omitted.

    Returns:
        The clip's status afterwards: ``done``, ``failed``, or its earlier status if it had already
        finished.
    """
    ctx = ctx or get_context()
    clip = ctx.repo.get_speech_clip(clip_id)
    if clip is None:
        log.warning("speech_clip_gone", clip_id=str(clip_id))
        return "failed"
    if clip.status not in {"queued", "working"}:
        return clip.status
    ctx.repo.finish_speech_clip(clip_id, status="working")
    try:
        audio = apply_effects(_voiced(clip, ctx), VoiceEffects.model_validate(clip.effects))
        key = speech_key(clip.owner_id, clip.clip_id)
        ctx.store.put(key, wav_bytes(audio), "audio/wav")
    except (SpeakError, GeminiQuotaError) as error:
        ctx.repo.finish_speech_clip(clip_id, status="failed", error=str(error))
        log.info("speech_clip_refused", clip_id=str(clip_id), reason=str(error))
        return "failed"
    except Exception:
        log.exception("speech_clip_failed", clip_id=str(clip_id))
        ctx.repo.finish_speech_clip(
            clip_id, status="failed", error="The voice engine failed on this text; try again."
        )
        return "failed"
    seconds = round(len(audio) / SR, 2)
    ctx.repo.finish_speech_clip(clip_id, status="done", object_key=key, duration_s=seconds)
    log.info("speech_clip_done", clip_id=str(clip_id), seconds=seconds)
    return "done"

"""Voice: per-host text-to-speech with a segment cache."""

import hashlib
import time
from typing import Any
from uuid import UUID

from podcast_engine.common.audio import wav_bytes
from podcast_engine.common.context import PipelineContext, get_context
from podcast_engine.common.logging import get_logger
from podcast_engine.common.models import ScriptLine
from podcast_engine.common.queue import Stage
from podcast_engine.stages.publish.service import AI_DISCLOSURE
from podcast_engine.stages.voice.backends import TtsBackend, make_backend

log = get_logger("voice")


def segment_cache_key(provider: str, voice_id: str, text: str) -> str:
    """Key for a synthesised line. Unchanged lines hit the cache on regeneration.

    Includes the provider and voice, so switching either never serves stale audio.
    """
    digest = hashlib.sha256(f"{provider}\x00{voice_id}\x00{text}".encode()).hexdigest()
    return f"tts/{digest}.wav"


def episode_lines(
    topic: str, hosts: list[str], script: dict[int, list[ScriptLine]]
) -> list[dict[str, Any]]:
    """Everything spoken, in order: AI disclosure (FR13), opening, each segment, closing."""
    first, second = hosts[0], hosts[-1]

    def spoken(kind: str, position: int | None, speaker: str, text: str) -> dict[str, Any]:
        return {"kind": kind, "position": position, "speaker": speaker, "text": text}

    return [
        spoken("disclosure", None, first, AI_DISCLOSURE),
        spoken("opening", None, first, f"Welcome to the show. Today: {topic}."),
        spoken("opening", None, second, "Glad to be here. Let's get into it."),
        *(
            spoken("segment", pos, line.speaker, line.text)
            for pos in sorted(script)
            for line in script[pos]
        ),
        spoken("closing", None, second, "That's all for this episode."),
        spoken(
            "closing",
            None,
            first,
            "Thanks for listening. Every source is linked in the show notes.",
        ),
    ]


_BACKENDS: dict[tuple[str, tuple[str, ...], str], TtsBackend] = {}


def _backend(ctx: PipelineContext, hosts: tuple[str, ...]) -> TtsBackend:
    """One backend per worker process and configuration: loading Chatterbox takes a while."""
    key = (ctx.settings.tts_backend, hosts, str(ctx.voices_file))
    if key not in _BACKENDS:
        _BACKENDS[key] = make_backend(ctx.settings, list(hosts), ctx.voices_file)
    return _BACKENDS[key]


def synthesise_voices(episode_id: UUID, ctx: PipelineContext | None = None) -> Stage | None:
    """FR6: voice each line with its host's voice. Lines already voiced are reused from storage."""
    from podcast_engine.stages.script.service import script_lines

    ctx = ctx or get_context()
    episode = ctx.repo.get_episode(episode_id)
    show = ctx.repo.get_show(episode.show_id)
    hosts = ctx.hosts(show.host_count)
    backend = _backend(ctx, tuple(hosts))
    if len({backend.voice_id(h) for h in hosts}) != len(hosts):
        raise ValueError("Each host needs a distinct voice (FR6); check the voice configuration.")
    lines = episode_lines(show.topic, hosts, script_lines(episode.script))
    synthesised = reused = 0
    started = time.perf_counter()
    for line in lines:
        key = segment_cache_key(backend.provider, backend.voice_id(line["speaker"]), line["text"])
        if ctx.store.exists(key):
            reused += 1
        else:
            ctx.store.put(
                key, wav_bytes(backend.synthesise(line["speaker"], line["text"])), "audio/wav"
            )
            synthesised += 1
        line["key"] = key
    voices = {
        host: {
            "voice_id": backend.voice_id(host),
            "credit": backend.credit(host),
            **backend.consent_record(host),
        }
        for host in hosts
    }
    manifest = dict(episode.manifest or {})
    manifest.update({"tts_provider": backend.provider, "voices": voices})
    ctx.repo.update_episode(episode_id, voice_lines=lines, manifest=manifest)
    log.info(
        "lines_voiced",
        episode_id=str(episode_id),
        provider=backend.provider,
        synthesised=synthesised,
        reused=reused,
        seconds=round(time.perf_counter() - started, 1),
    )
    return Stage.ASSEMBLE

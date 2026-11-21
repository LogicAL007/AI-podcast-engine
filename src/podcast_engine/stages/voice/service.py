"""Voice: per-host text-to-speech with a segment cache."""

import hashlib
import time
from typing import Any
from uuid import UUID

from podcast_engine.common.audio import wav_bytes
from podcast_engine.common.context import PipelineContext, get_context
from podcast_engine.common.logging import get_logger
from podcast_engine.common.models import ScriptLine
from podcast_engine.common.pronunciation import rules_for, spoken
from podcast_engine.common.queue import Stage
from podcast_engine.stages.publish.service import AI_DISCLOSURE
from podcast_engine.stages.voice.backends import DialogueBackend, TtsBackend, make_backend
from podcast_engine.stages.voice.registry import ClonedVoice

log = get_logger("voice")


def segment_cache_key(provider: str, voice_id: str, text: str, delivery: str = "neutral") -> str:
    """Key for a synthesised line. Unchanged lines hit the cache on regeneration.

    Includes the provider, voice and delivery, so changing any of them never serves stale audio.
    (A neutral line keeps the key it had before lines carried a delivery.)
    """
    said = text if delivery == "neutral" else f"{delivery}\x00{text}"
    digest = hashlib.sha256(f"{provider}\x00{voice_id}\x00{said}".encode()).hexdigest()
    return f"tts/{digest}.wav"


def episode_lines(
    topic: str, hosts: list[str], script: dict[int, list[ScriptLine]]
) -> list[dict[str, Any]]:
    """Everything spoken, in order: AI disclosure (FR13), opening, each segment, closing.

    Each line keeps how it is said (``delivery``) and whether it states a fact (``claim``), which
    the assembly uses to pace the conversation.
    """
    first, second = hosts[0], hosts[-1]

    def spoken(
        kind: str,
        position: int | None,
        speaker: str,
        text: str,
        delivery: str = "neutral",
        claim: bool = False,
    ) -> dict[str, Any]:
        return {
            "kind": kind,
            "position": position,
            "speaker": speaker,
            "text": text,
            "delivery": delivery,
            "claim": claim,
        }

    return [
        spoken("disclosure", None, first, AI_DISCLOSURE),
        spoken("opening", None, first, f"Welcome to the show. Today: {topic}.", "warm"),
        *(  # a narrator does not greet themself
            [spoken("opening", None, second, "Glad to be here. Let's get into it.", "warm")]
            if second != first
            else []
        ),
        *(
            spoken("segment", pos, line.speaker, line.text, line.delivery.value, bool(line.claims))
            for pos in sorted(script)
            for line in script[pos]
        ),
        spoken("closing", None, second, "That's all for this episode.", "warm"),
        spoken(
            "closing",
            None,
            first,
            "Thanks for listening. Every source is linked in the show notes.",
            "warm",
        ),
    ]


def voice_groups(lines: list[dict[str, Any]], max_chars: int) -> list[list[int]]:
    """The lines voiced together in one request, as indexes into ``lines``.

    A group is consecutive lines of one part of the episode (the disclosure, the opening, one
    segment, the closing), so chapters and pauses between parts stay exact. A group holds at most
    two speakers and about ``max_chars`` of text; a longer part is split.
    """
    groups: list[list[int]] = []
    for index, line in enumerate(lines):
        if groups:
            group = [lines[i] for i in groups[-1]]
            same_part = (group[0]["kind"], group[0]["position"]) == (line["kind"], line["position"])
            speakers = {g["speaker"] for g in group} | {line["speaker"]}
            size = sum(len(g["text"]) for g in group) + len(line["text"])
            if same_part and len(speakers) <= 2 and size <= max_chars:
                groups[-1].append(index)
                continue
        groups.append([index])
    return groups


def dialogue_cache_key(backend: TtsBackend, lines: list[dict[str, Any]]) -> str:
    """Key for lines voiced together: the provider, each speaker's voice and every word."""
    voices = "|".join(
        f"{speaker}={backend.voice_id(speaker)}"
        for speaker in dict.fromkeys(line["speaker"] for line in lines)
    )
    words = "\n".join(
        f"{line['speaker']}"
        + ("" if line.get("delivery", "neutral") == "neutral" else f" ({line['delivery']})")
        + f": {line['text']}"
        for line in lines
    )
    return segment_cache_key(backend.provider, voices, words)


_BACKENDS: dict[tuple[str, tuple[str, ...], str, tuple[tuple[str, str], ...]], TtsBackend] = {}


def registered_voices(
    ctx: PipelineContext, host_voices: dict[str, str], hosts: list[str]
) -> dict[str, ClonedVoice]:
    """The voices a show's hosts were given in the web app, as cloneable registry entries.

    Each recording is copied once (by content hash) into the voice worker's cache, where
    Chatterbox reads it. A voice deleted since it was assigned is skipped: that host keeps the
    default voice. Only the Chatterbox backend clones; the others ignore these.
    """
    wanted = {host: voice for host, voice in host_voices.items() if host in hosts}
    if not wanted or ctx.settings.tts_backend != "chatterbox":
        return {}
    records = ctx.repo.get_voices(wanted.values())
    folder = ctx.settings.data_dir / "tts_cache" / "voices"
    folder.mkdir(parents=True, exist_ok=True)
    voices: dict[str, ClonedVoice] = {}
    for host, voice_id in wanted.items():
        record = records.get(voice_id)
        if record is None:
            log.warning("voice_missing", host=host, voice_id=voice_id)
            continue
        path = folder / f"{record.sha256}.wav"
        if not path.is_file():
            path.write_bytes(ctx.store.get(record.object_key))
        consent = record.consent
        voices[host] = ClonedVoice(
            reference_audio=str(path),  # absolute, so the registry's root does not apply
            speaker=record.speaker,
            consent=(
                f"signed in Oasis by {consent.get('signed_by', '?')} on "
                f"{consent.get('agreed_at', '?')} ({consent.get('relationship', '?')}, "
                f"form {consent.get('version', '?')})"
            ),
            license=record.license,
        )
    return voices


def prune_withdrawn_voices(ctx: PipelineContext) -> int:
    """Delete this worker's copies of recordings whose voice has been deleted (consent
    withdrawn). The consent form promises this happens the next time episodes are voiced."""
    folder = ctx.settings.data_dir / "tts_cache" / "voices"
    if not folder.is_dir():
        return 0
    kept = ctx.repo.voice_hashes()
    removed = 0
    for copy in folder.glob("*.wav"):
        if copy.stem not in kept:
            copy.unlink(missing_ok=True)
            removed += 1
    if removed:
        log.info("withdrawn_voices_deleted", copies=removed)
    return removed


def _backend(
    ctx: PipelineContext, hosts: tuple[str, ...], overrides: dict[str, ClonedVoice]
) -> TtsBackend:
    """One backend per worker process and configuration: loading Chatterbox takes a while."""
    chosen = tuple(sorted((host, str(voice.reference_audio)) for host, voice in overrides.items()))
    key = (ctx.settings.tts_backend, hosts, str(ctx.voices_file), chosen)
    if key not in _BACKENDS:
        _BACKENDS[key] = make_backend(
            ctx.settings, list(hosts), ctx.voices_file, overrides, budget=ctx.budget
        )
    return _BACKENDS[key]


def synthesise_voices(episode_id: UUID, ctx: PipelineContext | None = None) -> Stage | None:
    """FR6: voice each line with its host's voice. Lines already voiced are reused from storage."""
    from podcast_engine.stages.script.service import script_lines

    ctx = ctx or get_context()
    episode = ctx.repo.get_episode(episode_id)
    show = ctx.repo.get_show(episode.show_id)
    hosts = ctx.hosts(show.host_count)
    if ctx.settings.tts_backend == "chatterbox":
        prune_withdrawn_voices(ctx)
    overrides = registered_voices(ctx, show.host_voices, hosts)
    backend = _backend(ctx, tuple(hosts), overrides)
    if len({backend.voice_id(h) for h in hosts}) != len(hosts):
        raise ValueError("Each host needs a distinct voice (FR6); check the voice configuration.")
    lines = episode_lines(show.topic, hosts, script_lines(episode.script))
    # What each voice says: the line with the pronunciation lexicon applied. The line's own text
    # stays as written for transcripts; the cache key follows what is said.
    rules = rules_for(ctx.settings.config_dir)
    said = [spoken(line["text"], rules) for line in lines]
    dialogue = isinstance(backend, DialogueBackend)
    groups = (
        voice_groups(lines, backend.max_dialogue_chars)
        if isinstance(backend, DialogueBackend)
        else [[i] for i in range(len(lines))]
    )
    keys = [
        segment_cache_key(
            backend.provider,
            backend.voice_id(lines[group[0]]["speaker"]),
            said[group[0]],
            lines[group[0]]["delivery"],
        )
        if len(group) == 1
        else dialogue_cache_key(backend, [{**lines[i], "text": said[i]} for i in group])
        for group in groups
    ]
    cached = [ctx.store.exists(key) for key in keys]
    if ctx.budget is not None and ctx.settings.tts_backend == "gemini":
        # Check the whole step fits first, so a run never stops at today's cap half voiced.
        missing = cached.count(False)
        ctx.budget.require({ctx.settings.tts_model: missing}, f"voicing {missing} part(s)")
    synthesised = reused = 0
    started = time.perf_counter()
    for group, key, done in zip(groups, keys, cached, strict=True):
        members = [lines[i] for i in group]
        first = members[0]
        if done:
            reused += 1
        else:
            if len(members) == 1:
                audio = backend.synthesise(first["speaker"], said[group[0]], first["delivery"])
            else:
                assert isinstance(backend, DialogueBackend)  # noqa: S101 - groups imply dialogue
                audio = backend.synthesise_dialogue(
                    [(lines[i]["speaker"], said[i]) for i in group],
                    [line["delivery"] for line in members],
                )
            ctx.store.put(key, wav_bytes(audio), "audio/wav")
            synthesised += 1
        first["key"] = key
        for line in members[1:]:
            line["key"] = None  # spoken in the clip of the group's first line
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
        dialogue=dialogue,
        synthesised=synthesised,
        reused=reused,
        seconds=round(time.perf_counter() - started, 1),
    )
    return Stage.ASSEMBLE

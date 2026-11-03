"""Registry of voices the pipeline may clone, with the consent record each one needs.

The PRD forbids cloning a real person without permission. A cloned voice therefore cannot be used
unless the registry names the speaker, says where their consent is recorded and states the licence,
and the reference recording exists. A host with no reference audio uses the model's built-in default
voice, which clones nobody.
"""

import hashlib
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

_REQUIRED_FOR_CLONE = ("speaker", "consent", "license")


class VoiceRegistryError(ValueError):
    """The registry cannot be used as written; the message lists every problem."""


class ClonedVoice(BaseModel):
    model_config = ConfigDict(frozen=True)

    reference_audio: str | None = None  # path from the repo root; None = the model's default voice
    speaker: str = ""  # who is speaking in the reference recording
    consent: str = ""  # where their written permission is kept
    license: str = ""  # terms under which the recording may be used

    @property
    def is_clone(self) -> bool:
        return bool(self.reference_audio)


class VoiceRegistry(BaseModel):
    chatterbox: dict[str, ClonedVoice] = {}


def load_registry(path: Path) -> VoiceRegistry:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return VoiceRegistry.model_validate(raw)


def problems_with(registry: VoiceRegistry, hosts: list[str], root: Path) -> list[str]:
    """Everything wrong with the registry for these hosts, so one run reports it all."""
    problems: list[str] = []
    for host in hosts:
        entry = registry.chatterbox.get(host)
        if entry is None:
            problems.append(f"{host}: no entry under 'chatterbox'")
            continue
        if not entry.is_clone:
            continue
        missing = [name for name in _REQUIRED_FOR_CLONE if not getattr(entry, name).strip()]
        if missing:
            problems.append(
                f"{host}: a cloned voice needs a consent record; fill in {', '.join(missing)}"
            )
        if not (root / str(entry.reference_audio)).is_file():
            problems.append(f"{host}: reference recording {entry.reference_audio} not found")
    return problems


def with_overrides(registry: VoiceRegistry, overrides: dict[str, ClonedVoice]) -> VoiceRegistry:
    """The registry with some hosts' voices replaced (voices registered in the app, by host)."""
    return VoiceRegistry(chatterbox={**registry.chatterbox, **overrides})


def resolve_voices(registry: VoiceRegistry, hosts: list[str], root: Path) -> dict[str, ClonedVoice]:
    """The registry entries for these hosts, or VoiceRegistryError naming every problem."""
    problems = problems_with(registry, hosts, root)
    if problems:
        raise VoiceRegistryError("Voice registry problems:\n- " + "\n- ".join(problems))
    return {host: registry.chatterbox[host] for host in hosts}


def fingerprint(voice: ClonedVoice, root: Path) -> str:
    """Identifies the reference recording by content, so replacing it invalidates cached audio."""
    if not voice.is_clone:
        return "default"
    data = (root / str(voice.reference_audio)).read_bytes()
    return hashlib.sha256(data).hexdigest()[:12]


def clips_voiced_with(
    sha256: str, episodes: Iterable[tuple[list[dict[str, Any]] | None, dict[str, Any] | None]]
) -> list[str]:
    """Stored clips of lines spoken in the voice whose recording has this checksum, from each
    episode's (voice_lines, manifest). The manifest names each host's voice as
    ``chatterbox:<fingerprint>:...``, so a host is matched by the recording, not the voice's id."""
    prefix = f"chatterbox:{sha256[:12]}:"
    keys: list[str] = []
    for lines, manifest in episodes:
        voices = (manifest or {}).get("voices", {})
        hosts = {h for h, voice in voices.items() if str(voice.get("voice_id")).startswith(prefix)}
        keys += [ln["key"] for ln in lines or [] if ln.get("key") and ln["speaker"] in hosts]
    return list(dict.fromkeys(keys))

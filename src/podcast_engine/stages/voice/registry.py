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
    """One host's voice in the registry, with the consent record a clone needs.

    - ``reference_audio``: the recording to clone, as a path from the repository root; None uses the
      model's default voice.
    - ``speaker``: who is speaking in the recording.
    - ``consent``: where their written permission is kept.
    - ``license``: the terms under which the recording may be used.
    """

    model_config = ConfigDict(frozen=True)

    reference_audio: str | None = None
    speaker: str = ""
    consent: str = ""
    license: str = ""

    @property
    def is_clone(self) -> bool:
        """Whether this voice clones a recording rather than using the default."""
        return bool(self.reference_audio)


class VoiceRegistry(BaseModel):
    """The voices the pipeline may clone, by host name, from ``config/voices.yaml``."""

    chatterbox: dict[str, ClonedVoice] = {}


def load_registry(path: Path) -> VoiceRegistry:
    """Read the voice registry file.

    Args:
        path: The YAML file.

    Returns:
        The registry; empty when the file is empty.

    Raises:
        ValidationError: The file does not match the registry's shape.
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return VoiceRegistry.model_validate(raw)


def problems_with(registry: VoiceRegistry, hosts: list[str], root: Path) -> list[str]:
    """List everything wrong with the registry for some hosts, so one run reports it all.

    The PRD forbids cloning a real person without permission, so a cloned voice needs the speaker,
    where their consent is recorded and the licence, and its recording must exist. A host with no
    reference audio uses the model's built-in default voice, which clones nobody.

    Args:
        registry: The voice registry.
        hosts: The hosts that will speak.
        root: The repository root that recording paths start from.

    Returns:
        One message per problem; empty when the registry is usable.
    """
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
    """Return the registry with some hosts' voices replaced.

    Used for voices registered in the app, which take precedence over the config file.

    Args:
        registry: The voice registry.
        overrides: The replacement voices, by host.

    Returns:
        A new registry.
    """
    return VoiceRegistry(chatterbox={**registry.chatterbox, **overrides})


def resolve_voices(registry: VoiceRegistry, hosts: list[str], root: Path) -> dict[str, ClonedVoice]:
    """Return the registry entries for some hosts, refusing an unusable registry.

    Args:
        registry: The voice registry.
        hosts: The hosts that will speak.
        root: The repository root that recording paths start from.

    Returns:
        Each host's voice.

    Raises:
        VoiceRegistryError: Anything is wrong; the message names every problem.
    """
    problems = problems_with(registry, hosts, root)
    if problems:
        raise VoiceRegistryError("Voice registry problems:\n- " + "\n- ".join(problems))
    return {host: registry.chatterbox[host] for host in hosts}


def fingerprint(voice: ClonedVoice, root: Path) -> str:
    """Identify a voice's reference recording by its content.

    Replacing the recording changes the fingerprint, which invalidates cached audio.

    Args:
        voice: The voice.
        root: The repository root that recording paths start from.

    Returns:
        The first 12 hex digits of the recording's SHA-256, or ``default`` for the default voice.
    """
    if not voice.is_clone:
        return "default"
    data = (root / str(voice.reference_audio)).read_bytes()
    return hashlib.sha256(data).hexdigest()[:12]


def clips_voiced_with(
    sha256: str, episodes: Iterable[tuple[list[dict[str, Any]] | None, dict[str, Any] | None]]
) -> list[str]:
    """Find the stored clips of lines spoken in one recorded voice.

    The manifest names each host's voice as ``chatterbox:<fingerprint>:...``, so a host is matched
    by the recording, not the voice's id.

    Args:
        sha256: The checksum of the voice's recording.
        episodes: Each episode's (voice_lines, manifest).

    Returns:
        The clips' object keys, without duplicates, in the order found.
    """
    prefix = f"chatterbox:{sha256[:12]}:"
    keys: list[str] = []
    for lines, manifest in episodes:
        voices = (manifest or {}).get("voices", {})
        hosts = {h for h, voice in voices.items() if str(voice.get("voice_id")).startswith(prefix)}
        keys += [ln["key"] for ln in lines or [] if ln.get("key") and ln["speaker"] in hosts]
    return list(dict.fromkeys(keys))

"""Text-to-speech backends. Each turns one line into 24 kHz mono samples for one host.

* ``placeholder``: tones with the rhythm of speech. Instant and dependency-free; for tests and CI.
* ``say``: macOS system voices. Host only (a container has no ``say``).
* ``chatterbox``: open model that can clone a voice, with consent records from voices.yaml. Heavy
  (torch); run the voice worker on a host with the ``cloning`` extra.
* ``gemini``: hosted Gemini TTS with prebuilt voices. Needs a key (the tts_api_key secret).
"""

import os
import subprocess
import tempfile
import warnings
from pathlib import Path
from typing import Protocol

import numpy as np

from podcast_engine.common.audio import SR, read_wav_bytes
from podcast_engine.common.config import Settings
from podcast_engine.stages.voice.registry import (
    ClonedVoice,
    fingerprint,
    load_registry,
    resolve_voices,
)

SAY_VOICES = {"Alex": "Samantha", "Sam": "Daniel", "Jordan": "Karen", "Riley": "Moira"}
GEMINI_VOICES = {"Alex": "Kore", "Sam": "Puck", "Jordan": "Charon", "Riley": "Aoede"}
PLACEHOLDER_PITCH_HZ = {"Alex": 200.0, "Sam": 120.0, "Jordan": 160.0, "Riley": 240.0}


class TtsBackend(Protocol):
    provider: str

    def voice_id(self, speaker: str) -> str:
        """Identifies the voice exactly, so changing it never serves stale cached audio."""
        ...

    def credit(self, speaker: str) -> str:
        """Public wording for the show notes."""
        ...

    def consent_record(self, speaker: str) -> dict[str, str]: ...

    def synthesise(self, speaker: str, text: str) -> np.ndarray: ...


class _NoConsentNeeded:
    def consent_record(self, speaker: str) -> dict[str, str]:  # noqa: ARG002
        return {}


class PlaceholderBackend(_NoConsentNeeded):
    """One voiced burst per word, longer for longer words. Rhythm only: this is not speech."""

    provider = "placeholder-tones"

    def voice_id(self, speaker: str) -> str:
        return f"placeholder-{speaker}"

    def credit(self, speaker: str) -> str:  # noqa: ARG002
        return "placeholder tone (not speech)"

    def synthesise(self, speaker: str, text: str) -> np.ndarray:
        pitch = PLACEHOLDER_PITCH_HZ.get(speaker, 150.0)
        pieces = []
        for word in text.split():
            seconds = 0.08 + 0.035 * len(word)
            t = np.arange(int(SR * seconds)) / SR
            envelope = np.sin(np.pi * t / seconds) ** 2
            wobble = 1 + 0.06 * (len(word) % 5)
            pieces.append(
                (0.3 * envelope * np.sin(2 * np.pi * pitch * wobble * t)).astype(np.float32)
            )
            pieces.append(np.zeros(int(SR * 0.04), dtype=np.float32))
        return np.concatenate(pieces) if pieces else np.zeros(1, dtype=np.float32)


class SayBackend(_NoConsentNeeded):
    provider = "macos-say"

    def voice_id(self, speaker: str) -> str:
        return SAY_VOICES[speaker]

    def credit(self, speaker: str) -> str:
        return f"macOS system voice {SAY_VOICES[speaker]}"

    def synthesise(self, speaker: str, text: str) -> np.ndarray:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "line.wav"
            subprocess.run(  # noqa: S603 - fixed argv; the text goes in on stdin
                [  # noqa: S607 - `say` is the macOS system command
                    "say",
                    "-v",
                    SAY_VOICES[speaker],
                    "-o",
                    str(path),
                    f"--data-format=LEI16@{SR}",
                    "-f",
                    "-",
                ],
                input=text.encode("utf-8"),
                check=True,
            )
            return read_wav_bytes(path.read_bytes(), name=path.name)


class ChatterboxBackend:
    """Open TTS model (MIT) that can imitate a voice from a short recording.

    A cloned voice is refused unless its consent record is complete and the recording exists, so
    this constructor fails before any audio is made. Chatterbox watermarks its audio, inaudibly.
    """

    provider = "chatterbox"
    EXAGGERATION = 0.5
    CFG_WEIGHT = 0.5

    def __init__(self, hosts: list[str], voices_file: Path, root: Path, seed: int) -> None:
        self.root = root
        self.voices: dict[str, ClonedVoice] = resolve_voices(
            load_registry(voices_file), hosts, root
        )
        os.environ["TQDM_DISABLE"] = "1"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            import torch
            from chatterbox.tts import ChatterboxTTS

            device = (
                "mps"
                if torch.backends.mps.is_available()
                else "cuda"
                if torch.cuda.is_available()
                else "cpu"
            )
            self.model = ChatterboxTTS.from_pretrained(device=device)
        torch.manual_seed(seed)

    def voice_id(self, speaker: str) -> str:
        recording = fingerprint(self.voices[speaker], self.root)
        return f"chatterbox:{recording}:e{self.EXAGGERATION}:c{self.CFG_WEIGHT}"

    def credit(self, speaker: str) -> str:
        voice = self.voices[speaker]
        if not voice.is_clone:
            return "Chatterbox default voice (no real person cloned)"
        return f"voice cloned from a recording by {voice.speaker}, with their permission"

    def consent_record(self, speaker: str) -> dict[str, str]:
        voice = self.voices[speaker]
        if not voice.is_clone:
            return {}
        return {"speaker": voice.speaker, "consent": voice.consent, "license": voice.license}

    def synthesise(self, speaker: str, text: str) -> np.ndarray:
        import torchaudio

        voice = self.voices[speaker]
        reference = str(self.root / str(voice.reference_audio)) if voice.is_clone else None
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            wav = self.model.generate(
                text,
                audio_prompt_path=reference,
                exaggeration=self.EXAGGERATION,
                cfg_weight=self.CFG_WEIGHT,
            )
        if self.model.sr != SR:
            wav = torchaudio.functional.resample(wav, self.model.sr, SR)
        samples: np.ndarray = wav.squeeze().cpu().numpy().astype(np.float32)
        return samples


class GeminiTtsBackend(_NoConsentNeeded):
    """Gemini's prebuilt voices (no cloning). Returns 24 kHz 16-bit PCM, the pipeline's format."""

    provider = "gemini-tts"

    def __init__(self, api_key: str, model: str) -> None:
        from google import genai

        self.model = model
        self.client = genai.Client(api_key=api_key) if api_key else genai.Client()

    def voice_id(self, speaker: str) -> str:
        return f"{self.model}:{GEMINI_VOICES[speaker]}"

    def credit(self, speaker: str) -> str:
        return f"Gemini TTS prebuilt voice {GEMINI_VOICES[speaker]} (no real person cloned)"

    def synthesise(self, speaker: str, text: str) -> np.ndarray:
        from google.genai import types

        response = self.client.models.generate_content(
            model=self.model,
            contents=text,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=GEMINI_VOICES[speaker]
                        )
                    )
                ),
            ),
        )
        candidate = response.candidates[0] if response.candidates else None
        part = (
            candidate.content.parts[0]
            if candidate and candidate.content and candidate.content.parts
            else None
        )
        data = part.inline_data.data if part and part.inline_data else None
        if not data:
            raise RuntimeError(f"Gemini TTS returned no audio for {speaker} ({self.model}).")
        return np.frombuffer(data, dtype="<i2").astype(np.float32) / 32768.0


def make_backend(settings: Settings, hosts: list[str], voices_file: Path) -> TtsBackend:
    choice = settings.tts_backend
    if choice == "placeholder":
        return PlaceholderBackend()
    if choice == "say":
        return SayBackend()
    if choice == "chatterbox":
        # Reference recordings are named from the repository root (assets/voices/...).
        return ChatterboxBackend(hosts, voices_file, settings.assets_dir.parent, settings.seed)
    if choice == "gemini":
        key = settings.tts_api_key.get_secret_value() or settings.llm_api_key.get_secret_value()
        return GeminiTtsBackend(key, settings.tts_model)
    raise ValueError(f"TTS_BACKEND must be placeholder, say, chatterbox or gemini, not {choice!r}")

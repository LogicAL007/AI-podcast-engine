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
import time
import warnings
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar, Protocol, runtime_checkable

import numpy as np

from podcast_engine.common.audio import SR, read_wav_bytes
from podcast_engine.common.config import Settings
from podcast_engine.common.llm import GeminiQuotaError, is_daily_quota, retry_after_seconds
from podcast_engine.common.logging import get_logger
from podcast_engine.common.quota import DailyBudget
from podcast_engine.stages.voice.registry import (
    ClonedVoice,
    fingerprint,
    load_registry,
    resolve_voices,
    with_overrides,
)

log = get_logger("voice")

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

    def synthesise(self, speaker: str, text: str, delivery: str = "neutral") -> np.ndarray:
        """One line in ``speaker``'s voice, said the way ``delivery`` names (see Delivery);
        a backend that cannot vary its delivery reads every line the same way."""
        ...


@runtime_checkable
class DialogueBackend(TtsBackend, Protocol):
    """A backend that voices several lines, by at most two speakers, in one request."""

    max_dialogue_chars: int

    def synthesise_dialogue(
        self, lines: list[tuple[str, str]], deliveries: list[str] | None = None
    ) -> np.ndarray: ...


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

    def synthesise(self, speaker: str, text: str, delivery: str = "neutral") -> np.ndarray:  # noqa: ARG002
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

    def synthesise(self, speaker: str, text: str, delivery: str = "neutral") -> np.ndarray:  # noqa: ARG002
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
    # Per delivery: (exaggeration, cfg_weight). More exaggeration is more expressive and a little
    # faster; a lower cfg_weight slows the pace, which keeps expressive lines from rushing.
    # Changing a value changes STYLES_VERSION, so no line is served from the old cache.
    STYLES: ClassVar[dict[str, tuple[float, float]]] = {
        "neutral": (0.5, 0.5),
        "warm": (0.55, 0.45),
        "curious": (0.6, 0.45),
        "excited": (0.7, 0.35),
        "thoughtful": (0.4, 0.4),
        "amused": (0.65, 0.4),
        "serious": (0.35, 0.5),
    }
    STYLES_VERSION = 1

    def __init__(
        self,
        hosts: list[str],
        voices_file: Path,
        root: Path,
        seed: int,
        overrides: dict[str, ClonedVoice] | None = None,
    ) -> None:
        self.root = root
        # Voices registered in the web app (with their signed consent) replace the file's entry
        # for their host; both go through the same consent check.
        registry = with_overrides(load_registry(voices_file), overrides or {})
        self.voices: dict[str, ClonedVoice] = resolve_voices(registry, hosts, root)
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
        return f"chatterbox:{recording}:styles{self.STYLES_VERSION}"

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

    def synthesise(self, speaker: str, text: str, delivery: str = "neutral") -> np.ndarray:
        import torchaudio

        voice = self.voices[speaker]
        reference = str(self.root / str(voice.reference_audio)) if voice.is_clone else None
        exaggeration, cfg_weight = self.STYLES.get(delivery, self.STYLES["neutral"])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            wav = self.model.generate(
                text,
                audio_prompt_path=reference,
                exaggeration=exaggeration,
                cfg_weight=cfg_weight,
            )
        if self.model.sr != SR:
            wav = torchaudio.functional.resample(wav, self.model.sr, SR)
        samples: np.ndarray = wav.squeeze().cpu().numpy().astype(np.float32)
        return samples


class GeminiTtsBackend(_NoConsentNeeded):
    """Gemini's prebuilt voices (no cloning). Returns 24 kHz 16-bit PCM, the pipeline's format.

    The voice stage sends a whole part of the episode (the opening, a segment, the closing) as one
    two-speaker request, so an episode costs a handful of requests and fits the free tier's daily
    cap. On a rate limit it waits as long as Gemini asks and tries again, and
    with ``requests_per_minute`` set it spaces requests out so the limit is not hit at all (the
    free tier allows 3 a minute). A used-up daily quota fails at once with a plain message, and
    with a daily ``budget`` a request that would pass it is never sent.
    """

    provider = "gemini-tts"
    ATTEMPTS = 8  # per request, across rate limits and brief server errors
    max_dialogue_chars = 3000  # about three minutes of speech per request

    def __init__(
        self,
        api_key: str,
        model: str,
        requests_per_minute: int = 0,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        budget: DailyBudget | None = None,
    ) -> None:
        from google import genai

        self.model = model
        self.budget = budget
        self.client = genai.Client(api_key=api_key) if api_key else genai.Client()
        self.interval = 60.0 / requests_per_minute if requests_per_minute > 0 else 0.0
        self.sleep = sleep
        self.clock = clock
        self.last_request: float | None = None

    def _pace(self) -> None:
        if self.interval and self.last_request is not None:
            wait = self.last_request + self.interval - self.clock()
            if wait > 0:
                self.sleep(wait)
        self.last_request = self.clock()

    def _generate(self, config: Any, contents: Any) -> Any:
        from google.genai import errors

        for attempt in range(self.ATTEMPTS):
            if self.budget is not None:
                self.budget.require({self.model: 1}, f"another {self.model} request")
            self._pace()
            try:
                response = self.client.models.generate_content(
                    model=self.model, contents=contents, config=config
                )
            except (errors.ServerError, errors.ClientError) as error:
                limited = isinstance(error, errors.ClientError) and error.code == 429
                if self.budget is not None and not limited:
                    self.budget.spend(self.model)
                if limited and is_daily_quota(error):
                    raise GeminiQuotaError(
                        f"Gemini's daily quota for {self.model} is used up. Try again tomorrow, "
                        "enable billing on the key, or set TTS_BACKEND to another voice."
                    ) from error
                if not (limited or isinstance(error, errors.ServerError)):
                    raise
                if attempt == self.ATTEMPTS - 1:
                    raise
                asked = retry_after_seconds(error) if limited else None
                wait = (asked or min(2 ** (attempt + 1), 30)) + 1
                log.warning("tts_busy", model=self.model, code=error.code, retry_in_s=round(wait))
                self.sleep(wait)
            else:
                if self.budget is not None:
                    self.budget.spend(self.model)
                return response
        raise AssertionError("unreachable")

    def voice_id(self, speaker: str) -> str:
        return f"{self.model}:{GEMINI_VOICES[speaker]}"

    def credit(self, speaker: str) -> str:
        return f"Gemini TTS prebuilt voice {GEMINI_VOICES[speaker]} (no real person cloned)"

    def _voice(self, speaker: str) -> Any:
        from google.genai import types

        return types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=GEMINI_VOICES[speaker])
        )

    def _audio(self, response: Any, who: str) -> np.ndarray:
        candidate = response.candidates[0] if response.candidates else None
        part = (
            candidate.content.parts[0]
            if candidate and candidate.content and candidate.content.parts
            else None
        )
        data = part.inline_data.data if part and part.inline_data else None
        if not data:
            raise RuntimeError(f"Gemini TTS returned no audio for {who} ({self.model}).")
        return np.frombuffer(data, dtype="<i2").astype(np.float32) / 32768.0

    def synthesise(self, speaker: str, text: str, delivery: str = "neutral") -> np.ndarray:  # noqa: ARG002 - one voice reads plain text
        from google.genai import types

        config = types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(voice_config=self._voice(speaker)),
        )
        return self._audio(self._generate(config, text), speaker)

    def synthesise_dialogue(
        self, lines: list[tuple[str, str]], deliveries: list[str] | None = None
    ) -> np.ndarray:
        """Several lines in one request, so a whole segment costs one request, not one a line.

        Two speakers use Gemini's multi-speaker mode, each with their own prebuilt voice. Each
        line is its own part, labelled with its speaker and (from ``deliveries``) the style to say
        it in; the text is read as a verbatim transcript, so it carries nothing but the words.
        """
        from google.genai import types

        speakers = list(dict.fromkeys(speaker for speaker, _ in lines))
        if len(speakers) == 1:
            return self.synthesise(speakers[0], "\n".join(text for _, text in lines))
        if len(speakers) > 2:
            raise ValueError(f"Gemini voices at most two speakers per request, not {speakers}.")
        config = types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                multi_speaker_voice_config=types.MultiSpeakerVoiceConfig(
                    speaker_voice_configs=[
                        types.SpeakerVoiceConfig(speaker=speaker, voice_config=self._voice(speaker))
                        for speaker in speakers
                    ]
                )
            ),
        )
        turns = types.Content(
            role="user",
            parts=[
                types.Part(
                    text=text,
                    speech_metadata=types.SpeechMetadata(
                        speaker=speaker, style=None if delivery == "neutral" else delivery
                    ),
                )
                for (speaker, text), delivery in zip(
                    lines, deliveries or ["neutral"] * len(lines), strict=True
                )
            ],
        )
        return self._audio(self._generate(config, turns), " and ".join(speakers))


# What each backend needs installed in this process, and where to run it instead.
NEEDS: dict[str, tuple[tuple[str, ...], str]] = {
    "chatterbox": (
        ("torch", "chatterbox"),
        "Chatterbox is not installed here. Docker on macOS cannot use the Mac's GPU, so run the "
        "voice worker on the Mac with `make voice-host` (or build this image with "
        "VOICE_EXTRAS=voice,llm,cloning for slow CPU-only voicing).",
    ),
    "gemini": (("google.genai",), "google-genai is not installed here: add the llm extra."),
}


def backend_unavailable(settings: Settings) -> str | None:
    """Why this process cannot run the configured voice backend, or None if it can.

    Checked before a voice worker takes any job, so a worker without the backend (the Docker
    voice image without Chatterbox, for example) never takes a job it would fail.
    """
    from importlib.util import find_spec
    from shutil import which

    choice = settings.tts_backend
    if choice == "say" and which("say") is None:
        return "The say backend needs macOS's say command, which this machine does not have."
    needed, advice = NEEDS.get(choice, ((), ""))
    missing = [module for module in needed if find_spec(module.split(".")[0]) is None]
    return f"{advice} Missing: {', '.join(missing)}." if missing else None


def make_backend(
    settings: Settings,
    hosts: list[str],
    voices_file: Path,
    overrides: dict[str, ClonedVoice] | None = None,
    budget: DailyBudget | None = None,
) -> TtsBackend:
    choice = settings.tts_backend
    if choice == "placeholder":
        return PlaceholderBackend()
    if choice == "say":
        return SayBackend()
    if choice == "chatterbox":
        # Reference recordings are named from the repository root (assets/voices/...).
        return ChatterboxBackend(
            hosts, voices_file, settings.assets_dir.parent, settings.seed, overrides
        )
    if choice == "gemini":
        key = settings.tts_api_key.get_secret_value() or settings.llm_api_key.get_secret_value()
        return GeminiTtsBackend(
            key, settings.tts_model, settings.tts_requests_per_minute, budget=budget
        )
    raise ValueError(f"TTS_BACKEND must be placeholder, say, chatterbox or gemini, not {choice!r}")

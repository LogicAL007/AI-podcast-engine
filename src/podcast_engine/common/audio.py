"""Audio helpers shared by the voice and assemble stages: 24 kHz mono 16-bit WAV, as bytes.

Clips travel between workers through object storage, so everything reads and writes ``bytes``.
"""

import io
import wave
from typing import Any

import numpy as np

SR = 24_000  # PRD: 24 kHz or higher
CLIP_CEILING = 0.97
SILENCE_LIMIT_S = 2.0


def wav_bytes(samples: np.ndarray, rate: int = SR) -> bytes:
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(pcm.tobytes())
    return buffer.getvalue()


def read_wav_bytes(data: bytes, *, name: str = "clip") -> np.ndarray:
    with wave.open(io.BytesIO(data), "rb") as handle:
        if handle.getframerate() != SR or handle.getnchannels() != 1 or handle.getsampwidth() != 2:
            raise ValueError(f"{name}: need {SR} Hz mono 16-bit, got {handle.getframerate()} Hz")
        frames = handle.readframes(handle.getnframes())
    return np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0


def silence(seconds: float) -> np.ndarray:
    return np.zeros(int(SR * seconds), dtype=np.float32)


def chime(freqs: tuple[float, ...], seconds: float) -> np.ndarray:
    """A short bell-like sting: the default intro, outro and transition when there is no asset."""
    t = np.arange(int(SR * seconds)) / SR
    mix = np.zeros_like(t)
    for n, freq in enumerate(freqs):
        onset = 0.16 * n
        envelope = np.where(t >= onset, np.exp(-(t - onset) * 2.4), 0.0)
        mix += np.sin(2 * np.pi * freq * t) * envelope
    return (0.28 * mix / len(freqs)).astype(np.float32)


def soft_limit(samples: np.ndarray, knee: float = 0.8) -> np.ndarray:
    """Smoothly squash peaks above ``knee`` toward CLIP_CEILING instead of hard clipping."""
    magnitude = np.abs(samples)
    room = CLIP_CEILING - knee
    squashed = knee + room * np.tanh((magnitude - knee) / room)
    return np.where(magnitude > knee, np.sign(samples) * squashed, samples).astype(np.float32)


def loudness(samples: np.ndarray) -> float:
    import pyloudnorm as pyln

    return float(pyln.Meter(SR).integrated_loudness(samples))


def normalise(samples: np.ndarray, target_lufs: float) -> np.ndarray:
    """Bring loudness to the target with a soft limiter.

    The gain is nudged until the limiter's own effect on loudness is absorbed.
    """
    out = samples
    gain_db = target_lufs - loudness(samples)
    for _ in range(4):
        out = soft_limit(samples * 10 ** (gain_db / 20))
        error = target_lufs - loudness(out)
        if abs(error) < 0.2:
            break
        gain_db += error
    return out


def longest_silence(
    samples: np.ndarray, *, threshold: float = 0.003, frame_s: float = 0.02
) -> float:
    n = int(SR * frame_s)
    frames = samples[: len(samples) // n * n].reshape(-1, n)
    quiet = np.sqrt((frames**2).mean(axis=1)) < threshold
    run = best = 0
    for is_quiet in quiet:
        run = run + 1 if is_quiet else 0
        best = max(best, run)
    return best * frame_s


def audio_report(samples: np.ndarray) -> dict[str, Any]:
    return {
        "sample_rate_hz": SR,
        "duration_s": len(samples) / SR,
        "lufs": loudness(samples),
        "peak": float(np.max(np.abs(samples))),
        "clipped_samples": int(np.sum(np.abs(samples) >= 0.999)),
        "longest_silence_s": longest_silence(samples),
    }

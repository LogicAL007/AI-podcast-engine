import io
import wave
from typing import Any

import numpy as np

SR = 24_000  # PRD: 24 kHz or higher
CLIP_CEILING = 0.97
SILENCE_LIMIT_S = 2.0


def wav_bytes(samples: np.ndarray, rate: int = SR) -> bytes:
    """Encode samples as a mono 16-bit WAV file.

    The voice and assemble stages share 24 kHz mono 16-bit WAV. Clips travel between workers through
    object storage, so everything reads and writes ``bytes``. Samples outside [-1, 1] are clipped.

    Args:
        samples: Float samples in [-1, 1].
        rate: The sample rate in Hz.

    Returns:
        The WAV file's bytes.
    """
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(pcm.tobytes())
    return buffer.getvalue()


def read_wav_bytes(data: bytes, *, name: str = "clip") -> np.ndarray:
    """Decode a 24 kHz mono 16-bit WAV file.

    Args:
        data: The WAV file's bytes.
        name: What to call the file in an error.

    Returns:
        The samples as float32 in [-1, 1).

    Raises:
        ValueError: The file is not 24 kHz mono 16-bit.
    """
    with wave.open(io.BytesIO(data), "rb") as handle:
        if handle.getframerate() != SR or handle.getnchannels() != 1 or handle.getsampwidth() != 2:
            raise ValueError(f"{name}: need {SR} Hz mono 16-bit, got {handle.getframerate()} Hz")
        frames = handle.readframes(handle.getnframes())
    return np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0


def silence(seconds: float) -> np.ndarray:
    """Return a stretch of silence.

    Args:
        seconds: Its length.

    Returns:
        Zero samples at the engine's sample rate.
    """
    return np.zeros(int(SR * seconds), dtype=np.float32)


def chime(freqs: tuple[float, ...], seconds: float) -> np.ndarray:
    """Make a short bell-like sting.

    The default intro, outro and transition when a show has no music for that slot. Each note starts
    0.16 s after the one before and decays exponentially.

    Args:
        freqs: The notes' frequencies in Hz, in the order they sound.
        seconds: The sting's length.

    Returns:
        The sting's samples.
    """
    t = np.arange(int(SR * seconds)) / SR
    mix = np.zeros_like(t)
    for n, freq in enumerate(freqs):
        onset = 0.16 * n
        envelope = np.where(t >= onset, np.exp(-(t - onset) * 2.4), 0.0)
        mix += np.sin(2 * np.pi * freq * t) * envelope
    return (0.28 * mix / len(freqs)).astype(np.float32)


def soft_limit(samples: np.ndarray, knee: float = 0.8) -> np.ndarray:
    """Smoothly squash peaks above a knee toward the clip ceiling instead of hard clipping.

    Args:
        samples: The samples to limit.
        knee: The level above which peaks are squashed.

    Returns:
        The limited samples, never above 0.97 in magnitude.
    """
    magnitude = np.abs(samples)
    room = CLIP_CEILING - knee
    squashed = knee + room * np.tanh((magnitude - knee) / room)
    return np.where(magnitude > knee, np.sign(samples) * squashed, samples).astype(np.float32)


def loudness(samples: np.ndarray) -> float:
    """Measure integrated loudness (ITU-R BS.1770).

    Args:
        samples: Samples at the engine's sample rate.

    Returns:
        The loudness in LUFS.
    """
    import pyloudnorm as pyln

    return float(pyln.Meter(SR).integrated_loudness(samples))


def normalise(samples: np.ndarray, target_lufs: float) -> np.ndarray:
    """Bring audio to a target loudness, with a soft limiter.

    The gain is nudged, up to four times, until the limiter's own effect on loudness is absorbed and
    the result is within 0.2 LU of the target.

    Args:
        samples: The audio.
        target_lufs: The loudness to reach, such as -16.

    Returns:
        The normalised audio.
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
    """Measure the longest quiet stretch in audio.

    Args:
        samples: The audio.
        threshold: The RMS level below which a frame counts as quiet.
        frame_s: The frame length in seconds.

    Returns:
        The longest run of quiet frames, in seconds.
    """
    n = int(SR * frame_s)
    frames = samples[: len(samples) // n * n].reshape(-1, n)
    quiet = np.sqrt((frames**2).mean(axis=1)) < threshold
    run = best = 0
    for is_quiet in quiet:
        run = run + 1 if is_quiet else 0
        best = max(best, run)
    return best * frame_s


def audio_report(samples: np.ndarray) -> dict[str, Any]:
    """Summarise audio for the assembly report and its checks.

    Args:
        samples: The audio.

    Returns:
        Sample rate, duration, loudness, peak, clipped samples and longest silence.
    """
    return {
        "sample_rate_hz": SR,
        "duration_s": len(samples) / SR,
        "lufs": loudness(samples),
        "peak": float(np.max(np.abs(samples))),
        "clipped_samples": int(np.sum(np.abs(samples) >= 0.999)),
        "longest_silence_s": longest_silence(samples),
    }

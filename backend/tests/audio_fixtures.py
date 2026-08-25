"""Synthesised recordings for testing the engine.

Amplitude-modulated tones, not speech — but the engine at Tier 0 measures an
energy envelope, and these produce a real one with a controllable syllable
rate, onset and pause structure. That makes the tests deterministic and lets
them assert on direction ("hesitant scores below fluent") rather than on a
magic number that would break the first time a threshold is tuned.
"""
from __future__ import annotations

import io
import wave

import numpy as np

SAMPLE_RATE = 16000


def to_wav(samples: np.ndarray, sample_rate: int = SAMPLE_RATE) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes((np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes())
    return buf.getvalue()


def speech_like(seconds: float = 6.0, syllables_per_sec: float = 4.2,
                start_silence: float = 0.4, gaps: tuple[tuple[float, float], ...] = (),
                noise: float = 0.001, level: float = 0.5,
                sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """A voiced-sounding envelope with a known syllable rate."""
    n = int(seconds * sample_rate)
    t = np.arange(n) / sample_rate
    carrier = 0.5 * np.sin(2 * np.pi * 140 * t) + 0.25 * np.sin(2 * np.pi * 280 * t)
    envelope = (0.5 * (1 + np.sin(2 * np.pi * syllables_per_sec * t - np.pi / 2))) ** 1.5
    signal = carrier * envelope * level

    signal[: int(start_silence * sample_rate)] = 0.0
    for start, end in gaps:
        signal[int(start * sample_rate):int(end * sample_rate)] = 0.0

    rng = np.random.default_rng(7)
    return signal + rng.normal(0, noise, n)


def silence(seconds: float = 5.0, noise: float = 0.0005,
            sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    rng = np.random.default_rng(1)
    return rng.normal(0, noise, int(seconds * sample_rate))


def clipped(seconds: float = 5.0, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    return np.clip(speech_like(seconds, level=3.0, sample_rate=sample_rate), -1.0, 1.0)


def noisy(seconds: float = 6.0, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    rng = np.random.default_rng(3)
    return (speech_like(seconds, level=0.12, sample_rate=sample_rate)
            + rng.normal(0, 0.06, int(seconds * sample_rate)))


# Named cases the tests read like sentences.
FLUENT = lambda: speech_like(6.0, 4.3, start_silence=0.35)                      # noqa: E731
HESITANT = lambda: speech_like(8.0, 2.1, start_silence=2.6, gaps=((4.0, 6.2),))  # noqa: E731
RUSHED = lambda: speech_like(6.0, 7.2, start_silence=0.3)                        # noqa: E731

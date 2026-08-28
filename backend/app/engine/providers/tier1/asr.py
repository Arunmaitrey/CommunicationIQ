"""Tier 1 — Automatic Speech Recognition using faster-whisper.

Provides word-level transcription with timestamps for the scoring pipeline.
Uses the small.en model for a good balance of speed and accuracy on CPU.
"""
from __future__ import annotations

import io
import logging
import struct
from pathlib import Path

import numpy as np

from app.engine.contracts.types import ProviderMeta, TranscriptResult, WordTiming

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000

# Lazy-loaded model singleton — loaded on first use, reused across requests.
_model = None
_model_name = "small.en"


def _get_model():
    """Load the faster-whisper model on first call."""
    global _model
    if _model is not None:
        return _model

    try:
        from faster_whisper import WhisperModel
        log.info("Loading Whisper model: %s", _model_name)
        _model = WhisperModel(_model_name, device="cpu", compute_type="int8")
        log.info("Whisper model loaded successfully")
    except Exception:
        log.exception("Failed to load Whisper model")
        raise

    return _model


def load_samples(audio_bytes: bytes) -> np.ndarray:
    """Load audio bytes and return float32 samples at 16kHz mono.

    Accepts WAV (PCM s16le) format. Returns a numpy array of float32
    samples normalised to [-1, 1].
    """
    # Try WAV parsing first
    if audio_bytes[:4] == b"RIFF":
        return _parse_wav(audio_bytes)

    # Fallback: assume raw PCM s16le
    samples = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    return samples


def _parse_wav(data: bytes) -> np.ndarray:
    """Parse a WAV file and return mono float32 samples."""
    import wave

    try:
        with wave.open(io.BytesIO(data), "rb") as wf:
            frames = wf.readframes(wf.getnframes())
            samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0

            # Convert stereo to mono if needed
            if wf.getnchannels() == 2:
                samples = (samples[0::2] + samples[1::2]) / 2.0

            # Resample to 16kHz if needed
            if wf.getframerate() != SAMPLE_RATE:
                ratio = SAMPLE_RATE / wf.getframerate()
                indices = np.arange(0, len(samples), ratio).astype(int)
                samples = samples[np.clip(indices, 0, len(samples) - 1)]

            return samples
    except Exception:
        log.warning("Failed to parse WAV, treating as raw PCM")
        samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
        return samples


async def transcribe(audio_bytes: bytes, *, language: str = "en",
                     hint_text: str = "") -> TranscriptResult:
    """Transcribe audio using faster-whisper with word-level timestamps.

    Returns a TranscriptResult with the full text, per-word timings,
    and overall confidence.
    """
    try:
        model = _get_model()
        samples = load_samples(audio_bytes)

        if len(samples) < SAMPLE_RATE * 0.5:
            # Less than 0.5 seconds — too short to transcribe meaningfully
            return TranscriptResult(text="", confidence=0.0)

        # faster-whisper expects float32 numpy array
        segments, info = model.transcribe(
            samples,
            language=language,
            beam_size=3,
            word_timestamps=True,
            vad_filter=True,
        )

        words: list[WordTiming] = []
        full_text_parts: list[str] = []
        confidences: list[float] = []

        for segment in segments:
            full_text_parts.append(segment.text.strip())
            avg_prob = getattr(segment, "avg_logprob", -1.0)
            # Convert log-prob to approximate confidence [0, 1]
            seg_conf = min(1.0, max(0.0, (avg_prob + 5.0) / 5.0))
            confidences.append(seg_conf)

            if hasattr(segment, "words") and segment.words:
                for w in segment.words:
                    words.append(WordTiming(
                        word=w.word,
                        start_ms=int(w.start * 1000),
                        end_ms=int(w.end * 1000),
                        confidence=round(w.probability, 3) if hasattr(w, "probability") else seg_conf,
                    ))

        full_text = " ".join(full_text_parts)
        overall_confidence = round(sum(confidences) / len(confidences), 3) if confidences else 0.0

        return TranscriptResult(
            text=full_text,
            words=words,
            confidence=overall_confidence,
        )

    except Exception:
        log.exception("Transcription failed")
        return TranscriptResult(text="", confidence=0.0)

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

from app.engine.audio import decode_wav, resample_to
from app.engine.contracts.types import (AudioRef, ProviderMeta,
                                        TranscriptResult, WordTiming)
from app.storage import get_storage

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


def load_samples(storage_key: str) -> np.ndarray:
    """Read a stored recording as 16 kHz mono float32 samples.

    Goes through the Storage contract rather than the filesystem, so the
    same provider works unchanged once recordings live in object storage.
    ``provider_registry`` names this module ``FasterWhisperASR``, a class
    that never existed here -- every ASR call failed to load, and every
    dimension downstream of a transcript (accuracy, disfluency, grammar,
    content) was unscored on every attempt as a result.
    """
    wave = decode_wav(get_storage().get(storage_key))
    return resample_to(wave, SAMPLE_RATE).samples.astype(np.float32)


def _decode_bytes(audio_bytes: bytes) -> np.ndarray:
    """Load raw audio bytes directly (WAV or PCM s16le), not via storage."""
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


class FasterWhisperASR:
    """Capability: ``asr``."""

    contract_version = "1.0"
    provider_key = "faster_whisper"
    version = "0.1.0"

    async def transcribe(self, audio: AudioRef, *, language: str = "en",
                         hint_text: str = "") -> TranscriptResult:
        # hint_text is deliberately ignored: priming the model with the
        # reference for a scripted task would make every score a
        # measurement of our own prompt rather than of the candidate.
        samples = load_samples(audio.storage_key)
        return _transcribe_samples(samples, language=language)


def _transcribe_samples(samples: np.ndarray, *, language: str = "en") -> TranscriptResult:
    """Run the model over already-decoded samples and shape the result."""
    try:
        model = _get_model()

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

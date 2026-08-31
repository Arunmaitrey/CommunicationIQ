"""Faster Whisper transcription with word timestamps and confidence."""
from __future__ import annotations

import numpy as np

from app.engine.audio import decode_wav, resample_to
from app.engine.contracts.types import (AudioRef, ProviderMeta,
                                        TranscriptResult, WordTiming)
from app.engine.providers.tier1.model import get_model
from app.storage import get_storage

SAMPLE_RATE = 16000


class FasterWhisperASR:
    contract_version = "1.0"
    provider_key = "faster_whisper"
    version = "whisper_v1"

    async def transcribe(self, audio: AudioRef, *, language: str = "en",
                         hint_text: str = "") -> TranscriptResult:
        # The hint contains the answer on scripted tasks. Never bias Whisper
        # with it when the transcript itself will be scored.
        return self.analyse(load_samples(audio.storage_key), language=language)

    def analyse(self, samples: np.ndarray, *, language: str = "en") -> TranscriptResult:
        meta = ProviderMeta(provider_id="", provider_key=self.provider_key,
                            version=self.version, tier=1)
        if samples.size < SAMPLE_RATE // 10:
            return TranscriptResult(text="", confidence=0.0, meta=meta)

        segments, _info = get_model().transcribe(
            samples, language=language or "en", word_timestamps=True,
            beam_size=1, condition_on_previous_text=False, vad_filter=False)
        words: list[WordTiming] = []
        parts: list[str] = []
        for segment in segments:
            parts.append(segment.text.strip())
            for word in segment.words or []:
                value = word.word.strip()
                if value:
                    words.append(WordTiming(
                        word=value, start_ms=int(word.start * 1000),
                        end_ms=int(word.end * 1000),
                        confidence=round(float(word.probability), 3)))
        text = " ".join(part for part in parts if part).strip()
        confidence = (round(sum(w.confidence for w in words) / len(words), 3)
                      if words else 0.0)
        return TranscriptResult(text=text, words=words, language=language,
                                confidence=confidence, meta=meta)


def load_samples(storage_key: str) -> np.ndarray:
    wave = decode_wav(get_storage().get(storage_key))
    return resample_to(wave, SAMPLE_RATE).samples.astype(np.float32)

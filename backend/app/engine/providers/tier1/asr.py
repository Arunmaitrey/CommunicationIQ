"""Tier 1 — transcription with word-level timestamps (ENG-01).

faster-whisper, running locally. The word timings it returns are what make
every downstream feature possible: which words were understood, where the
fillers fell, and where in the recording to jump to when a student taps a word
in their own transcript.

**The reference text is never given to the model.** ``hint_text`` exists on the
contract because some providers accept a biasing prompt, and for a *scripted*
task that would be the single most damaging thing we could do: whisper would
happily emit the sentence it was primed with and every Read Aloud score would
be a measurement of our own prompt. Ignored here, deliberately and loudly.
"""
from __future__ import annotations

import numpy as np

from app.engine.audio import decode_wav, resample_to
from app.engine.contracts.types import (AudioRef, ProviderMeta,
                                        TranscriptResult, WordTiming)
from app.engine.providers.tier1.model import get_model
from app.storage import get_storage

SAMPLE_RATE = 16000


class FasterWhisperASR:
    """Capability: ``asr``."""

    contract_version = "1.0"
    provider_key = "faster_whisper"
    version = "0.1.0"

    async def transcribe(self, audio: AudioRef, *, language: str = "en",
                         hint_text: str = "") -> TranscriptResult:
        samples = load_samples(audio.storage_key)
        return self.analyse(samples, language=language)

    def analyse(self, samples: np.ndarray, *, language: str = "en") -> TranscriptResult:
        meta = ProviderMeta(provider_id="", provider_key=self.provider_key,
                            version=self.version, tier=1)

        if samples.size < SAMPLE_RATE // 10:
            return TranscriptResult(text="", confidence=0.0, meta=meta)

        segments, _info = get_model().transcribe(
            samples,
            language=language or "en",
            word_timestamps=True,
            # Greedy. Beam search buys little on short scripted utterances and
            # costs the latency budget several times over.
            beam_size=1,
            # Whisper invents text in silence; this is the standard guard.
            condition_on_previous_text=False,
            vad_filter=False,   # VAD is its own capability, resolved separately
        )

        words: list[WordTiming] = []
        parts: list[str] = []
        for segment in segments:
            parts.append(segment.text.strip())
            for word in segment.words or []:
                text = word.word.strip()
                if not text:
                    continue
                words.append(WordTiming(
                    word=text,
                    start_ms=int(word.start * 1000),
                    end_ms=int(word.end * 1000),
                    confidence=round(float(word.probability), 3),
                ))

        text = " ".join(p for p in parts if p).strip()
        confidence = (round(sum(w.confidence for w in words) / len(words), 3)
                      if words else 0.0)

        return TranscriptResult(text=text, words=words, language=language,
                                confidence=confidence, meta=meta)


def load_samples(storage_key: str) -> np.ndarray:
    """Read a stored recording as 16 kHz mono float samples.

    Goes through the Storage contract rather than the filesystem, so the same
    provider works unchanged once recordings live in object storage.
    """
    wave = decode_wav(get_storage().get(storage_key))
    return resample_to(wave, SAMPLE_RATE).samples.astype(np.float32)

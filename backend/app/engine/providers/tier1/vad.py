"""Tier 1 — Silero voice activity detection (ENG-02).

The ONNX Silero model that ships with faster-whisper. It replaces the Tier-0
energy threshold, and the difference shows up exactly where it matters: a
hostel corridor, a ceiling fan, a room with three other students in it. An
energy gate calls that speech; Silero does not.

Tier 0 stays registered as the fallback. If the model cannot load, latency and
pause structure are still measured — less well, but measured.
"""
from __future__ import annotations

import numpy as np

from app.engine.contracts.types import (AudioRef, ProviderMeta, SpeechSegment,
                                        VADResult)
from app.engine.providers.tier1.asr import SAMPLE_RATE, load_samples


class SileroVAD:
    """Capability: ``vad``."""

    contract_version = "1.0"
    provider_key = "silero_vad"
    version = "0.1.0"

    async def detect(self, audio: AudioRef, *, prompt_end_ms: int = 0) -> VADResult:
        samples = load_samples(audio.storage_key)
        return self.analyse(samples, prompt_end_ms=prompt_end_ms)

    def analyse(self, samples: np.ndarray, *, prompt_end_ms: int = 0) -> VADResult:
        from faster_whisper.vad import VadOptions, get_speech_timestamps

        meta = ProviderMeta(provider_id="", provider_key=self.provider_key,
                            version=self.version, tier=1)
        duration_ms = int(1000 * samples.size / SAMPLE_RATE)

        options = VadOptions(
            threshold=0.5,
            # Matched to the Tier-0 provider so the two are comparable in
            # shadow mode — a fallback that measures a different thing is not
            # a fallback, it is a second opinion nobody asked for.
            min_speech_duration_ms=120,
            min_silence_duration_ms=180,
            # No padding: it would shift the response-onset measurement, which
            # is the one number this feeds that must not drift.
            speech_pad_ms=0,
        )
        raw = get_speech_timestamps(samples, options, sampling_rate=SAMPLE_RATE)

        segments = [
            SpeechSegment(start_ms=int(1000 * s["start"] / SAMPLE_RATE),
                          end_ms=int(1000 * s["end"] / SAMPLE_RATE))
            for s in raw
        ]
        speech_ms = sum(s.end_ms - s.start_ms for s in segments)
        onset = max(0, segments[0].start_ms - prompt_end_ms) if segments else None

        return VADResult(
            segments=segments,
            speech_ms=speech_ms,
            silence_ms=max(0, duration_ms - speech_ms),
            onset_ms=onset,
            meta=meta,
        )

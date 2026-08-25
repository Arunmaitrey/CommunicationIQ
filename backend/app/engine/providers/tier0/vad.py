"""Tier 0 — energy-threshold voice activity detection (ENG-02).

Boring, and load-bearing. Response latency, pause structure and speech rate
all come out of this one measurement, and those are the features that
actually fail students in a timed spoken test — long before pronunciation
does.

Silero (Tier 1) will replace it and be better in noise. What this provides
today is real: the segments are computed from the samples, not assumed.
"""
from __future__ import annotations

import numpy as np

from app.engine.audio import HOP_MS, Waveform, frame_rms_dbfs, signal_quality
from app.engine.contracts.types import (AudioRef, ProviderMeta, SpeechSegment,
                                        VADResult)
from app.storage import get_storage
from app.engine.audio import decode_wav

# A burst shorter than this is a click, a chair, a breath — not speech.
MIN_SPEECH_MS = 120
# A gap shorter than this is the closure of a stop consonant, not a pause.
MIN_SILENCE_MS = 180
# How far above the room a frame must be to count as speech. Low enough for a
# quiet speaker on a budget handset, high enough to reject fan noise.
MARGIN_DB = 8.0


class EnergyVAD:
    """Capability: ``vad``."""

    contract_version = "1.0"
    provider_key = "energy_vad"
    version = "0.1.0"

    async def detect(self, audio: AudioRef, *, prompt_end_ms: int = 0) -> VADResult:
        wave = decode_wav(get_storage().get(audio.storage_key))
        return self.analyse(wave, prompt_end_ms=prompt_end_ms)

    # Kept sync and separate so the pipeline can reuse one decode across
    # providers instead of reading the same file three times.
    def analyse(self, wave: Waveform, *, prompt_end_ms: int = 0) -> VADResult:
        quality = signal_quality(wave)
        meta = ProviderMeta(provider_id="", provider_key=self.provider_key,
                            version=self.version, tier=0)

        if quality.silent:
            return VADResult(segments=[], speech_ms=0,
                             silence_ms=wave.duration_ms, onset_ms=None, meta=meta)

        times, db = frame_rms_dbfs(wave)
        threshold = quality.noise_floor_dbfs + MARGIN_DB
        # Never let the threshold sit above the speech itself: in a very quiet
        # recording the noise floor and the voice are close together, and a
        # fixed margin would declare the whole thing silence.
        threshold = min(threshold, quality.speech_dbfs - 3.0)

        voiced = db >= threshold
        segments = _runs_to_segments(voiced, times, wave.duration_ms)
        segments = _merge_close(segments, MIN_SILENCE_MS)
        segments = [s for s in segments if s.end_ms - s.start_ms >= MIN_SPEECH_MS]

        speech_ms = sum(s.end_ms - s.start_ms for s in segments)
        onset = None
        if segments:
            # Latency is measured from when the prompt stopped, not from the
            # top of the file — the student cannot answer before then.
            onset = max(0, segments[0].start_ms - prompt_end_ms)

        return VADResult(
            segments=segments,
            speech_ms=speech_ms,
            silence_ms=max(0, wave.duration_ms - speech_ms),
            onset_ms=onset,
            meta=meta,
        )


def _runs_to_segments(voiced: np.ndarray, times: np.ndarray,
                      duration_ms: int) -> list[SpeechSegment]:
    if voiced.size == 0:
        return []
    # Edge-detect on the boolean mask: +1 where speech starts, -1 where it ends.
    padded = np.concatenate(([False], voiced, [False]))
    edges = np.diff(padded.astype(np.int8))
    starts = np.flatnonzero(edges == 1)
    ends = np.flatnonzero(edges == -1)

    out: list[SpeechSegment] = []
    for s, e in zip(starts, ends):
        start_ms = int(times[min(s, len(times) - 1)])
        end_ms = int(times[min(e, len(times) - 1)] + HOP_MS) if e < len(times) else duration_ms
        out.append(SpeechSegment(start_ms=start_ms, end_ms=min(end_ms, duration_ms)))
    return out


def _merge_close(segments: list[SpeechSegment], gap_ms: int) -> list[SpeechSegment]:
    if not segments:
        return []
    merged = [segments[0]]
    for seg in segments[1:]:
        last = merged[-1]
        if seg.start_ms - last.end_ms < gap_ms:
            merged[-1] = SpeechSegment(start_ms=last.start_ms, end_ms=seg.end_ms)
        else:
            merged.append(seg)
    return merged

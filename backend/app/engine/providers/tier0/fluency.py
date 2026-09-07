"""Tier 0 — feature-based fluency and prosody (ENG-05).

Interpretable by construction: the score is a weighted sum of four features a
student can be shown directly. There is no model here to be opaque about, and
when Tier 1 replaces the feature extraction the explanation stays the same
shape.

What it does not do is guess. Without a transcript there is no word count, so
"words per minute" is derived from syllable nuclei and reported as the
estimate it is.
"""
from __future__ import annotations

from app.engine.audio import Waveform, signal_quality, syllable_nuclei
from app.engine.contracts.types import (AudioRef, FluencyResult, ProviderMeta,
                                        TranscriptResult, VADResult)
from app.engine.audio import decode_wav
from app.storage import get_storage

# English averages close to 1.4 syllables per word. Used only to present a
# familiar unit; every judgement below is made on the syllable rate itself.
SYLLABLES_PER_WORD = 1.4

# Comfortable articulation for spoken English, in syllables per second of
# actual speech. Below the floor reads as halting; above the ceiling reads as
# rushed, which costs a listener comprehension just as much.
RATE_FLOOR = 2.6
RATE_IDEAL_LOW = 3.6
RATE_IDEAL_HIGH = 5.2
RATE_CEILING = 6.8

# Share of the response window actually spent speaking.
PHONATION_IDEAL_LOW = 0.55
PHONATION_IDEAL_HIGH = 0.90

# A pause this long inside an answer is heard as a stall, not as phrasing.
LONG_PAUSE_MS = 1200

SCALE_MIN = 0.0
SCALE_MAX = 100.0


class FeatureFluency:
    """Capability: ``fluency``."""

    contract_version = "1.0"
    provider_key = "feature_fluency"
    version = "0.1.0"

    async def score(self, audio: AudioRef, *, transcript: TranscriptResult,
                    vad: VADResult, task_type: str = "") -> FluencyResult:
        wave = decode_wav(get_storage().get(audio.storage_key))
        return self.analyse(wave, vad=vad, task_type=task_type)

    def analyse(self, wave: Waveform, *, vad: VADResult,
                task_type: str = "") -> FluencyResult:
        meta = ProviderMeta(provider_id="", provider_key=self.provider_key,
                            version=self.version, tier=0)

        quality = signal_quality(wave)
        speech_s = vad.speech_ms / 1000.0

        if not vad.segments or speech_s < 0.3:
            # Nothing was said. A floor score with zero confidence, not a guess.
            return FluencyResult(score=SCALE_MIN, confidence=0.0, meta=meta)

        nuclei = syllable_nuclei(wave, speech_floor_dbfs=quality.noise_floor_dbfs + 8.0)
        # Only count nuclei that fall inside detected speech, or a noisy gap
        # inflates the rate.
        inside = [n for n in nuclei
                  if any(s.start_ms <= n <= s.end_ms for s in vad.segments)]
        syllables = max(len(inside), 1)

        articulation_rate = syllables / speech_s
        words_per_minute = (syllables / SYLLABLES_PER_WORD) / max(speech_s / 60.0, 1e-6)

        pauses = _internal_pauses(vad)
        pause_count = len(pauses)
        mean_pause = sum(pauses) / pause_count if pause_count else 0.0
        longest_pause = max(pauses) if pauses else 0

        span_ms = vad.segments[-1].end_ms - vad.segments[0].start_ms
        phonation = vad.speech_ms / span_ms if span_ms > 0 else 0.0

        rate_score = _band(articulation_rate, RATE_FLOOR, RATE_IDEAL_LOW,
                           RATE_IDEAL_HIGH, RATE_CEILING)
        phonation_score = _band(phonation, 0.30, PHONATION_IDEAL_LOW,
                                PHONATION_IDEAL_HIGH, 1.01)
        # Long pauses are counted per ten seconds of answer, so a 40-second
        # open response is not punished for having more of them than a
        # 15-second one.
        per_10s = len([p for p in pauses if p >= LONG_PAUSE_MS]) / max(span_ms / 10000.0, 0.1)
        stall_score = max(0.0, 1.0 - per_10s / 3.0)
        longest_score = max(0.0, 1.0 - max(0, longest_pause - LONG_PAUSE_MS) / 3000.0)

        composite = (0.40 * rate_score + 0.25 * phonation_score
                     + 0.20 * stall_score + 0.15 * longest_score)
        score = SCALE_MIN + composite * (SCALE_MAX - SCALE_MIN)

        # Confidence, honestly derived: a short answer or a noisy room means we
        # measured less, and the number says so rather than hiding it.
        confidence = 0.55
        if speech_s < 2.0:
            confidence *= 0.6
        if not quality.usable:
            confidence *= 0.6

        return FluencyResult(
            score=round(score, 1),
            words_per_minute=round(words_per_minute, 1),
            articulation_rate=round(articulation_rate, 2),
            pause_count=pause_count,
            mean_pause_ms=round(mean_pause, 1),
            longest_pause_ms=longest_pause,
            # Pitch needs an F0 tracker, which is Tier 1 work. Reported as
            # zero rather than invented.
            pitch_range_semitones=0.0,
            confidence=round(confidence, 2),
            meta=meta,
        )


def _internal_pauses(vad: VADResult) -> list[int]:
    """Gaps between speech runs. Leading and trailing silence are not pauses."""
    return [vad.segments[i + 1].start_ms - vad.segments[i].end_ms
            for i in range(len(vad.segments) - 1)]


def _band(value: float, floor: float, ideal_low: float,
          ideal_high: float, ceiling: float) -> float:
    """1.0 inside the ideal band, sloping linearly to 0 at floor and ceiling.

    A plateau rather than a peak, because there is no single correct speaking
    rate — there is a range that a listener follows comfortably.
    """
    if ideal_low <= value <= ideal_high:
        return 1.0
    if value < ideal_low:
        if value <= floor:
            return 0.0
        return (value - floor) / (ideal_low - floor)
    if value >= ceiling:
        return 0.0
    return (ceiling - value) / (ceiling - ideal_high)

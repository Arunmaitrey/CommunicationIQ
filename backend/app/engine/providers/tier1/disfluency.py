"""Tier 1 — fillers, repetitions and false starts (ENG-06).

Reads the transcript and the pause structure together, because the two say
different things: "um" is a filler wherever it appears, but a repeated word is
only a stumble if it was not deliberate, and a long silence before a restart is
what separates a false start from a normal phrase boundary.

Scored per hundred words, not as a raw count — a forty-second open response
should not be marked down for having more of everything than a six-word repeat.
"""
from __future__ import annotations

import re

from app.engine.contracts.types import (DisfluencyResult, ProviderMeta,
                                        TranscriptResult, VADResult)

SCALE_MIN = 20.0
SCALE_MAX = 80.0

# Whisper transcribes hesitation reasonably consistently in English.
FILLERS = {"um", "uh", "erm", "er", "ah", "hmm", "mm", "mhm", "uhh", "umm"}

# Phrases that function as hesitation when they are not carrying meaning. Kept
# short on purpose: "like" and "you know" are ordinary words most of the time,
# and flagging normal speech as a defect is how a diagnostic loses trust.
FILLER_PHRASES = [("you", "know"), ("i", "mean"), ("sort", "of"), ("kind", "of")]

# A repeat after a real gap is a restart, not a stutter.
RESTART_GAP_MS = 400

# Below this there is not enough speech for hesitation to mean anything.
MIN_WORDS_TO_JUDGE = 8

_PUNCT = re.compile(r"[^\w']+")


class TranscriptDisfluency:
    """Capability: ``disfluency``."""

    contract_version = "1.0"
    provider_key = "transcript_disfluency"
    version = "0.1.0"

    async def detect(self, *, transcript: TranscriptResult,
                     vad: VADResult) -> DisfluencyResult:
        return self.analyse(transcript, vad)

    def analyse(self, transcript: TranscriptResult,
                vad: VADResult) -> DisfluencyResult:
        meta = ProviderMeta(provider_id="", provider_key=self.provider_key,
                            version=self.version, tier=1)

        words = [w for w in transcript.words if _clean(w.word)]
        if len(words) < MIN_WORDS_TO_JUDGE:
            # A two-word answer has nowhere to hesitate. No opinion, rather
            # than a floor score that would punish a correct short answer.
            return DisfluencyResult(score=SCALE_MIN, confidence=0.0, meta=meta)

        events: list[dict] = []
        fillers = 0
        repetitions = 0

        cleaned = [_clean(w.word) for w in words]

        for i, (word, timing) in enumerate(zip(cleaned, words)):
            if word in FILLERS:
                fillers += 1
                events.append({"type": "filler", "text": timing.word.strip(),
                               "start_ms": timing.start_ms, "end_ms": timing.end_ms})
                continue

            if i > 0 and word == cleaned[i - 1] and len(word) > 1:
                gap = timing.start_ms - words[i - 1].end_ms
                kind = "false_start" if gap >= RESTART_GAP_MS else "repetition"
                repetitions += 1
                events.append({"type": kind, "text": timing.word.strip(),
                               "start_ms": timing.start_ms, "end_ms": timing.end_ms})

        for i in range(len(cleaned) - 1):
            if (cleaned[i], cleaned[i + 1]) in FILLER_PHRASES:
                fillers += 1
                events.append({"type": "filler",
                               "text": f"{cleaned[i]} {cleaned[i + 1]}",
                               "start_ms": words[i].start_ms,
                               "end_ms": words[i + 1].end_ms})

        per_hundred = 100.0 * (fillers + repetitions) / len(words)
        # Clean speech has a couple per hundred words; above about ten it is
        # the first thing a listener notices.
        penalty = min(1.0, max(0.0, (per_hundred - 2.0) / 10.0))
        score = SCALE_MAX - penalty * (SCALE_MAX - SCALE_MIN)

        return DisfluencyResult(
            score=round(score, 1),
            events=sorted(events, key=lambda e: e["start_ms"])[:40],
            filler_count=fillers,
            repetition_count=repetitions,
            confidence=0.6,
            meta=meta,
        )


def _clean(word: str) -> str:
    return _PUNCT.sub("", word.lower().strip())

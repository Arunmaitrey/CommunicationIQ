"""Speech capability contracts — Layers 1 and 2 of the engine.

Each Protocol is versioned by the ``contract_version`` class attribute. A
provider declaring a contract version we no longer serve is refused at
registration rather than failing mysteriously mid-attempt.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.engine.contracts.types import (AccuracyResult, AlignmentResult,
                                        AudioRef, DisfluencyResult,
                                        FluencyResult, IntelligibilityResult,
                                        L1Result, PronunciationResult,
                                        TranscriptResult, VADResult)


@runtime_checkable
class ASRProvider(Protocol):
    """ENG-01 — transcription with word-level timestamps."""

    contract_version = "1.0"
    provider_key: str
    version: str

    async def transcribe(self, audio: AudioRef, *, language: str = "en",
                         hint_text: str = "") -> TranscriptResult:
        """``hint_text`` is the reference for scripted tasks; ignore it for free speech."""
        ...


@runtime_checkable
class VADProvider(Protocol):
    """ENG-02 — speech/silence structure, the source of pause and latency features."""

    contract_version = "1.0"
    provider_key: str
    version: str

    async def detect(self, audio: AudioRef, *, prompt_end_ms: int = 0) -> VADResult:
        ...


@runtime_checkable
class AlignmentProvider(Protocol):
    """ENG-03 — forced alignment to word and phoneme timestamps."""

    contract_version = "1.0"
    provider_key: str
    version: str

    async def align(self, audio: AudioRef, transcript: str) -> AlignmentResult:
        ...


@runtime_checkable
class PronunciationProvider(Protocol):
    """ENG-04 — phoneme-level accuracy.

    Scores intelligibility-relevant accuracy, not nativeness. A provider that
    penalises an Indian English accent as such does not satisfy this contract.
    """

    contract_version = "1.0"
    provider_key: str
    version: str

    async def score(self, audio: AudioRef, *, reference_text: str,
                    alignment: AlignmentResult | None = None,
                    l1_language: str = "") -> PronunciationResult:
        ...


@runtime_checkable
class FluencyProvider(Protocol):
    """ENG-05 — fluency and prosody from interpretable features."""

    contract_version = "1.0"
    provider_key: str
    version: str

    async def score(self, audio: AudioRef, *, transcript: TranscriptResult,
                    vad: VADResult, task_type: str = "") -> FluencyResult:
        ...


@runtime_checkable
class DisfluencyProvider(Protocol):
    """ENG-06 — fillers, repetitions, self-corrections."""

    contract_version = "1.0"
    provider_key: str
    version: str

    async def detect(self, *, transcript: TranscriptResult,
                     vad: VADResult) -> DisfluencyResult:
        ...


@runtime_checkable
class IntelligibilityProvider(Protocol):
    """ENG-07 — would a hiring panel understand this?

    The differentiating model, and the last one built: it is trained on human
    intelligibility ratings from Indian raters, so the contract exists long
    before any implementation can. Scores comprehensibility, never nativeness.
    """

    contract_version = "1.0"
    provider_key: str
    version: str

    async def score(self, audio: AudioRef, *, transcript: TranscriptResult,
                    l1_language: str = "") -> IntelligibilityResult:
        ...


@runtime_checkable
class L1Provider(Protocol):
    """ENG-08 — first-language identification, for routing feedback.

    Used to pick which phoneme confusions to drill, never to label a student
    publicly and never as an input to their score.
    """

    contract_version = "1.0"
    provider_key: str
    version: str

    async def identify(self, audio: AudioRef) -> L1Result:
        ...


@runtime_checkable
class AccuracyProvider(Protocol):
    """Word accuracy against an item's reference text.

    Scripted tasks only — Read Aloud and Repeat Sentence have a right answer.
    Needs no audio: the transcript and the reference are the whole input,
    which is why this is a separate capability rather than a pronunciation
    provider wearing the wrong name.
    """

    contract_version = "1.0"
    provider_key: str
    version: str

    async def score(self, *, transcript: TranscriptResult, reference_text: str,
                    task_type: str = "",
                    alternatives: tuple[str, ...] = ()) -> AccuracyResult:
        ...

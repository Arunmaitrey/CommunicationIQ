"""Value types exchanged across provider contracts.

Deliberately plain: no provider's SDK objects cross a contract boundary, so a
consumer cannot accidentally depend on one implementation's shape. Every
result carries the provider identity that produced it, because ENG-21 requires
a score to be traceable to an exact implementation and version.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Capability(str, Enum):
    """Everything that is pluggable. One contract per member, no exceptions."""

    ASR = "asr"
    VAD = "vad"
    ALIGNMENT = "alignment"
    PRONUNCIATION = "pronunciation"
    ACCURACY = "accuracy"
    FLUENCY = "fluency"
    DISFLUENCY = "disfluency"
    INTELLIGIBILITY = "intelligibility"
    L1_ID = "l1_id"
    GRAMMAR = "grammar"
    CONTENT_RELEVANCE = "content_relevance"
    TTS = "tts"
    STORAGE = "storage"
    NOTIFICATION = "notification"
    PAYMENT = "payment"


@dataclass(frozen=True)
class ProviderMeta:
    """Identity stamped onto everything a provider returns."""

    provider_id: str
    provider_key: str
    version: str
    tier: int = 0


@dataclass(frozen=True)
class AudioRef:
    """A recording, addressed by storage key rather than path."""

    storage_key: str
    mime_type: str = "audio/webm"
    sample_rate: int = 48000
    duration_ms: int = 0


@dataclass(frozen=True)
class WordTiming:
    word: str
    start_ms: int
    end_ms: int
    confidence: float = 1.0


@dataclass(frozen=True)
class SpeechSegment:
    start_ms: int
    end_ms: int


@dataclass
class TranscriptResult:
    text: str
    words: list[WordTiming] = field(default_factory=list)
    language: str = "en"
    confidence: float = 0.0
    meta: ProviderMeta | None = None


@dataclass
class VADResult:
    segments: list[SpeechSegment] = field(default_factory=list)
    speech_ms: int = 0
    silence_ms: int = 0
    # Time from the prompt ending to the first speech frame — the raw number
    # behind "slow to start" (DIAG-04).
    onset_ms: int | None = None
    meta: ProviderMeta | None = None


@dataclass
class AlignmentResult:
    words: list[WordTiming] = field(default_factory=list)
    # [{phoneme, start_ms, end_ms}]
    phonemes: list[dict] = field(default_factory=list)
    meta: ProviderMeta | None = None


@dataclass
class PronunciationResult:
    """Phoneme-level accuracy (ENG-04).

    ``score`` is on the profile's presentation scale; ``phonemes`` is what
    makes it explainable, and what the L1 heatmap (DIAG-03) is built from.
    """

    score: float
    phonemes: list[dict] = field(default_factory=list)
    mispronounced_words: list[dict] = field(default_factory=list)
    confidence: float = 0.0
    meta: ProviderMeta | None = None


@dataclass
class FluencyResult:
    """Interpretable by construction (ENG-05) — the features are the explanation."""

    score: float
    words_per_minute: float = 0.0
    articulation_rate: float = 0.0
    pause_count: int = 0
    mean_pause_ms: float = 0.0
    longest_pause_ms: int = 0
    pitch_range_semitones: float = 0.0
    confidence: float = 0.0
    meta: ProviderMeta | None = None


@dataclass
class DisfluencyResult:
    score: float
    # [{type: filler|repetition|self_correction, text, start_ms, end_ms}]
    events: list[dict] = field(default_factory=list)
    filler_count: int = 0
    repetition_count: int = 0
    # Zero means the answer was too short to judge. The pipeline drops it
    # rather than recording a floor score as though it were a measurement.
    confidence: float = 0.0
    meta: ProviderMeta | None = None


@dataclass
class AccuracyResult:
    """Did the words come out as the item required (ENG-01 downstream)?

    Distinct from pronunciation on purpose. This measures whether an English
    recogniser recovered the expected words — the primary thing a Repeat
    Sentence task is actually testing. It says nothing about phoneme quality,
    and must never be presented as if it did.
    """

    score: float
    matched: int = 0
    reference_words: int = 0
    accuracy: float = 0.0
    # [{expected, heard, kind: substitution|deletion|insertion, start_ms}]
    word_errors: list[dict] = field(default_factory=list)
    confidence: float = 0.0
    meta: ProviderMeta | None = None


@dataclass
class IntelligibilityResult:
    """How understandable this was to a listener — the metric that matters.

    Deliberately not "how close to a native speaker": accent is not the
    defect, and scoring it as one would be both wrong and cruel.
    """

    score: float
    confidence: float = 0.0
    rater_agreement: float | None = None
    meta: ProviderMeta | None = None


@dataclass
class L1Result:
    l1_language: str
    confidence: float = 0.0
    alternatives: list[dict] = field(default_factory=list)
    meta: ProviderMeta | None = None


@dataclass
class GrammarResult:
    score: float
    # [{type, span, suggestion, severity}]
    errors: list[dict] = field(default_factory=list)
    # Zero means there was not enough language to judge — three correct words
    # are not evidence of good grammar, and neither are they evidence of bad.
    confidence: float = 0.0
    meta: ProviderMeta | None = None


@dataclass
class RelevanceResult:
    """Retell/open-response content coverage (ENG-11).

    Rubric-constrained: ``key_points`` says which required points were found.
    A language model may contribute one signal here, never the verdict.
    """

    score: float
    key_points: list[dict] = field(default_factory=list)
    coverage: float = 0.0
    off_topic: bool = False
    # Zero means "measured, but not scoreable" — an open response has no right
    # answer, so its result is a flag rather than a number the overall can use.
    confidence: float = 0.0
    meta: ProviderMeta | None = None


@dataclass
class SynthesisResult:
    storage_key: str
    duration_ms: int = 0
    accent: str = "indian"
    meta: ProviderMeta | None = None


class ProviderError(RuntimeError):
    """A provider failed. The registry decides whether a fallback runs."""


class ProviderUnavailable(ProviderError):
    """No implementation is configured or importable for this capability."""

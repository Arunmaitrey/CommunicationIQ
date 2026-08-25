"""Provider contracts.

Written before any implementation, on purpose: the BRD's rule is that no
capability exists without its contract (ENG-16). Every module that consumes a
capability imports from here and never from a provider package.
"""
from app.storage.base import StorageProvider
from app.engine.contracts.language import (ContentRelevanceProvider,
                                           GrammarProvider, TTSProvider)
from app.engine.contracts.services import (NotificationProvider,
                                           NotificationResult, PaymentIntent,
                                           PaymentProvider)
from app.engine.contracts.speech import (AccuracyProvider, AlignmentProvider,
                                         ASRProvider, DisfluencyProvider,
                                         FluencyProvider,
                                         IntelligibilityProvider, L1Provider,
                                         PronunciationProvider, VADProvider)
from app.engine.contracts.types import (AccuracyResult, AlignmentResult,
                                        AudioRef, Capability,
                                        DisfluencyResult, FluencyResult,
                                        GrammarResult, IntelligibilityResult,
                                        L1Result, ProviderError,
                                        ProviderMeta, ProviderUnavailable,
                                        PronunciationResult, RelevanceResult,
                                        SpeechSegment, SynthesisResult,
                                        TranscriptResult, VADResult,
                                        WordTiming)

# Which Protocol implements which capability. The registry uses this to refuse
# a provider that does not actually satisfy the contract it claims.
CONTRACT_FOR: dict[Capability, type] = {
    Capability.ASR: ASRProvider,
    Capability.VAD: VADProvider,
    Capability.ALIGNMENT: AlignmentProvider,
    Capability.PRONUNCIATION: PronunciationProvider,
    Capability.ACCURACY: AccuracyProvider,
    Capability.FLUENCY: FluencyProvider,
    Capability.DISFLUENCY: DisfluencyProvider,
    Capability.INTELLIGIBILITY: IntelligibilityProvider,
    Capability.L1_ID: L1Provider,
    Capability.GRAMMAR: GrammarProvider,
    Capability.CONTENT_RELEVANCE: ContentRelevanceProvider,
    Capability.TTS: TTSProvider,
    Capability.NOTIFICATION: NotificationProvider,
    Capability.PAYMENT: PaymentProvider,
    Capability.STORAGE: StorageProvider,
}

__all__ = [
    "ASRProvider", "VADProvider", "AlignmentProvider", "PronunciationProvider",
    "FluencyProvider", "DisfluencyProvider", "GrammarProvider",
    "AccuracyProvider", "AccuracyResult",
    "ContentRelevanceProvider", "TTSProvider", "NotificationProvider",
    "PaymentProvider", "StorageProvider", "IntelligibilityProvider",
    "L1Provider", "NotificationResult", "PaymentIntent",
    "AudioRef", "Capability", "ProviderMeta", "ProviderError",
    "ProviderUnavailable", "TranscriptResult", "VADResult", "AlignmentResult",
    "PronunciationResult", "FluencyResult", "DisfluencyResult", "GrammarResult",
    "RelevanceResult", "SynthesisResult", "IntelligibilityResult", "L1Result",
    "WordTiming", "SpeechSegment",
    "CONTRACT_FOR",
]

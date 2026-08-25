"""Provider implementations, grouped by tier.

* ``tier0`` — heuristic/feature-based. No GPU, no API keys, no network.
* ``tier1`` — local open models (faster-whisper, Silero-VAD, wav2vec2 GOP).
* ``tier2`` — vendor APIs, promoted only after shadow evaluation.

Nothing outside this package imports from it. Consumers go through the
registry, which is what makes a tier swap a configuration change.
"""

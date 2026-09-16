"""Unified provider implementations.

* ``energy_vad`` / ``feature_fluency`` — heuristic, no ML dependencies.
* ``whisper_asr`` / ``wav2vec_gop`` / ``reference_accuracy`` / ``common_error_grammar`` / ``rubric_relevance`` / ``transcript_disfluency`` — ML-assisted, require torch.

Nothing outside this package imports from it. Consumers go through the
registry, which is what makes a provider swap a configuration change.
"""

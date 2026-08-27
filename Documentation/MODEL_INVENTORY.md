# Model Inventory: knowledge.md vs Implementation Status

**Generated:** 2026-08-26  
**Purpose:** Track what's in the design doc vs what's actually built

---

## Summary

| Layer | Total | Implemented | Partial | Missing |
|-------|-------|-------------|---------|---------|
| Layer 1 - Hearing | 3 | 3 | 0 | 0 |
| Layer 2 - Speech Quality | 5 | 3 | 1 | 1 |
| Layer 3 - Language Content | 2 | 2 | 0 | 0 |
| Layer 4 - Intelligence Stack | 4 | 0 | 0 | 4 |
| **Other Contracts** | 4 | 0 | 0 | 4 |
| **TOTAL** | **18** | **8** | **1** | **9** |

---

## Layer 1 — Hearing (speech → signal)

| # | Capability | knowledge.md | Implementation |
|---|---|---|---|
| 1 | **ASR (transcription)** | Whisper / WhisperX-class, fine-tuned on Indian-English later | ✅ **Tier 1**: `app/engine/providers/tier1/asr.py` — faster-whisper with word timestamps. `FasterWhisperASR.transcribe()` returns `TranscriptResult` with words, confidence, language. No hint_text used (correctly). |
| 2 | **Voice activity detection** | Silero-VAD class, off-shelf | ✅ **Tier 0**: `app/engine/providers/tier0/vad.py` — `EnergyVAD` energy-threshold VAD with prompt-end offset for latency. ✅ **Tier 1**: `app/engine/providers/tier1/vad.py` — `SileroVAD` using faster-whisper's bundled Silero ONNX model. Same `VADResult` contract. |
| 3 | **Forced alignment** | WhisperX / MFA (word & phoneme timestamps) | ✅ **Embedded in Pronunciation**: `app/engine/providers/tier1/pronunciation.py` uses `torchaudio.functional.forced_align` on wav2vec2 CTC logits for character-level GOP. No standalone alignment provider registered. |

**Status: COMPLETE** — All 3 capabilities have working implementations.

---

## Layer 2 — Judging speech quality (assessment core)

| # | Capability | knowledge.md | Implementation |
|---|---|---|---|
| 4 | **Pronunciation scoring** | GOP on wav2vec2/HuBERT, fine-tuned SpeechOcean762-style | ✅ **Tier 1**: `app/engine/providers/tier1/pronunciation.py` — `Wav2VecGOP` using facebook/wav2vec2-base-960h. Character-level (not phoneme) posteriors. Scores per-word + overall. SNR penalty. Edge padding for timer-cutoff recordings. Returns `PronunciationResult` with phonemes, mispronounced_words, confidence. |
| 5 | **Fluency & prosody scoring** | Feature-based regressor (GB on pause/rate/pitch), build | ✅ **Tier 0**: `app/engine/providers/tier0/fluency.py` — `FeatureFluency` computes: syllable nuclei rate → WPM, articulation rate, phonation ratio, pause count/mean/longest, stall score. Weighted composite (40/25/20/15). Confidence drops for short/noisy answers. **Tier 1: NOT IMPLEMENTED** — no pitch tracker, no prosody model. |
| 6 | **Disfluency/filler detection** | Token classification on transcript + acoustic cues | ✅ **Tier 1**: `app/engine/providers/tier1/disfluency.py` — `TranscriptDisfluency` detects fillers (um, uh, er...), filler phrases (you know, i mean...), repetitions, false starts (gap ≥ 400ms). Per-100-words penalty. Returns `DisfluencyResult` with events, filler_count, repetition_count. |
| 7 | **Intelligibility model** ⭐ | Regressor predicting human intelligibility ratings per L1 group, trained on own labelled panel data. **Moat model.** | ❌ **MISSING** — Contract exists: `app/engine/contracts/speech.py:101` `IntelligibilityProvider`. No provider implementation. No training data pipeline. This is explicitly the differentiator: "would a hiring panel understand this" vs "accuracy vs native reference". |
| 8 | **L1/accent identification** | Small classifier on speech embeddings (ECAPA-class) | ❌ **MISSING** — Contract exists: `app/engine/contracts/speech.py:119` `L1Provider`. No provider implementation. Used to route L1-specific feedback and power L1-difficulty stats. |

**Status: 3/5 implemented, 1 partial (fluency), 2 missing (intelligibility, L1)**

---

## Layer 3 — Judging language content

| # | Capability | knowledge.md | Implementation |
|---|---|---|---|
| 9 | **Grammar error detection** | GEC model (T5/LLM-based) on transcripts, error-typed | ✅ **Tier 1 (rule-based)**: `app/engine/providers/tier1/grammar.py` — `CommonErrorGrammar` with 40+ high-precision regex rules. Covers: verb+preposition, redundant pairs, agreement, uncountable nouns, tense, stative verbs. **Explicitly excludes Indian English dialect features** (prepone, kindly revert, etc.). Severity-weighted penalty. Returns `GrammarResult` with errors, score, confidence=0.5. **Not an LLM/T5 model** — rule set only. |
| 10 | **Content relevance & retell recall** | Sentence embeddings for key-point coverage + rubric-constrained LLM grading | ✅ **Tier 1**: `app/engine/providers/tier1/relevance.py` — `RubricRelevance` matches key_points via content word overlap (stopword-filtered, threshold 0.5). Three modes: `_coverage` (retell), `_any_of` (short_answer), `_on_topic` (open_response — flag only, score=0, confidence=0). Returns `RelevanceResult` with key_points, coverage, off_topic flag. No embeddings/LLM — simple word overlap. |

**Status: 2/2 implemented (grammar is rule-based not ML; content is word-overlap not embeddings)**

---

## Layer 4 — Intelligence nobody sees (the real moat)

| # | Capability | knowledge.md | Implementation |
|---|---|---|---|
| 11 | **Item calibration** | IRT (2PL): difficulty + discrimination per item, L1-split | ❌ **MISSING** — No IRT implementation. No `app/engine/psychometrics/irt.py` used in production (file exists but not wired). |
| 12 | **Skill mastery tracking** | Bayesian Knowledge Tracing first; DKT if data volume justifies | ❌ **MISSING** — `SkillMastery` document exists in tenant models but no BKT engine. `app/engine/psychometrics/bkt.py` exists but not used for live mastery updates. |
| 13 | **Adaptive item selection** | IRT-information-based selection (CAT), later contextual bandits | ❌ **MISSING** — No adaptive selection. Sections use random sampling from bank with filters. |
| 14 | **Crosswalk readiness prediction** | GBDT / regularized logistic on feature record → outcome band, with isotonic/Platt calibration | ❌ **MISSING** — No readiness prediction model. `CohortReadiness` document exists but computes from current scores, not predictive. |

**Status: 0/4 implemented**

---

## Other Contracts (defined in `app/engine/contracts/__init__.py`)

| Capability | Contract File | Implementation |
|---|---|---|
| **TTS** | `app/engine/contracts/language.py:42` | ❌ No provider. `TTSProvider` protocol exists. |
| **STORAGE** | `app/engine/contracts/__init__.py:46` / `app/storage/base.py` | ❌ No provider. `StorageProvider` protocol exists. Current storage uses `app/storage/` local filesystem directly. |
| **NOTIFICATION** | `app/engine/contracts/services.py:34` | ❌ No provider. `NotificationProvider` protocol exists. |
| **PAYMENT** | `app/engine/contracts/services.py:48` | ❌ No provider. `PaymentProvider` protocol exists. |

---

## Provider Registry Status

The registry system (`app/engine/registry.py`) is **fully implemented** with:
- Per-tenant configuration with global defaults
- Primary / fallback / shadow / canary modes
- Per-call telemetry (`ProviderCall` document)
- Contract validation at load time (`CONTRACT_FOR` mapping)
- Graceful fallback when Tier 1 fails to import (e.g., torch not installed)

**Currently registered providers (from code inspection):**

| Capability | Tier 0 | Tier 1 |
|---|---|---|
| ASR | — | faster_whisper |
| VAD | energy_vad | silero_vad |
| FLUENCY | feature_fluency | — |
| ACCURACY | — | reference_match |
| DISFLUENCY | — | transcript_disfluency |
| GRAMMAR | — | common_error_rules |
| PRONUNCIATION | — | wav2vec2_gop |
| CONTENT_RELEVANCE | — | rubric_coverage |
| INTELLIGIBILITY | — | — |
| L1_ID | — | — |
| TTS | — | — |
| STORAGE | — | — |
| NOTIFICATION | — | — |
| PAYMENT | — | — |

---

## Performance Notes

| Provider | Approx Latency (CPU) | Notes |
|---|---|---|
| faster-whisper ASR | ~0.6× real-time | 8s audio ≈ 5s. Runs on ingest (background). |
| Silero VAD | <100ms | ONNX, very fast. |
| wav2vec2 GOP | ~2-3s per response | Forced alignment is the bottleneck. Loads once per process. |
| Feature Fluency | <50ms | Pure numpy, no model load. |
| Transcript Disfluency | <20ms | Regex on transcript words. |
| Common Error Grammar | <30ms | 40 compiled regexes. |
| Rubric Relevance | <10ms | Set intersection on content words. |

**Pipeline:** Each answer scored on upload (background). VAD → ASR → (if transcript) Fluency, Accuracy, Disfluency, Grammar, Pronunciation, Content in parallel. No batch scoring at submit.

---

## What's Needed to Complete the Inventory

### Priority 1 (Differentiators from knowledge.md)
1. **Intelligibility model** — Collect human ratings from Indian raters, train regressor per L1. This is the stated moat.
2. **L1/accent identification** — ECAPA-TDNN classifier on wav2vec2 embeddings. Routes feedback, powers L1-difficulty stats.

### Priority 2 (Intelligence stack)
3. **IRT calibration** — 2PL on existing response data. Output: difficulty/discrimination per item.
4. **BKT mastery tracking** — Per-skill, per-student hidden state updated per response.
5. **Adaptive selection** — Use IRT info to pick next item maximizing information at student's current estimate.
6. **Readiness prediction** — GBDT on feature record → placement outcome band, with calibration.

### Priority 3 (Missing contracts)
7. **TTS provider** — For prompt playback (currently browser speechSynthesis fallback).
8. **Storage provider** — Abstract local FS to S3/GCS.
9. **Notification provider** — Email/push for engagement events.
10. **Payment provider** — Invoice/billing integration.

---

## Files to Update

- `Documentation/knowledge.md` — Add implementation status column, mark what's built/partial/missing
- `Documentation/MODEL_INVENTORY.md` — This file as living reference
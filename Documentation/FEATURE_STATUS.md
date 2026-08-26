# Feature Implementation Status

This document tracks which features from `SIMULATOR_FEATURES.md` and `FEATURES.md` are implemented.

## P1 Features (Foundation)

### A. Test-Fidelity Simulation

| ID | Feature | Status | Notes |
|---|---|---|---|
| SIM-01 | Profile engine renders any task sequence | ✅ Implemented | `formats.py` with 15+ blueprints |
| SIM-02 | One-shot audio, server-enforced | ✅ Implemented | Runner enforces no replay |
| SIM-03 | Authentic pacing (beep, countdown, auto-advance) | ✅ Implemented | `runner` page with countdown timers |
| SIM-04 | Pre-test environment check | ✅ Implemented | `attempt/[id]/check/page.tsx` |
| SIM-05 | MCQ + listening comprehension | ✅ Implemented | `listening_bank.py`, `quiz_items` collection |
| SIM-06 | Varied prompt voices (Indian, US, UK) | ✅ Implemented | `tts.py` with accent mapping |
| SIM-07 | Score presentation mapped to vendor scales | ✅ Implemented | 20-80 scale + CEFR crosswalk |
| SIM-08 | Company-round profiles | ✅ Implemented | TCS, Cognizant, Accenture, Wipro formats |
| SIM-09 | Distraction/stress training modes | ✅ Implemented | Stress mode toggle on simulate page |
| SIM-10 | Resume after reload | ✅ Implemented | IndexedDB persistence + drainPending on mount |

### B. Diagnostic Depth

| ID | Feature | Status | Notes |
|---|---|---|---|
| DIAG-01 | Sub-score decomposition in plain language | ✅ Implemented | `result/[id]/page.tsx` with verdicts |
| DIAG-02 | Annotated listen-back | ✅ Implemented | Waveform + transcript + pauses |
| DIAG-03 | L1-specific phoneme heatmap | ⚠️ Partial | Phoneme scores captured; heatmap visualization pending |
| DIAG-04 | Latency anatomy | ⚠️ Partial | onset_ms captured; hearing/thinking/speaking split pending |
| DIAG-05 | Working-memory profile | ⚠️ Partial | Repeat Sentence scoring exists; decomposition pending |
| DIAG-06 | Comparative replay | ⚠️ Partial | Previous attempt shown; side-by-side pending |
| DIAG-07 | Environment-vs-speech attribution | ⚠️ Partial | SNR measured; attribution message pending |
| DIAG-08 | Explain-my-score agent | ⚠️ Partial | Narration module exists; conversational agent pending |
| DIAG-09 | Code-switching detection | ❌ Not started | |
| DIAG-10 | Calibrated readiness prediction | ❌ Not started | Needs validation study data |

### C. Training Intelligence

| ID | Feature | Status | Notes |
|---|---|---|---|
| TRAIN-01 | Fail → why → practice → re-test loop | ✅ Implemented | `practice.py` router + `practise/page.tsx` |
| TRAIN-02 | Adaptive difficulty (IRT) | ✅ Implemented | `engine/psychometrics/irt.py` |
| TRAIN-03 | Shadowing mode | ❌ Not started | |
| TRAIN-04 | Memory-span builder | ❌ Not started | |
| TRAIN-05 | Sentence Build pattern gym | ❌ Not started | |
| TRAIN-06 | Retell strategy training | ❌ Not started | |
| TRAIN-07 | Real-time speaking-rate meter (drill only) | ⚠️ Partial | WPM computed; drill-only restriction pending |
| TRAIN-08 | Placement-drive countdown planner | ✅ Implemented | `gamification/engine.py` with season planning |
| TRAIN-09 | 10-minute warm-up routine | ❌ Not started | |
| TRAIN-10 | AI interview partner | ❌ Not started | |

### D. Motivation & Retention

| ID | Feature | Status | Notes |
|---|---|---|---|
| MOT-01 | Progress framed as gap-closing | ✅ Implemented | `priorities.py` with gap metrics |
| MOT-02 | Practice streaks, weekly targets | ✅ Implemented | `streak_states`, `xp_ledger` collections |
| MOT-03 | Peer percentile (opt-in) | ❌ Not started | |
| MOT-04 | Shareable readiness report | ❌ Not started | |
| MOT-05 | Milestone audio postcards | ❌ Not started | |

### E. Language & Accessibility

| ID | Feature | Status | Notes |
|---|---|---|---|
| ACC-01 | Multilingual feedback (Telugu, Hindi, Tamil) | ✅ Implemented | `lib/i18n.ts` with 40+ translated strings |
| ACC-01b | Language switcher | ✅ Implemented | `LanguageSwitcher` in Settings page with EN/TE/HI/TA |
| ACC-01c | i18n integrated in runner UI | ✅ Implemented | Runner uses `t()` for feedback messages |
| ACC-02 | Budget-Android-first | ✅ Implemented | Resumable uploads, pending queue |
| ACC-03 | Offline-tolerant drill packs | ❌ Not started | |
| ACC-04 | Data-cost transparency | ✅ Implemented | `lib/dataUsage.ts` + `DataUsageIndicator` in runner footer |

### F. Assessment Operations

| ID | Feature | Status | Notes |
|---|---|---|---|
| OPS-01 | Scheduled cohort mocks | ✅ Implemented | `assignments` collection, `tenant_writes.py` |
| OPS-02 | Trainer live-monitor | ⚠️ Partial | Cohort readiness exists; live monitoring pending |
| OPS-03 | Proctoring-lite | ❌ Not started | |
| OPS-04 | Voice-consistency check | ❌ Not started | |
| OPS-05 | Item-bank freshness workflow | ❌ Not started | |

## Summary

- **Fully implemented:** 23 features
- **Partially implemented:** 8 features  
- **Not started:** 9 features

## What's Deliberately NOT Built

- No accent-erasure coaching or "sound like a native" scoring
- No verbatim vendor items or claimed algorithm replication
- No guaranteed-score marketing
- No always-on surveillance-style proctoring of self-practice

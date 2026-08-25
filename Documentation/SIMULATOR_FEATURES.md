# Communication IQ — Simulator Feature Spec (Vendor Parity + Beyond)

The simulator is the product's front door: a full-fidelity replica of Versant-style, SVAR-style, and SpeechX-style assessments — plus a layer of capabilities none of those vendors (or any practice app) offers. This document covers the simulation and training experience specifically; platform/tenant/billing features live in `FEATURES.md`.

Tagging: **[PARITY]** = matches what real tests do (table stakes) · **[EDGE]** = beyond any vendor or practice app today · **P1/P2/P3** = build phase, aligned to `FEATURES.md`.

---

## A. Test-Fidelity Simulation (mimic the real thing exactly)

### A1. Vendor-style profiles, section by section

| Simulated section | Versant-style (6 parts, ~20 min) | SVAR-style (6 sections, 16–20 min) | SpeechX-style (4 sections, ~45 min) |
|---|---|---|---|
| Read Aloud | Part A | Section 1 | Section A (sentences + passages) |
| Repeat Sentence | Part B | Section 2 (up to 40 words) | — |
| Short Answer Q&A | Part C | Section 3 (listening deductions) | — |
| Sentence Build | Part D | — | — |
| Story Retell | Part E | — | — |
| Open Response | Part F (40s opinion) | Section 6 (30–45s extempore) | Section B (up to 60s) |
| Grammar/Vocab MCQ | — | Sections 4–5 (error ID) | Section C |
| Audio Comprehension | — | — | Section D (long clips, MCQ) |

- **SIM-01 [PARITY, P1]** — Profile engine renders any configured task sequence with per-section timing, item counts, and instructions matching the target test style.
- **SIM-02 [PARITY, P1]** — One-shot audio: prompts play exactly once, no replay, no pause — enforced server-side, not just in the UI.
- **SIM-03 [PARITY, P1]** — Authentic pacing artifacts: beep-to-speak cues, countdown clocks, auto-advance on timeout, no back-navigation.
- **SIM-04 [PARITY, P1]** — Pre-test environment check exactly like the real flow: mic check, playback check, ambient-noise measurement, headphone detection.
- **SIM-05 [PARITY, P2]** — MCQ + listening-comprehension task types (SVAR Sections 4–5, SpeechX C–D) so full-length SVAR/SpeechX profiles are complete, not just the speaking parts.
- **SIM-06 [PARITY, P2]** — Varied prompt voices: TTS/recorded prompts in Indian, US, and UK accents at test-realistic speeds, because real tests don't use one comfortable voice.
- **SIM-07 [PARITY, P2]** — Score presentation mapped to each style's scale and bands (e.g., Versant-style 20–80 overall + 4 sub-scores; CEFR crosswalk), so a student sees the number format their recruiter will see.
- **SIM-08 [PARITY, P2]** — Company-round profiles: TCS/Infosys/Accenture/Cognizant-style communication-round flows assembled from the same task engine, kept current each season.

### A2. Beyond-real-test realism

- **SIM-09 [EDGE, P2]** — **Distraction/stress conditions**: optional modes that add hostel-corridor background noise, slightly compressed timers, or an unexpected item order — training under worse-than-real conditions so the real test feels easy. (Never scored as the official attempt; clearly labeled training modes.)
- **SIM-10 [EDGE, P2]** — **Time-compression training**: practice at 0.9× the real time allowance; graduate back to 1.0× — the mock-CAT trick applied to speaking.
- **SIM-11 [EDGE, P3]** — **Full drive-day rehearsal**: a scheduled, proctoring-lite, no-retake mock that reproduces the actual one-shot stakes — cohort takes it simultaneously, results release together, like the real drive.

---

## B. Diagnostic Depth (where we beat every vendor)

The real tests give a number. We give the "why" — this section is the moat in feature form.

- **DIAG-01 [EDGE, P1]** — **Sub-score decomposition in plain language**: grammar / pronunciation / fluency / response-latency, each with a verdict ("fine — stop worrying"), and one explicit *biggest lever* ("+4 predicted points if you fix latency").
- **DIAG-02 [EDGE, P1]** — **Annotated listen-back**: replay your own answer with a synced transcript — fillers highlighted, pauses visualized as gaps, speech-rate curve overlaid, mispronounced words flagged at the exact timestamp.
- **DIAG-03 [EDGE, P2]** — **L1-specific phoneme heatmap**: your personal confusion pairs (e.g., Telugu-L1 p/b, v/w; Hindi-L1 s/ʃ; Tamil-L1 word-final stops), ranked by how much each costs you — with auto-generated minimal-pair drills per pair.
- **DIAG-04 [EDGE, P2]** — **Latency anatomy**: response time split into hearing-lag vs. thinking-lag vs. speaking-onset, per task type — because "slow to start" has three different causes with three different fixes.
- **DIAG-05 [EDGE, P2]** — **Working-memory profile**: Repeat Sentence failures decomposed into memory-span limits vs. language limits (did you fail 12-word sentences you understood, or 6-word sentences you didn't parse?).
- **DIAG-06 [EDGE, P2]** — **Comparative replay**: attempt 1 vs. attempt N, same task type, side by side — audio, waveform, and metrics — so improvement is *audible*, not just a number.
- **DIAG-07 [EDGE, P2]** — **Environment-vs-speech attribution**: noise/clipping detection that says "your mic environment cost you points, not your English" when that's true — honesty that also prevents unfair self-blame.
- **DIAG-08 [EDGE, P3]** — **"Explain my score" agent**: a conversational assistant grounded strictly in the student's own feature record ("why did I get 61 in fluency?" → answers from their actual pause data, never generic advice).
- **DIAG-09 [EDGE, P2]** — **Code-switching / mother-tongue insertion detection**, flagged gently as a habit with targeted substitution drills.
- **DIAG-10 [EDGE, P3]** — **Calibrated readiness prediction with honest confidence**: "estimated Versant-style band 52 ± 4" — a range, never false precision, gated on enough paired outcome data (BRD ENG-15).

---

## C. Training Intelligence (the drill loop)

- **TRAIN-01 [EDGE, P1]** — Fail → why → 5 similar items → 1 harder challenge → re-test → mastery, targeted at the weakest sub-skill (the slide-9 loop).
- **TRAIN-02 [EDGE, P2]** — **Adaptive difficulty**: item selection driven by IRT calibration so every drill sits at the edge of the student's ability, not a fixed ladder.
- **TRAIN-03 [EDGE, P2]** — **Shadowing mode**: hear a model sentence, speak along or after it, see your pitch/rhythm curve overlaid on the reference — prosody training without "sound American" framing; the reference is an intelligible Indian-English speaker.
- **TRAIN-04 [EDGE, P2]** — **Memory-span builder**: graduated Repeat Sentence ladder (6 → 18 words) that trains the working-memory component separately from the language component.
- **TRAIN-05 [EDGE, P2]** — **Sentence Build pattern gym**: jumbled-sentence drills organized by grammar pattern (clause order, prepositions, tense sequence) so errors train the *rule*, not the item.
- **TRAIN-06 [EDGE, P2]** — **Retell strategy training**: key-point extraction practice — listen, tap the key points, then retell — teaching the note-taking-in-your-head skill the task actually measures.
- **TRAIN-07 [EDGE, P2]** — **Real-time speaking-rate meter in drill mode only** (never in test mode): live WPM and pause feedback while practicing, removed under test conditions so students don't develop meter-dependence.
- **TRAIN-08 [EDGE, P2]** — **Placement-drive countdown planner**: enters the drive date, works backward to a daily 20–30 min plan across their specific gaps; re-plans automatically when they miss days.
- **TRAIN-09 [EDGE, P3]** — **10-minute warm-up routine** for the morning of the real test, personalized to the student's habits (their phoneme pairs, their pacing) — the last-mile feature nobody offers.
- **TRAIN-10 [EDGE, P3]** — **AI interview partner**: open-response practice with follow-up probing questions (HR-round style), scored with the same engine — extends the simulator into the human-interview round.

---

## D. Motivation & Retention (dignity-first, not gimmick gamification)

- **MOT-01 [EDGE, P1]** — Progress framed as gap-closing ("fluency gap: 9 → 4 points"), never as streaks of shame. Every message passes the slide-11 test: dignity in, practice out.
- **MOT-02 [P2]** — Practice streaks, weekly targets, and cohort challenges ("your section's average latency dropped 0.4s this week") — competitive at cohort level, private at individual level.
- **MOT-03 [P2]** — Peer percentile with consent: "68th percentile among final-years in your branch" — opt-in, because for some students this motivates and for others it wounds.
- **MOT-04 [P3]** — Shareable readiness report: a verified, dated summary a student can attach to applications — carefully worded as *platform* readiness, never a vendor score claim.
- **MOT-05 [P2]** — Milestone audio postcards: the system replays your attempt-1 audio next to today's — "listen to yourself three weeks ago." The single most convincing artifact we can produce.

## E. Language & Accessibility (built for tier-2/3 reality)

- **ACC-01 [P1]** — Feedback and instructions available in Telugu, Hindi, and Tamil — the *explanation* in the student's language, the *practice* in English.
- **ACC-02 [P1]** — Budget-Android-first: capture works on low-end devices, degrades gracefully on 3G-class connections, resumable uploads on network drops.
- **ACC-03 [P2]** — Offline-tolerant drill packs: download a drill set, practice offline, sync scores when connectivity returns.
- **ACC-04 [P2]** — Data-cost transparency: show MB used per session; audio-quality settings that trade fidelity for data on request.

## F. Assessment Operations (tenant-facing simulator features)

- **OPS-01 [P1]** — Scheduled cohort mocks: tenant sets a window; students take the same profile under identical conditions; results land on the readiness dashboard.
- **OPS-02 [P2]** — Trainer live-monitor during scheduled mocks: who's started, who's stuck, whose mic failed — placement-lab reality handled.
- **OPS-03 [P2]** — Proctoring-lite for tenant-mandated attempts: tab-switch detection, random liveness prompts, session photos if the tenant requires — off by default for self-practice, because practice must feel private.
- **OPS-04 [P3]** — Voice-consistency check (same speaker across attempts) for tenant-official mocks — DPDP-sensitive, explicit consent, never for self-practice.
- **OPS-05 [P2]** — Item-bank freshness workflow: LLM-assisted item generation feeding a human psychometric review queue — content velocity without unreviewed items ever reaching students (BRD CONTENT-04 guardrail applies).

---

## What we deliberately do NOT build

- No accent-erasure coaching or "sound like a native" scoring — intelligibility is the metric (slide 11; it's also the honest one).
- No verbatim vendor items, no claimed replication of Pearson/SHL/Mettl algorithms — format, timing, and pressure only ("-style").
- No guaranteed-score marketing — calibrated predictions with confidence ranges, or nothing.
- No always-on surveillance-style proctoring of self-practice — practice must be private to work; proctoring exists only for tenant-official mocks.

---

## Suggested build order within the simulator

1. **P1:** SIM-01→04, DIAG-01→02, TRAIN-01, MOT-01, ACC-01→02, OPS-01 — a real simulator with a real diagnosis, on real students' phones.
2. **P2:** full vendor-profile coverage (SIM-05→08), the diagnostic depth set (DIAG-03→07, 09), the training gym (TRAIN-02→08), stress modes (SIM-09→10), cohort ops (OPS-02→03, 05).
3. **P3:** drive-day rehearsal (SIM-11), readiness prediction (DIAG-10), explain-my-score agent (DIAG-08), warm-up routine (TRAIN-09), AI interview partner (TRAIN-10), shareable report (MOT-04).

Traceability: engine capabilities behind these features are ENG-01→21 in `FEATURES.md` / BRD §8.5. Task-format ground truth for the vendor tables is `Documentation/knowledge.md`.

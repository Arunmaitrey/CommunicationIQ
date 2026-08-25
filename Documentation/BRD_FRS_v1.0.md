# Communication IQ — Consolidated BRD + FRS (Baseline v1.0)

**Product:** Communication IQ — AI spoken-assessment simulator & gamified training platform (multi-tenant SaaS)
**Prepared for:** SaashX AI Labs
**Date:** 17 August 2026 · **Status:** Baseline v1.0 — supersedes BRD v0.1 draft
**Baselines:** `CommunicationIQ_BRD.docx` (v0.1), `FEATURES.md`, `SIMULATOR_FEATURES.md`, `PREREQUISITES.md`, `Documentation/knowledge.md`, `Documentation/CommunicationIQ-Student-Impact.pptx`
**New in v1.0:** Full gamification layer (Part III) — Duolingo-grade engagement mechanics, redesigned around a different purpose: *finite mission, not infinite engagement.*

---

# PART I — BUSINESS REQUIREMENTS (BRD)

## 1. Vision

Final-year students at tier-2/3 Indian engineering colleges face AI-scored spoken-English rounds (Pearson Versant, SHL SVAR, Mercer | Mettl SpeechX, company voice rounds) as a placement gate — usually seeing the format for the first time in the real test, and failing it without ever learning why. Communication IQ is a full-fidelity simulator of those gates plus a diagnosis-first training engine: it replaces the verdict ("my English is bad") with a named, closeable gap ("a 9-point fluency gap and slow response latency"), then drills exactly that gap until it closes.

**v1.0 addition — the engagement thesis:** Diagnosis alone converts avoidance into intent; *habit* converts intent into practice. The platform is therefore fully gamified — streaks, XP, quests, leagues, quizzes, seasonal campaigns — at Duolingo's level of craft, but with an inverted purpose:

| | Duolingo | Communication IQ |
|---|---|---|
| Goal | Lifetime engagement — never leave | **Mission completion — get placed, then leave** |
| Time frame | Infinite | Finite: a countdown to placement-drive day |
| Win condition | Streak itself | Gap closed + real assessment cleared |
| Emotional engine | Fun, fear of streak loss | Momentum, visible progress toward a job |
| Success metric | DAU forever | Readiness on drive day; the student *graduating off the app* is success |

Every gamified mechanic in Part III is judged against one rule: **it must increase drive-day readiness, not just time-on-app.** Engagement is the vehicle. Placement is the purpose.

## 2. Business Objectives

1. Unlimited realistic practice for AI spoken rounds — the real test becomes attempt №15, not attempt №1.
2. Diagnosis over verdict — every score decomposed into named, trainable sub-skills.
3. A daily-habit engine (gamification) that sustains 20–30 min/day of targeted practice across a placement season without human enforcement.
4. Own-build assessment engine (ASR → scoring → psychometrics) behind a provider-abstraction layer — third-party AI pluggable later, per capability, per tenant, via configuration.
5. Multi-tenant B2B2C SaaS: platform operator controls tenants/pricing/providers; institutions manage their staff, students, cohorts; students get a private, personal experience.
6. Long-term moat: Indian-L1 intelligibility model trained on the platform's own labelled data + closed-loop outcome data (simulation → real result → placement) from the partner-college network.

## 3. Scope

**In scope (this baseline):** Platform Admin, Tenant Admin, Trainer, and Student modules; the simulator (all vendor-style + company-round profiles); the own-build engine (Layers 1–4) with provider abstraction; the full gamification system; quizzes (grammar/vocab/listening MCQ as both game content and SVAR/SpeechX-section parity); notifications; billing (Razorpay Day-1, pluggable); reporting; SSO/export integrations; DPDP-aligned consent and data rights.

**Out of scope (this phase):** native mobile apps (mobile-web first); non-English tracks; video assessment; any replication of vendors' proprietary items or algorithms ("-style" only); third-party AI adapters (architecture supports them; building them is deferred); B2C go-to-market.

## 4. Personas (engagement-relevant view)

- **Ravi — final-year, Telugu-medium schooling, first-generation graduate.** Believes his English is bad. Avoids speaking. Has 90 days to drive day. Needs: privacy, dignity, visible progress, a reason to open the app tomorrow.
- **Placement Officer.** 4,800 students, 90 days, no way to give individual attention. Needs: a dashboard that says who's ready, who's at risk, and proof the intervention hours worked.
- **Trainer.** Runs the communication lab. Needs: per-student diagnosis, assignable drills, and cohort momentum she can see.
- **Platform Operator (SaashX).** Needs: tenant/pricing/provider control, engine observability, and engagement telemetry that distinguishes healthy habit from hollow grinding.

## 5. Business Model

B2B2C institutional licensing (per-seat / flat / usage-based, free pilots), GST-invoiced via pluggable gateway (Razorpay Day-1). Gamification is a retention asset for the *tenant's renewal decision* too: seat utilization and streak participation become the numbers a placement officer shows their principal.

## 6. Success Metrics

| Metric | Target intent |
|---|---|
| Baseline completion | ≥60% of assigned cohort within 2 weeks |
| **Habit formation** | ≥40% of active students hold a ≥7-day practice streak in any given month |
| **Daily quest completion** | ≥50% of daily-active students complete the day's quest |
| Resimulation depth | ≥5 avg. full-simulation attempts per student per season (target: 15) |
| Gap closure | Measurable sub-score improvement attempt 1 → attempt 5 for ≥70% of students who complete ≥12 targeted hours |
| **Graduation** | % of students who reach "drive-ready" state before their drive date — the metric Duolingo would never use |
| Tenant renewal | ≥80% after first full season |
| Engine trust | Human-rater correlation above the pre-launch accuracy bar, monitored per model version |

## 7. Key Risks (carried forward + gamification-specific)

1. **Own-build engine underperforms early** → provider-abstraction layer allows temporary third-party fallback per tenant (reversible decision by design).
2. **IP exposure** on "-style" simulation → independent legal review before scale; content guardrails block verbatim vendor items.
3. **DPDP non-compliance** (voice ≈ biometric-adjacent) → consent-first, DPO named, India residency, deletion rights.
4. **Gamification backfires** *(new)* — streak anxiety on top of placement anxiety; XP-farming shallow drills instead of hard practice; shame from public comparison. → Mitigations are structural, in Part III §G: streak freezes are free, XP is effort-weighted toward weaknesses, all individual data is private-by-default, and every mechanic passes the "does this raise drive-day readiness?" test.
5. **Cold-start content** — gamification demands volume (quests/quizzes daily) → LLM-assisted item generation with mandatory human psychometric review before any item reaches students.

---

# PART II — FUNCTIONAL REQUIREMENTS SPECIFICATION (FRS)

Conventions: requirement IDs carry over from the baselined docs (PLAT/TEN/TRN/STU/ENG/SIM/DIAG/TRAIN/CONTENT/NOTIF/BILL/RPT/INT). New v1.0 series: **GAM** (gamification), **QUIZ** (quiz system). Priorities: **M**ust / **S**hould / **C**ould. Phases P1/P2/P3 as previously defined. Where a requirement is unchanged from a baselined doc, it is listed in summary; where new or changed, it is specified in full with acceptance criteria (AC).

## 8. Platform Admin Module (operator console)

Carried forward unchanged: PLAT-01…PLAT-16 (tenant lifecycle; tenant config; plan templates; plan assignment/overrides; GST invoicing; dunning; Provider Registry; active/fallback provider per capability via config; shadow mode; canary routing; global content library; cross-tenant analytics; provider performance dashboards; immutable audit log; support queue; role-scoped MFA staff accounts).

**New in v1.0:**

- **PLAT-17 (M, P1) — Gamification configuration console.** Platform Admin can tune the game economy per tenant or globally: XP values per activity type, streak rules, quest difficulty mix, league on/off, season calendar binding. AC: changing any value requires no deployment; every change is audit-logged; a tenant can be set to "gamification-lite" (progress bars and streaks only, no leagues) without code changes.
- **PLAT-18 (S, P2) — Engagement telemetry dashboard.** Distinguishes healthy engagement (drills on weak skills, rising mastery) from hollow engagement (XP-farming easy content). AC: dashboard shows, per tenant, the ratio of weighted-XP earned on weakness-targeted activity vs. total; flags cohorts where quiz-XP > 70% of total XP (grinding signal).

## 9. Tenant Admin Module

Carried forward unchanged: TEN-01…TEN-12 (guided onboarding; branding/subdomain; bulk import; role management; cohorts; assignment with deadlines; readiness dashboard; drill-down; seat usage; exports/LMS push; announcements; hard tenant isolation).

**New in v1.0:**

- **TEN-13 (M, P1) — Season setup.** Tenant Admin binds gamification to reality: sets the placement-drive window per cohort; the system derives each student's countdown, season length, and quest pacing from it. AC: a cohort without a set drive date defaults to a rolling 90-day season; changing the date re-plans quests within 24h.
- **TEN-14 (S, P2) — Cohort challenge management.** Tenant Admin/Trainer can launch cohort-vs-cohort challenges (e.g., CSE-A vs CSE-B weekly latency improvement). AC: challenges compare *cohort aggregates only*; no individual student is publicly ranked by the system in any tenant-visible view.

## 10. Trainer Module

Carried forward: TRN-01…TRN-05 (cohort-scoped diagnostics; manual drill assignment; at-risk flags with notes; intervention-outcome tracking; read/assign-only access).

**New in v1.0:**

- **TRN-06 (S, P2) — Momentum view.** Trainer sees cohort streak/quest participation alongside skill mastery — who is practicing consistently vs. who has gone dark. AC: "gone dark ≥5 days with drive date <45 days away" produces an automatic at-risk suggestion to the trainer, not an automatic message shaming the student.

## 11. Student Module — Core Flow

Carried forward: STU-01…STU-14 (invite/SSO registration; consent-first recording; baseline diagnostic; 6 task types in vendor-style profiles; one-shot/timed fidelity; streaming capture; result screen within latency budget with "biggest lever"; drill loop; plan-governed resimulation; progress dashboard; reminders; data export/deletion; budget-Android/low-bandwidth resilience; strict visibility boundaries).

Simulator detail carried forward from `SIMULATOR_FEATURES.md`: SIM-01…SIM-11 (profile engine, one-shot enforcement, pacing artifacts, environment check, MCQ/listening parity sections, varied prompt accents, vendor-scale score presentation, company-round profiles, stress/distraction modes, time-compression training, drive-day rehearsal), DIAG-01…DIAG-10 (sub-score decomposition, annotated listen-back, L1 phoneme heatmap, latency anatomy, working-memory profile, comparative replay, environment-vs-speech attribution, explain-my-score agent, code-switch detection, calibrated readiness with confidence range), TRAIN-01…TRAIN-10 (drill loop, adaptive difficulty, shadowing, memory-span builder, sentence-build gym, retell strategy, drill-mode rate meter, countdown planner, warm-up routine, AI interview partner).

## 12. Assessment Engine

Carried forward unchanged: ENG-01…ENG-21 — Layer 1 (ASR with word timestamps; VAD/latency features; forced alignment), Layer 2 (phoneme-level pronunciation; interpretable fluency/prosody; disfluency detection; Indian-L1 intelligibility model gated on the human-rater labelling program; L1/accent ID), Layer 3 (grammar error typing; rubric-constrained content relevance — never sole-LLM judged), Layer 4 (IRT calibration; BKT mastery; adaptive selection; calibrated outcome prediction behind a data-volume gate), and the cross-cutting provider abstraction (versioned Provider Contracts; registration-only extension; runtime per-tenant selection; automatic fallback; shadow mode; provider/version stamped on every score).

**Engine additions serving gamification:**

- **ENG-22 (M, P1) — Mastery event stream.** The engine emits typed events (skill_mastery_up, gap_closed, personal_best, plateau_detected) consumed by the gamification service. AC: events are derived from BKT/score deltas, not from raw activity counts — the game rewards *getting better*, not *doing more*.
- **ENG-23 (S, P2) — Difficulty-aware scoring of quiz items.** Quiz items carry IRT difficulty; XP awarded scales with item difficulty relative to student ability. AC: a student answering at their edge earns more than a student farming easy items, verifiably in the XP ledger.

## 13. Quiz System (new — QUIZ series)

Quizzes serve double duty: they are *real test parity* (SVAR Sections 4–5 grammar/error-ID; SpeechX Sections C–D grammar/vocab MCQ and audio comprehension) and the game's fast-loop content (30-second interactions for days when a student won't do a full speaking drill).

- **QUIZ-01 (M, P1) — MCQ engine.** Timed multiple-choice and fill-in-the-blank items: grammar, vocabulary, sentence correction, error identification. AC: item formats cover SVAR 4–5 and SpeechX C styles; per-item timer configurable; items served from the versioned item bank with difficulty metadata.
- **QUIZ-02 (M, P2) — Audio-comprehension quizzes.** Listen-once clips followed by MCQs (SpeechX D / SVAR 3 style), with varied Indian/US/UK prompt accents. AC: one-shot playback enforced; clip + question metadata versioned.
- **QUIZ-03 (M, P1) — Micro-session design.** Any quiz playable in ≤3 minutes; resumable; fully functional offline with deferred sync (pairs with ACC-03 drill packs). AC: a 10-item quiz works end-to-end on a throttled 3G-class connection.
- **QUIZ-04 (S, P2) — Speed rounds.** Rapid-fire error-spotting under a per-item shot clock — trains the time-pressure reflex that fails students in real MCQ sections. AC: speed-round results feed the latency profile (DIAG-04), not just XP.
- **QUIZ-05 (S, P2) — Mistake bank.** Every wrong answer enters a personal review queue; spaced-repetition resurfacing until mastered. AC: resurfacing schedule follows a documented SR algorithm; mastered items retire.
- **QUIZ-06 (M, P1) — Quiz XP capping.** Quiz XP counts toward daily quests but is capped as a share of weekly XP so quizzes cannot substitute for speaking practice. AC: cap configurable (default: quiz XP ≤40% of weekly XP counted toward league/level progression).

## 14. Notifications, Billing, Reporting, Integrations

Carried forward unchanged: NOTIF-01…04 (pluggable channels; per-tenant/type config; templated localizable content; consent-stored opt-in/out), BILL-01…08 (pluggable gateway, Razorpay Day-1; seat/flat/usage models; trials; GST invoices; proration; dunning; coupons; no raw payment credentials), RPT-01…04 (three role-gated tiers; exports/scheduling; closed-loop outcome report; consent- and tenant-scoped analytics), INT-01…04 (Google/Microsoft SSO; LMS/placement-portal export; public API; consent-gated data egress).

**Additions:**

- **NOTIF-05 (M, P1) — Engagement notifications with hard limits.** Streak reminders, quest availability, league updates — capped at 1 engagement notification/day by default, quiet hours enforced, one-tap mute-forever, and *all* engagement messaging suppressed for a student in the 24h before their real drive date except their warm-up routine prompt. AC: caps are per-tenant configurable but the mute right is not removable.
- **RPT-05 (S, P2) — Engagement vs. outcome report.** For tenants: does streak participation correlate with readiness improvement in this cohort? Honest reporting — if the correlation is weak, the report says so. AC: report includes confidence framing, not bare correlations.

## 15. Non-Functional Requirements

Carried forward: NFR-01…NFR-13 (≤5s scripted / ≤8s unscripted scoring latency; placement-season concurrency sizing; ≥99.5% seasonal availability; TLS + at-rest encryption; MFA + API-layer RBAC; zero-deploy provider switching; DPDP compliance with verifiable consent and deletion; India data residency; Telugu/Hindi/Tamil UI localization; budget-device/3G resilience; audit of score-affecting actions; DR with defined RPO/RTO; no provider promotion without shadow/canary evaluation).

**Additions:**

- **NFR-14 (M, P1) — Gamification latency.** XP/streak/quest state updates render ≤1s after the triggering action; the reward moment must feel instant even when speech scoring is still processing (optimistic UI with reconciliation).
- **NFR-15 (M, P1) — Game-state integrity.** XP ledger is append-only and server-authoritative; client-reported XP is never trusted; anti-abuse rate limits on XP-earning endpoints.
- **NFR-16 (M, P1) — Ethical engagement constraints (structural, not policy).** No pay-to-restore-streak, no loot boxes/gacha mechanics, no public individual leaderboards at tenant level, no dark-pattern countdown pressure unrelated to the real drive date. These are build-time constraints: the systems that would enable them are not built.

## 16. Data Model Additions (v1.0)

New entities joining the baseline model (Tenant, Plan, Subscription, User, Cohort, ConsentRecord, SimulationProfile, TaskItem, Attempt, ResponseAudio, ScoreRecord, ProviderRegistry/Config, ModelVersion, AuditLog, NotificationLog):

| Entity | Purpose |
|---|---|
| XPLedger | Append-only record of every XP award: activity, base XP, difficulty multiplier, weakness multiplier, caps applied |
| StreakState | Current streak, best streak, freeze inventory, freeze-usage history |
| Quest | Daily/weekly quest instance: objective, target skill, progress, completion |
| League | Weekly league grouping (opt-in), membership, standings |
| Badge | Earned achievements with earn criteria version |
| SeasonPlan | Student's countdown plan derived from drive date: weekly targets, re-planning history |
| QuizItem / QuizAttempt | MCQ/listening items (IRT-tagged) and responses feeding both XP and diagnostics |
| MistakeBankEntry | Wrong answers with spaced-repetition schedule state |
| EngagementEvent | Telemetry stream powering PLAT-18 (healthy-vs-hollow analysis) |

---

# PART III — GAMIFICATION SYSTEM DESIGN (GAM series)

Design charter: **Duolingo's craft, inverted purpose.** Duolingo optimizes for never leaving; we optimize for *leaving successfully*. The season ends on drive day. The game's final level is the real test. "Addictive" here means: the student who was avoiding English opens the app anyway, daily, for 20 minutes — because the app makes progress visible, effort rewarding, and tomorrow's session feel worth showing up for.

## A. The Core Loop

Daily open → **Today's Quest** (auto-built from the student's weakest skill + drive-date pacing) → warm-up quiz (2 min) → targeted speaking drill (10–15 min) → instant reward moment (XP + gap-meter movement) → tomorrow's quest preview. One full simulation ("Boss Mock") per week anchors the loop to reality.

- **GAM-01 (M, P1) — Daily Quest.** One personalized objective per day ("Cut your average response delay below 1.2s in 5 Repeat-Sentence items"), generated from the diagnostic profile and season pacing. AC: quest always targets a top-3 weakness or scheduled review; completing it awards bonus XP and advances the streak; a full simulation always satisfies the day's quest.
- **GAM-02 (M, P1) — XP economy, effort-weighted.** Base XP per activity × difficulty multiplier (IRT-relative) × weakness multiplier (higher XP for training weak skills). AC: the multiplier table is platform-configurable (PLAT-17); the same activity yields visibly more XP when it targets the student's declared gap; all math is server-side (NFR-15).
- **GAM-03 (M, P1) — Levels & the Gap Meter.** Two progress bars, deliberately distinct: *Level* (XP-driven, effort recognition — always goes up) and the *Gap Meter* (mastery-driven, honest — moves only when the diagnosed gap actually closes, can plateau). AC: UI never conflates them; plateau on the Gap Meter triggers a coaching message and drill-mix change, not more XP.

## B. Streaks (the habit engine)

- **GAM-04 (M, P1) — Practice streak.** A day counts toward the streak when the Daily Quest is completed (not mere app-open). Streak milestones (7/14/30/60/90) award badges and streak freezes. AC: streak state visible on home screen; milestone moments celebrated with restraint (dignity rule — no infantilizing animations for a 21-year-old preparing for a job).
- **GAM-05 (M, P1) — Streak freezes, free and earned.** 2 free freezes/month + freezes earned at milestones; auto-applied on a missed day. **Never purchasable.** AC: a student returning after a lapse sees "welcome back — here's where your gap stands" and a 3-day rebuild quest, not a guilt screen; freeze economy configurable per tenant within platform-set floors.
- **GAM-06 (S, P2) — Streak repair window.** A missed day can be repaired within 24h by completing a double quest — effort, not payment. AC: repair usable ≤2×/month.

## C. Quests, Chapters & the Season

- **GAM-07 (M, P1) — Season = countdown to drive day.** The whole game calendar derives from the cohort's real placement window (TEN-13). Season map shows weeks remaining, weekly themes (e.g., Week 3: latency; Week 4: retell structure), and the drive-day rehearsal as the finale. AC: re-planning on missed weeks is automatic (TRAIN-08); the countdown shown is always the *real* date — manufactured urgency is prohibited (NFR-16).
- **GAM-08 (M, P1) — Skill chapters with mastery gates.** Content organized as chapters per sub-skill (Pronunciation Habits, Response Speed, Sentence Building, Retell Craft, Open Response, Grammar Under Pressure). A chapter completes on *demonstrated mastery* (BKT threshold via ENG-22), not on content consumption. AC: chapter completion is reflected on the trainer's dashboard as a mastery event.
- **GAM-09 (M, P2) — Boss Mocks.** Weekly full-length simulation styled as the chapter boss: higher stakes framing, full result ceremony, comparative replay against the previous boss attempt (DIAG-06). AC: boss results drive next week's quest mix; skipping a boss two weeks running triggers a trainer-visible momentum flag (TRN-06), not a student-facing shame message.
- **GAM-10 (S, P2) — Weekly quests & side quests.** Weekly objectives (e.g., "3 speaking drills + 1 boss mock + clear 10 mistake-bank items") and opt-in side quests (shadowing session, speed round). AC: weekly quest completion is the primary streak-independent progress signal for trainers.

## D. Social & Competition (private-by-default)

- **GAM-11 (S, P2) — Leagues, opt-in and pseudonymous.** Weekly XP leagues of ~20 students drawn tenant-wide (not within a single classroom, to reduce social exposure), under chosen display names. Promotion/demotion tiers like Duolingo. AC: opt-out at any time; real identity never shown; league XP respects the quiz cap (QUIZ-06) so speaking practice decides leagues.
- **GAM-12 (S, P2) — Cohort challenges (aggregate only).** Section vs. section on aggregate improvement metrics (TEN-14). AC: no individual's data identifiable in any challenge view.
- **GAM-13 (C, P3) — Duo drills.** Two students pair for accountability: shared weekly quest, mutual streak visibility by consent. AC: pairing requires both students' explicit opt-in and is dissolvable by either, silently.
- **GAM-14 (S, P2) — Percentile, private.** "You're at the 68th percentile of final-years in your branch" — shown only to the student, opt-in (MOT-03), never in any list.

## E. Badges, Milestones & Identity

- **GAM-15 (M, P1) — Badge system.** Badges for mastery events (first chapter cleared, latency under 1s, personal-best boss score), consistency (streak milestones), and courage (first Open Response, first full mock — the hardest button for this population to press). AC: badge criteria versioned; earning moments logged; no badge for mere volume.
- **GAM-16 (S, P2) — Milestone audio postcards.** At streak/chapter milestones the app replays attempt-1 audio beside today's (MOT-05) — the single most convincing artifact of progress. AC: student can share the postcard *outward* (their choice); the platform never shares it for them.
- **GAM-17 (S, P3) — Graduation.** When a student's drive window passes: a closing ceremony — season summary, gap-then vs. gap-now, badges earned, shareable readiness report (MOT-04). The app explicitly celebrates *leaving*. AC: post-graduation, engagement notifications stop by default.

## F. Reward Psychology (the craft, honestly applied)

- **GAM-18 (M, P1) — The reveal moment.** Score reveals are staged (sub-scores animate in sequence, biggest lever last) — the variable-reward moment engineered around *information*, not chance. AC: reveal ≤1s to start (NFR-14); full decomposition skippable by one tap for repeat users.
- **GAM-19 (S, P2) — Near-miss and next-step framing.** "2 points from clearing this chapter — one more session like today's does it" — always true (computed from actual mastery state), never fabricated. AC: any near-miss message must be backed by the real number; fabricated proximity is a defect.
- **GAM-20 (S, P2) — Comeback mechanics.** Returning after ≥7 dark days triggers a "comeback arc": reduced-friction 3-day quest line rebuilding from a fresh mini-diagnostic. AC: comeback arc completion restores full quest difficulty.

## G. Ethical Guardrails (structural — what makes this addictive-but-honest)

These are requirements, not values statements. Each is testable.

- **GAM-21 (M, P1)** — No monetization of anxiety: streak restoration, freezes, and repairs are never purchasable; no in-app currency purchasable with money. (Build-time: no payment hooks exist in the gamification service.)
- **GAM-22 (M, P1)** — Private by default: every individual metric (streak, XP, scores, percentile) is visible only to the student unless they opt in per-surface; tenant staff see mastery and participation, not vanity metrics.
- **GAM-23 (M, P1)** — Effort cannot fake mastery: level/XP and Gap Meter are separated (GAM-03); readiness reporting to tenants uses mastery only.
- **GAM-24 (M, P1)** — Notification restraint: hard caps + quiet hours + drive-week suppression (NOTIF-05); the mute is one tap and permanent.
- **GAM-25 (M, P1)** — Real deadlines only: the only countdowns in the product are the student's actual drive date and real quest windows (NFR-16).
- **GAM-26 (S, P2)** — Wellbeing telemetry: sessions >90 min/day or 2am–5am usage patterns generate a gentle in-app check-in ("rest is training too") and never a reward. AC: the check-in has no dismissal penalty.

---

# PART IV — TRACEABILITY & PHASING

## Phase mapping (delta view — gamification lands early by design)

| Phase | Adds (v1.0 items) |
|---|---|
| **P1 — Core MVP** | GAM-01…05, 08, 15, 18, 21…25 (quest/XP/streak/chapters/badges + all structural guardrails) · QUIZ-01, 03, 06 · ENG-22 · PLAT-17 · TEN-13 · NOTIF-05 · NFR-14…16 |
| **P2 — Depth** | GAM-06, 09…12, 14, 16, 19, 20, 26 · QUIZ-02, 04, 05 · ENG-23 · PLAT-18 · TEN-14 · TRN-06 · RPT-05 |
| **P3 — Moat** | GAM-13, 17 (duo drills, graduation) + previously phased P3 items (intelligibility model, adaptive selection, calibrated prediction, AI interview partner, drive-day rehearsal at scale) |

Rationale for P1 placement: the habit engine is not polish — for this population it is the difference between a diagnosis that sits unused and 12–18 targeted hours actually happening. The guardrails (GAM-21…25) ship in P1 *because* the engagement mechanics do; they are the same feature.

## Document map

| Document | Role after this baseline |
|---|---|
| `Documentation/BRD_FRS_v1.0.md` (this file) | **Single source of truth** — BRD + FRS + gamification design |
| `Documentation/CommunicationIQ_BRD.docx` | v0.1 historical draft (superseded, keep for reference) |
| `FEATURES.md` | Build checklist — to be updated with GAM/QUIZ items |
| `SIMULATOR_FEATURES.md` | Simulator deep-dive (SIM/DIAG/TRAIN detail) — still current |
| `PREREQUISITES.md` | Pre-build checklist — still current |
| `Documentation/knowledge.md` | Model inventory + vendor test formats — engine ground truth |

## Open items for next revision

1. Named XP values and multiplier table (needs one balancing workshop; ship configurable defaults).
2. League size/tier structure tuning after first pilot cohort data.
3. Quest content templates per task type (content team, ~30 templates for P1).
4. Whether Boss Mock frequency is weekly or biweekly for cohorts starting <45 days from drive day.
5. Localized (Telugu/Hindi/Tamil) copy for all reward/coaching moments — tone review by a native-speaker writer, not machine translation alone.

— End of Baseline v1.0 —

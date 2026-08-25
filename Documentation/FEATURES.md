# Communication IQ — Feature List

Derived from `CommunicationIQ_BRD.docx` (v0.1). Grouped by module, phase-tagged per the BRD's release plan (Section 14), with the originating requirement ID kept for traceability back to the BRD. Use the checkboxes to track build status as this project moves forward.

Phases: **P1** = Core MVP · **P2** = Depth · **P3** = Moat (see BRD Section 14 for full phase definitions)

---

## 1. Platform Admin (Operator Console)

- [ ] **PLAT-01** — Create, activate, suspend, and offboard tenant institutions, with scheduled data export/deletion on offboarding. *(P1)*
- [ ] **PLAT-02** — Configure tenant settings: plan, feature flags, branding, seat limits, placement-season calendar. *(P1)*
- [ ] **PLAT-03** — Define and version pricing plan templates (per-seat, per-institution flat, usage-based, freemium/pilot). *(P1)*
- [ ] **PLAT-04** — Assign/override plans per tenant, including negotiated pricing and scheduled future changes. *(P1)*
- [ ] **PLAT-05** — Auto-generate GST-compliant invoices each billing cycle. *(P1)*
- [ ] **PLAT-06** — Renewal tracking, dunning notices, grace periods. *(P2)*
- [ ] **PLAT-07** — Central Provider Registry: every pluggable AI/payment/notification capability and its registered providers. *(P1)*
- [ ] **PLAT-08** — Set active + fallback provider per capability, globally or per tenant, via config (no deploy). *(P1)*
- [ ] **PLAT-09** — Shadow-mode evaluation: run a new provider silently, compare against production before promotion. *(P2)*
- [ ] **PLAT-10** — Canary routing: split live traffic by percentage across two providers for the same capability. *(P2)*
- [ ] **PLAT-11** — Manage the global simulation content library; publish/restrict profiles per tenant. *(P1)*
- [ ] **PLAT-12** — Cross-tenant analytics: adoption, usage, revenue, plan mix, aggregate outcome trends. *(P2)*
- [ ] **PLAT-13** — Provider performance dashboards: accuracy, latency, error rate, cost per call. *(P1)*
- [ ] **PLAT-14** — Immutable audit log of all admin actions (actor, timestamp, before/after). *(P1)*
- [ ] **PLAT-15** — Internal support/ticketing queue with SLA tracking. *(P2)*
- [ ] **PLAT-16** — Role-scoped internal staff accounts (Super Admin, Finance, Content, Data/ML, Support) with mandatory MFA. *(P1)*

## 2. Tenant Admin (Institution Console)

- [ ] **TEN-01** — Guided onboarding: institution profile, branches, academic year, placement-season dates. *(P1)*
- [ ] **TEN-02** — Branding: logo, color theme, custom subdomain on eligible plans. *(P2)*
- [ ] **TEN-03** — Bulk import students/staff via CSV/Excel or SSO directory sync, with validation and error reporting. *(P1)*
- [ ] **TEN-04** — Role assignment and activation/deactivation within the tenant. *(P1)*
- [ ] **TEN-05** — Cohort/batch creation (branch/year/section) with trainer assignment. *(P1)*
- [ ] **TEN-06** — Assign simulation profiles/task types to a cohort, with deadlines and mandatory/optional flags. *(P1)*
- [ ] **TEN-07** — Cohort readiness dashboard: assessed / placement-ready / needs training / high-risk. *(P1)*
- [ ] **TEN-08** — Drill-down from cohort dashboard into individual student diagnostic reports. *(P2)*
- [ ] **TEN-09** — Seat usage view vs. plan limit, with upgrade/downgrade requests. *(P1)*
- [ ] **TEN-10** — Export cohort reports (CSV/PDF); push summary data to the institution's placement portal/LMS. *(P2)*
- [ ] **TEN-11** — Broadcast announcements and deadline reminders to a cohort. *(P2)*
- [ ] **TEN-12** — Hard tenant data isolation — no cross-tenant visibility under any configuration. *(P1, non-negotiable)*

## 3. Trainer / Staff

- [ ] **TRN-01** — View diagnostic reports for students in assigned cohort(s) only. *(P1)*
- [ ] **TRN-02** — Assign targeted drills beyond the system's auto-recommendations. *(P2)*
- [ ] **TRN-03** — Flag at-risk students with staff-visible notes. *(P2)*
- [ ] **TRN-04** — Track whether a flagged intervention correlated with a later score change. *(P3)*
- [ ] **TRN-05** — Read/assign-only access — trainers cannot alter a recorded score or attempt history. *(P1)*

## 4. Student App

- [ ] **STU-01** — Registration via tenant invite, tenant-permitted self-signup, or SSO. *(P1)*
- [ ] **STU-02** — Consent screen (what's recorded, retention, purpose) before first recording. *(P1)*
- [ ] **STU-03** — Baseline diagnostic simulation before any training is assigned. *(P1)*
- [ ] **STU-04** — Configurable task types: Read Aloud, Repeat Sentence, Sentence Build, Short Answer Q&A, Story Retell, Open Response. *(P1: 2–3 types · P2: all 6)*
- [ ] **STU-05** — Full format fidelity per profile: timed countdown, one-shot audio (no replay), section pacing. *(P1)*
- [ ] **STU-06** — Streaming mic capture — no manual save/upload step. *(P1)*
- [ ] **STU-07** — Result screen with plain-language sub-scores + one "biggest lever" recommendation, within the latency budget. *(P1)*
- [ ] **STU-08** — Personalized drill loop: fail → why → similar-item drill → harder challenge → re-test. *(P1)*
- [ ] **STU-09** — Re-simulation with plan-governed attempt allowance; mastery tracked across attempts. *(P1)*
- [ ] **STU-10** — Personal progress dashboard: mastery over time, attempt history, readiness estimate with confidence range. *(P2)*
- [ ] **STU-11** — Configurable reminders/nudges for deadlines and streaks. *(P2)*
- [ ] **STU-12** — Self-service data export/deletion request. *(P1)*
- [ ] **STU-13** — Graceful degradation on low-bandwidth connections and budget Android devices. *(P1, hard requirement)*
- [ ] **STU-14** — Strict tenant + role data visibility boundaries. *(P1)*

## 5. Core Assessment Engine (Own-Build)

**Layer 1 — Hearing**
- [ ] **ENG-01** — Speech-to-text transcription with word-level timestamps. *(P1)*
- [ ] **ENG-02** — Voice activity detection → pause/response-latency features. *(P1)*
- [ ] **ENG-03** — Forced alignment (word/phoneme timestamps). *(P1)*

**Layer 2 — Speech Quality**
- [ ] **ENG-04** — Phoneme-level pronunciation accuracy scoring. *(P1)*
- [ ] **ENG-05** — Fluency/prosody scoring — interpretable, feature-based model. *(P1)*
- [ ] **ENG-06** — Disfluency detection (fillers, repetitions, self-corrections). *(P1)*
- [ ] **ENG-07** — Intelligibility scoring, trained on Indian-L1 human ratings — **the core differentiator.** *(P3, gated on ENG-09 data)*
- [ ] **ENG-08** — L1/accent classification for routed feedback and difficulty stats. *(P2)*
- [ ] **ENG-09** — Human-rater labelling program (onboarding, inter-rater agreement, training pipeline). *(P1 — start immediately, longest lead time in the project)*

**Layer 3 — Content**
- [ ] **ENG-10** — Grammar error detection and typing. *(P1)*
- [ ] **ENG-11** — Content relevance/recall scoring for retell tasks (rubric-constrained, never sole LLM judgment). *(P1)*

**Layer 4 — Intelligence**
- [ ] **ENG-12** — Item calibration (IRT: difficulty + discrimination, L1-split). *(P2)*
- [ ] **ENG-13** — Per-skill mastery tracking (Bayesian Knowledge Tracing). *(P2)*
- [ ] **ENG-14** — Adaptive item selection from calibrated item information. *(P3)*
- [ ] **ENG-15** — Calibrated outcome/readiness prediction — only once the minimum paired-record gate is met. *(P3, gated)*

**Provider Abstraction (cross-cutting — applies to every capability above)**
- [ ] **ENG-16** — Every capability behind a versioned Provider Contract. *(P1)*
- [ ] **ENG-17** — New providers addable by registration, zero change to consuming modules. *(P1)*
- [ ] **ENG-18** — Provider selection as runtime config, global or per-tenant. *(P1)*
- [ ] **ENG-19** — Automatic fallback to a secondary provider on failure/timeout. *(P1)*
- [ ] **ENG-20** — Side-by-side shadow-mode comparison before promotion. *(P2)*
- [ ] **ENG-21** — Every score traceable to the exact provider + version that produced it. *(P1)*

## 6. Simulation Profile & Content Management

- [ ] **CONTENT-01** — Item authoring/import with metadata (task type, difficulty, discrimination, L1 group, source). *(P1)*
- [ ] **CONTENT-02** — No-code vendor-style profile builder (task sequence, timing, scoring weights). *(P1)*
- [ ] **CONTENT-03** — Versioned item bank and profiles, with rollback. *(P1)*
- [ ] **CONTENT-04** — Guardrail blocking verbatim proprietary vendor item import — "-style" only, by design. *(P1)*
- [ ] **CONTENT-05** — End-to-end profile preview before publishing. *(P2)*
- [ ] **CONTENT-06** — Staged rollout to pilot tenants before global publish. *(P2)*

## 7. Notifications & Communication

- [ ] **NOTIF-01** — Pluggable channel providers (email, SMS, WhatsApp, push) — same abstraction pattern as the engine. *(P1)*
- [ ] **NOTIF-02** — Per-tenant, per-notification-type channel configuration. *(P1)*
- [ ] **NOTIF-03** — Templated, localizable notification content. *(P2)*
- [ ] **NOTIF-04** — Stored, respected channel opt-in/opt-out as part of consent record. *(P1)*

## 8. Payments & Billing

- [ ] **BILL-01** — Pluggable payment gateway — Razorpay Day-1, PayU/Stripe-ready contract. *(P1)*
- [ ] **BILL-02** — Fixed per-seat, per-institution flat, and usage-based billing models. *(P1)*
- [ ] **BILL-03** — Free trial/pilot period with auto-convert or graceful downgrade. *(P1)*
- [ ] **BILL-04** — Automated GST-compliant invoicing. *(P1)*
- [ ] **BILL-05** — Mid-cycle upgrade/downgrade proration. *(P2)*
- [ ] **BILL-06** — Dunning workflow for failed payments. *(P2)*
- [ ] **BILL-07** — Coupon/discount codes and custom pricing overrides. *(P3)*
- [ ] **BILL-08** — No raw payment credential storage — gateway-handled PCI compliance only. *(P1)*

## 9. Reporting & Analytics

- [ ] **RPT-01** — Three reporting tiers: platform / tenant / individual, role-gated. *(P1)*
- [ ] **RPT-02** — Exportable, schedulable reports (CSV/PDF). *(P2)*
- [ ] **RPT-03** — Closed-loop outcome report: simulation score → real assessment → interview → placement. *(P2, deepens in P3)*
- [ ] **RPT-04** — All analytics respect tenant isolation and consent scope. *(P1)*

## 10. Integrations

- [ ] **INT-01** — SSO via Google Workspace / Microsoft. *(P2)*
- [ ] **INT-02** — Export API/webhook to institution placement portal/LMS. *(P2)*
- [ ] **INT-03** — Documented public API for future third-party integrations. *(P3)*
- [ ] **INT-04** — Consent + audit logging on any data leaving the platform. *(P1)*

---

## Phase Summary

| Phase | What ships |
|---|---|
| **P1 — Core MVP** | Tenant CRUD + basic billing · onboarding, cohorts, assignment · student app on 2–3 task types · own-build ASR/VAD/feature-based fluency · Provider Abstraction Layer live from day one · DPDP consent flow · hard tenant isolation |
| **P2 — Depth** | All 6 task types · IRT + BKT · tenant branding/SSO · cross-tenant analytics · shadow-mode/canary tooling · multi-channel notifications |
| **P3 — Moat** | Intelligibility model (ENG-07) · adaptive item selection · calibrated outcome prediction (ENG-15) · third-party provider adapters activated where useful · provider marketplace · mobile app |

Full requirement text, priorities, non-functional requirements, RBAC matrix, data model, and risks are in `Documentation/CommunicationIQ_BRD.docx`.

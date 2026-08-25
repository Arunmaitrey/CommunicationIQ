# CommunicationIQ — Implementation Plan v1

Source of truth for requirements: `Documentation/BRD_FRS_v1.0.md` (+ `FEATURES.md`,
`SIMULATOR_FEATURES.md`, `PREREQUISITES.md`, `Documentation/knowledge.md`).
This document covers *how* we build it, not *what* it must do.

---

## 0. Locked decisions

| Decision | Choice |
|---|---|
| Stack | Next.js 14 (App Router, TS, Tailwind) · FastAPI (async) · PostgreSQL · Alembic |
| Multi-tenancy | Schema-per-tenant on one Postgres — `public` control plane + `tenant_<slug>` |
| Themes | All 16 QSprint themes ported verbatim, token-driven |
| File/audio storage | Local `tmp/` for now, behind a `Storage` provider contract |
| M1 scope | Student simulation vertical slice (consent → mic check → attempt → score → result) |
| Engine day-1 | Tier 0 heuristics; Tier 1 local open models at M2, same contracts |
| Auth & data | Real JWT + RBAC from M0, plus a seeded demo tenant |

## 1. Reuse from QSprint (`C:\Projects\QuadrantITServices\QSprint`)

| Donor file | What we take |
|---|---|
| `frontend/app/globals.css` | All 16 theme token blocks (`[data-theme=...]`) |
| `frontend/components/ThemeProvider.tsx` | Theme context, grouped picker, per-account persistence |
| `frontend/tailwind.config.ts` | CSS-variable colour contract — no component hardcodes a colour |
| `frontend/components/ui.tsx` | PageHeader, Card, Section, StatCard, EmptyState, Badge, Table, Progress, Avatar, Tabs, Modal |
| `frontend/components/shell/*` | AppShell, SideNav, MobileNav, UserMenu, SearchBox, NotificationsMenu |
| `frontend/lib/api.ts` | API client shape: single entry point, snake→camel mapping, token + session-expiry handling |
| `backend/app/db.py` | Two declarative bases, `schema_translate_map`, fail-closed tenant session factory |
| `backend/app/config.py` | pydantic-settings pattern |

### The 16 themes

- **Professional** — Ocean Blue (default), Royal Blue, Quadrant Light, Enterprise SaaS, Minimal, Gold
- **Dark** — Quadrant Dark, Midnight Console, Dark AI Console, AI Futurism, Luxury Enterprise, Cyberpunk
- **Expressive** — Material 3, Bento UI, Glassmorphism, Liquid Glass

Token contract every new component must obey:
`--bg --surface --surface-2 --text --muted --border --primary --secondary --accent --success --warning --error --radius --shadow --font`

### Built new (no QSprint equivalent)

- Test runner surface: full-screen, no navigation, countdown, beep-to-speak, waveform, mic states, one-shot enforcement
- Diagnostic report: staged sub-score reveal, annotated listen-back with synced transcript, pause visualisation
- Game surfaces: quest card, gap meter vs. level bar, streak, badges, season map

## 2. Repository layout

```
CommunicationIQ/
├─ frontend/                     Next.js 14 · port 3010
│  ├─ app/(app)/...              role-gated routes under one AppShell
│  ├─ app/attempt/[id]/run/      full-screen runner, deliberately outside (app)
│  ├─ components/                ui.tsx, shell/, ThemeProvider, audio/, game/
│  └─ lib/                       api.ts, roles.ts, nav.ts, audio.ts
├─ backend/                      FastAPI · port 8010
│  └─ app/
│     ├─ models/                 platform.py, tenant.py
│     ├─ routers/                auth, student, trainer, tenant_admin, platform_admin, engine, webhooks
│     ├─ engine/
│     │  ├─ contracts/           Protocols — written BEFORE any implementation
│     │  ├─ providers/tier0/     heuristic implementations
│     │  ├─ providers/tier1/     faster-whisper, silero-vad, whisperx, wav2vec2-GOP
│     │  ├─ registry.py          resolve(capability, tenant) → provider + fallback
│     │  └─ pipeline.py          orchestration + latency instrumentation
│     ├─ gamification/           XP ledger, quests, streaks, seasons (server-authoritative)
│     └─ storage/                LocalTempStorage (now) · S3Storage (later)
├─ tmp/                          gitignored
│  ├─ recordings/<tenant>/<attempt>/<response>.webm
│  ├─ prompts/
│  └─ exports/
└─ Documentation/                existing, untouched
```

## 3. Provider Abstraction Layer — the day-one rule

No capability is consumed except through a versioned contract (ENG-16…21, PLAT-07/08).

Contracts: `ASR · VAD · ForcedAlignment · Pronunciation · Fluency · Disfluency · Grammar · ContentRelevance · TTS · Storage · Notification · Payment`

- **Tier 0** (M1): heuristic — energy-based VAD, duration/pause/rate features, deterministic
  pseudo-scores derived from the real audio. No GPU, no API keys, whole product demoable.
- **Tier 1** (M2, shipped): faster-whisper with word timestamps, Silero VAD,
  reference-match word accuracy, transcript-based disfluency detection. Runs
  locally on CPU; Tier 0 is the configured fallback for VAD, so a host without
  the model still measures timing and pause structure.
  Still outstanding at Tier 1: wav2vec2 GOP pronunciation, a grammar-error
  model, and content/retell scoring.
- **Tier 2** (later): vendor APIs, promoted only after shadow-mode comparison.

Rules: provider selection is a config row (global or per-tenant), never a deploy · automatic
fallback on failure/timeout · every `ScoreRecord` stamps provider id + version.

## 4. Data model (first cut)

**public** — `Tenant, Plan, Subscription, Invoice, PlatformUser, ProviderRegistry,
ProviderConfig, ModelVersion, AuditLog, FeatureFlag, GamificationConfig`

**tenant_&lt;slug&gt;** — `User, Cohort, CohortMember, ConsentRecord, SimulationProfile,
ProfileSection, TaskItem, QuizItem, Assignment, Attempt, Response, ResponseAudio,
ScoreRecord, FeatureRecord, SkillMastery, Drill, MistakeBankEntry, XPLedger,
StreakState, Quest, SeasonPlan, Badge, League, EngagementEvent, NotificationLog, Flag`

`ResponseAudio` holds a storage *key*, never a filesystem path.

## 5. Route map

| Role | Routes |
|---|---|
| Student | `/home` `/simulate` `/attempt/[id]/check` `/attempt/[id]/run` `/results/[id]` `/drills` `/quiz` `/progress` `/mistakes` `/season` |
| Trainer | `/cohorts` `/cohorts/[id]` `/students/[id]` `/flags` |
| Tenant Admin | `/tenant/setup` `/tenant/users` `/tenant/cohorts` `/tenant/assignments` `/tenant/readiness` `/tenant/season` `/tenant/branding` `/tenant/seats` |
| Platform | `/platform/tenants` `/plans` `/billing` `/providers` `/content` `/gamification` `/analytics` `/audit` `/staff` |

## 6. Milestones

| # | Deliverable | Demoable outcome |
|---|---|---|
| M0 ✅ | Scaffold · 16 themes · AppShell + role nav · Postgres/Alembic/tenant schemas · JWT+RBAC · seed demo tenant · CI cross-tenant isolation tests · provider contracts (no impls) | Four roles log in, all 16 themes switch, seeded data visible |
| M1 ✅ | Consent → mic check → Read Aloud + Repeat Sentence timed attempt → capture to `tmp/` → Tier-0 engine → result screen with sub-scores + biggest lever | A student completes a real timed simulation and gets a real diagnosis |
| M2 ✅ | Tier-1 engine (faster-whisper + Silero) · word accuracy · hesitation detection · annotated listen-back (DIAG-02) · score-on-ingest | Scores become genuinely meaningful |
| M3 ✅ | Tenant plane: onboarding, CSV import with full validation, cohorts, assignments, readiness, trainer flags + momentum, seat limits | An institution can be onboarded and run a cohort |
| M4 ✅ | Gamification P1: append-only XP ledger, daily quest, streak + freezes, level vs. gap meter, badges, season plan, guardrails GAM-21…25 | The daily loop exists, honest by construction |
| M5 ✅ | Quiz engine (QUIZ-01/03/06) with the weekly cap, drill loop TRAIN-01, spaced-repetition mistake bank | Full P1 practice loop |
| M6 ✅ | Platform console writes: provider switching with fallback/shadow/canary validation, institution onboarding, versioned plans, GST invoicing, economy floors | Operator can run the business |

## 7. Non-negotiables enforced from M0

- Cross-tenant isolation tests in CI from the first table (TEN-12)
- Consent recorded before any recording is captured (STU-02, DPDP)
- Retention sweeper over `tmp/recordings` from day one
- XP ledger append-only and server-authoritative; client XP never trusted (NFR-15)
- No pay-to-restore-streak, no loot boxes, no public individual leaderboards, no fabricated
  countdowns — enforced by *not building* the mechanisms (NFR-16, GAM-21…25)
- Every score traceable to provider + version (ENG-21)

## 8. Known debt carried out of M1

- **Uploads are 16 kHz mono WAV** (~32 KB/s). Right for the engine, wrong for a
  hostel 3G connection (ACC-02/ACC-04). Fix: Opus upload with a decode at ingest,
  alongside the Tier-1 work.
- **Repeat Sentence prompts are spoken by the browser**, so the text is present in
  a network response a determined student could read. Acceptable in practice mode;
  pre-rendered prompt audio (SIM-06) closes it and is part of Tier 1, not polish.
- **Item selection is random**, not IRT-driven. Honest until items are calibrated —
  "at the edge of your ability" is not a claim we can make yet (ENG-12/14).
- **The engine has never been measured on real Indian-L1 speech.** Every accuracy
  figure so far comes from Windows TTS, which is the easy case. The 50–100
  recording evaluation set in PREREQUISITES §5 is the gate before any of these
  numbers should be quoted to an institution.

## 9. Still to build

**Engine (P2/P3):** per-phoneme detail — the confusion pairs DIAG-03 wants
need a phoneme-output acoustic model and a grapheme-to-phoneme front end;
today's GOP is character-level. Intelligibility (P3, gated on the human rater
programme — the actual moat). IRT calibration and adaptive selection. BKT
mastery, currently a running mean. L1 identification, currently self-declared.

**Product:** the remaining four task types, leagues and cohort challenges,
scheduled cohort mocks (OPS-01), notification delivery, LMS/SSO integration,
offline drill packs, Telugu/Hindi/Tamil localisation of the interface copy.

**Not planned:** accent-erasure coaching, verbatim vendor items,
guaranteed-score marketing, always-on proctoring of self-practice.

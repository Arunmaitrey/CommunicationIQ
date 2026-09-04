# CommunicationIQ — Last-Week Change Summary & New Exam Scheduling

> Covers the work landed on `main` between **28 Aug 2026 and 4 Sep 2026**
> plus the new platform **Exam Scheduling** system added on top.

---

## 1. What was added in the last week (by commit)

| Date | Commit | What landed |
|------|--------|-------------|
| 28 Aug | `61dc9b2`, `735c9d9`, `d7eb77a`, `c35b982`, `413a453` | Role-mismatch fix + removal of whisper/trainer/billing scaffolding; toast notifications on all actions; nav fixes; question-bank CRUD with audio upload; charts on the platform overview; tenant profiles page; detailed exam history with IP tracking, timing and reports; readiness leaderboard; writing review cards; footer; company filtering; cross-exam dedup; orphan cleanup |
| 27 Aug | `a0e3361`, `cd5ed21`, `711f24b`, `af268c9` | Beanie 1.30 compatibility (`alias='_id'` on all documents, operator handling, ObjectId coercion); docker-compose pointed at Atlas |
| 31 Aug | `b851b8e`, `0680dee` | Secret scrubbed from `.env.example`; **ExamSidebar + FullscreenGuard** added to the exam runner; server-side dedup for reading/listening/writing; quiz duplicate prevention |
| 1–2 Sep | `6105bea`, `3cee811`, `6a6a680`, `17b5d86`, `56893dd` | **Proctoring module**: full-screen guard, camera preview, face-not-detected / multiple-faces / looking-away / tab-switch detectors, violation strikes and warning UI |
| 3 Sep | `0b5dcdf`, `93f68d1` | Seed/debug/test scripts removed from the repo; **Exam Tests** engine (weightage + per-section timing), **Question Sets** (10-question sets auto-created), **Companies** with question counts, **Plans & Pricing** (4 seeded plans), **Exam Schedules** groundwork, platform pages for Messages, Email/SMTP, Email Templates, Payments, Contact, Plans; student Plans page for general users; subscription gating for general users; audit log |
| 4 Sep | `7093b48` | Removed duplicate code blocks and fixed JSX structure / imports in all practice pages (quiz, reading, writing, listening, attempt runner) |

### Platforms pages now live under `/platform/…`
`Dashboard` · `All Institutions` (tenants) · `Plans & Pricing` · `Question Bank` ·
`Question Sets` · `Exam Tests` · **`Exam Schedules` (new)** · `Companies` ·
`All Results` · `Reviews` · `Audit Log` · `Messages` · `Email / SMTP` ·
`Email Templates` · `Payments` · `Settings`

### Student pages now live under `/(app)/…`
`Today` (home) · `Practise` · `Take a test` · `My progress` · `Writing reviews` ·
`Plans` (general users only) · `Contact Us` · `Settings` ·
quiz / reading / listening / writing practice · `simulate` (exam library) ·
`results/[id]` (report + review card)

---

## 2. NEW — Exam Scheduling for Institutions (super admin)

Super admins can now run a real **institution drive**: pick one of the exam
tests configured under **Exam Tests** (which already carries the question
weightage and per-section timing), choose which institutions may sit it, open a
window, and cap attempts per student. Students of the targeted institutions see
the exam on their **Take a test** page only while the window is live, and the
backend enforces the window and the attempt cap.

### How it works (end to end)

1. **Super admin → Exam → Exam Schedules → “Schedule Exam”**
   - Choose an **Exam Test** (its weightage/timing is shown live in the form).
   - Choose **All institutions + general users**, or tick specific institutions.
   - Set **Opens at / Closes at** (any timezone — stored as UTC).
   - Set **attempts per student** (0 = unlimited, default 1).
2. Backend validates the test is active, the window is in the future, and any
   institution ids exist, then records an `exam_schedules` document and links it
   to the published `SimulationProfile` behind that exam test.
3. **Student → Take a test** fetches `/api/v1/student/exam-schedules`. Only
   schedules whose window is live/upcoming and whose audience includes the
   student's institution (or “everyone”) are returned, each with the test
   weightage/timing, window, attempts used and the startable profile id.
4. **Attempt start enforcement** (`POST /api/v1/student/attempts`): when the
   request carries `schedule_id`, the server refuses to start the attempt
   before the window opens, after it closes, for a non-targeted institution, or
   once the student has used their attempt allowance in the window.

### Data model (`exam_schedules` collection)

| Field | Meaning |
|-------|---------|
| `exam_test_id` | The ExamTest being scheduled (weightage + timing come from it) |
| `profile_id` | Published SimulationProfile that students actually start |
| `name` | Snapshot of the test name |
| `tenant_ids` | Targeted institutions; **empty = all institutions + general users** |
| `starts_at`, `ends_at` | Window during which students may sit the exam |
| `max_attempts` | Per-student attempt cap inside the window (0 = unlimited) |
| `is_active` | Admin can cancel a schedule without deleting it |
| `created_by`, `created_at`, `updated_at` | Who/when |

### API surface

| Method & path | Purpose |
|---------------|---------|
| `GET  /api/v1/platform/exam-schedules` | List schedules w/ test + institution names + status |
| `POST /api/v1/platform/exam-schedules` | Create a schedule |
| `PATCH /api/v1/platform/exam-schedules/{id}` | Update window / audience / cap / active |
| `DELETE /api/v1/platform/exam-schedules/{id}` | Delete (started attempts untouched) |
| `GET  /api/v1/student/exam-schedules` | Student-facing list scoped to their institution |

Schedule status shown in the console: `upcoming` · `live` · `ended` ·
`cancelled` (inactive before the window ends).

---

## 3. Live visibility — Activate / Deactivate for tests & companies

Every platform Exam Test and Company card now has an explicit **Activate /
Deactivate** action, and toggling updates the student side **immediately — no
backend restart**:

- **Exam Test → `is_active`**: the synced SimulationProfile that students
  actually start is set to `published` (active) or `retired` (inactive). The
  student Take-a-test / simulate pages list published profiles only, so a
  deactivated test disappears and an activated one appears on the next page
  load. Deleting a test also retires its profile (no orphaned published exam).
- **Company → `is_active`**: all SimulationProfiles + ExamTests carrying that
  company name are flipped the same way, and a renamed company retires objects
  still holding the old name. New companies are published on creation.
- Engine: `_sync_exam_test_profiles()` (startup + after every create/update)
  and `_sync_company_visibility()` keep profiles/tests in step with the flags;
  the frontends re-fetch after every toggle, so nothing caches stale state.

## 4. Verification notes

- Frontend `npx tsc --noEmit` — **0 errors**.
- Backend imports (`app.main` + all routers) and OpenAPI route registration —
  clean.
- Live smoke test against the database: resolved an active exam test → linked
  its published SimulationProfile → created a tenant-targeted schedule →
  audience filter returns it only for the targeted tenant → cleanup OK.
- Live visibility smoke tests: deactivating an ExamTest retired its profile
  (`published → retired`) and reactivating restored it; same round-trip
  verified for companies — both with a throwaway record cleaned up afterwards.
- The exam tests themselves also auto-sync into `simulation_profiles` at
  startup (`_sync_exam_test_profiles`), and a legacy backfill now stamps
  `profile_id` onto schedules created before this release.

### Results per schedule

Each schedule card in the Exam Schedules console now shows live results for its
window: **attempts started**, **distinct students**, and **average overall
score** (aggregated from `score_records` for that profile between `starts_at`
and `ends_at`). The schedule list endpoint returns this under `results`
(`started` / `students` / `average_score`).

### Schedule Activate / Deactivate

Each schedule card also has a one-click **Activate / Deactivate** button (no
form needed) — deactivating hides the scheduled exam from the student Take-a-
test page immediately; reactivating restores it. The same toggle lives in the
edit form. Deactivated or expired schedules never appear to students, and a
schedule whose underlying exam test has been deactivated is filtered out of the
student list as well.

---

## 5. Runtime cleanup — no auto-seeding, no full-DB export endpoint

- **Auto-seeding removed.** The backend no longer creates exam tests, plans or
tenants at startup. Content is created only by the platform admin through the
UI (Exam Tests, Plans, Companies pages) and persists in MongoDB — a restart
never re-seeds or duplicates anything. The one startup sync left in place
(`_sync_exam_test_profiles`) only *links* already-created ExamTests to their
student-facing SimulationProfile (and flips published/retired to match
`is_active`) — it never creates tests.
- **Full-DB JSON export endpoint deleted.** `GET /api/v1/platform/export-db`
(an unauthenticated dump of the whole control plane + every tenant database,
which previously produced stray `communicationiq_full_export.json` files) was
removed. The only remaining exports are the deliberate, audited ones:
`/platform/tenants/{id}/export.zip` (super-admin per-institution reports),
`/tenant/export-results`, and per-attempt report CSV — all behind their role
guards. `.gitignore` already blocks `*_export*.json` dumps from ever being
committed.
- Contact-message inbox endpoints were audited: list / submit / update /
reply all route correctly and the legacy `.sort("created_at", -1)` Beanie
crash in the messages list was replaced with a safe Python-side sort.

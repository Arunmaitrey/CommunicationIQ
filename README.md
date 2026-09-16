# CommunicationIQ

Communication assessment and training platform for placement readiness. AI-powered scoring of pronunciation, fluency, grammar, content, and listening comprehension. Multi-tenant SaaS with data isolation by `tenant_id` on MongoDB Atlas.

## Architecture

```
Frontend (Next.js 14)       Backend (FastAPI)           MongoDB Atlas
     |                           |                          |
  /login ──────────────────> /api/v1/auth/login            |
  /home ───────────────────> /api/v1/student/home           |
  /platform ───────────────> /api/v1/platform/*             |
     |                           |                          |
     └── API layer ────────> deps.py (auth) ─────────> MongoDB
                                 |                    Motor + Beanie
                             routers/                  |
                             gamification/             |
                             engine/                   |
                           ┌─────┴─────┐               |
                           │ db.py     │──────────────>│
                           │ Session   │   Beanie ODM  │
                           │ .find()   │──────────────>│
                           └───────────┘               |
                                                       |
                      ┌────────────────────────────────┤
                      │ CommunicationIQ (single DB)    │
                      │                                │
                      │  Control plane:                 │
                      │    tenants, platform_users,     │
                      │    provider_registry, audit     │
                      │                                │
                      │  Tenant data (tenant_id):      │
                      │    users, attempts, scores,     │
                      │    profiles, gamification       │
                      │                                │
                      │  Shared question bank:          │
                      │    reading_passages, writing_   │
                      │    prompts, listening_passages,  │
                      │    quiz_items, task_items       │
                      └────────────────────────────────┘
```

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14, React 18, TypeScript, Tailwind CSS |
| Backend | Python 3.14+, FastAPI, uvicorn |
| Database | MongoDB Atlas (Beanie ODM + Motor) |
| Auth | JWT (python-jose), bcrypt |
| Speech | faster-whisper + wav2vec2 (open source, local — no API keys) |
| Speech Scoring | faster-whisper + wav2vec2 (local, open source) |

## Quick Start

### Backend
```bash
cd backend
python -m venv .venv
.venv/Scripts/activate  # Windows
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8010
```

> **Speech scoring**: real transcription/pronunciation scoring uses the
> open-source engine (`torch`, `faster-whisper`, `transformers`) — all included
> in `requirements.txt`, no API keys. Without those packages installed the API
> still runs and every other feature works; speech dimensions report as not
> measured.

### Frontend
```bash
cd frontend
npm install
npm run dev  # Runs on port 3010
```

### Environment Variables

Copy `backend/.env.example` to `backend/.env` and configure:

| Variable | Description |
|----------|-------------|
| `MONGO_URI` | MongoDB Atlas connection string |
| `JWT_SECRET` | Secret for signing JWT tokens |
| `APP_URL` | Frontend URL (default: http://localhost:3010) |
| `CORS_ORIGINS` | Comma-separated allowed origins |
| `WHISPER_MODEL` | Speech model: `small.en` (default) |

## Login Credentials

All passwords: `Password123!`

### Platform Super Admin

| Email | Password | Role |
|-------|----------|------|
| admin@saashx.ai | Password123! | super_admin |
| super@platform.com | Password123! | super_admin |
| superadmin@fluenzee.com | Password123! | super_admin |

### St. Mary's Engineering College (stmarys.edu)

| Email | Password | Role |
|-------|----------|------|
| admin@stmarys.edu | Password123! | tenant_admin |
| aarav.reddy@stmarys.edu | Password123! | student |
| priya.sharma@stmarys.edu | Password123! | student |
| rahul.verma@stmarys.edu | Password123! | student |
| meera.patel@stmarys.edu | Password123! | student |

### Vignan's Institute of Engineering (vignan.ac.in)

| Email | Password | Role |
|-------|----------|------|
| admin@vignan.ac.in | Password123! | tenant_admin |
| ananya.nair@vignan.ac.in | Password123! | student |
| vikram.singh@vignan.ac.in | Password123! | student |
| deepa.reddy@vignan.ac.in | Password123! | student |

### Login & Account Creation

- Login routes via the user directory — the account decides the institution,
  never the email domain.
- Self-registration always creates a **general** practice account; institution
  students are created by their tenant admin (People → add/import) with a
  temporary password.
- Platform admins log in with the seeded super-admin accounts below.

### Email (system-triggered)

Emails are sent automatically on real events — there is no manual send button
and no admin template editor:
- **Student created** by a tenant admin → welcome email with the temporary
  password.
- **First login** → welcome email.
- (Report-ready / password-reset templates are built in and fire with the
  same pipeline.)

Sending uses the SMTP configuration saved under Platform → Email / SMTP
(`smtp_configs` collection; tenant-specific row preferred, platform row
fallback). Until SMTP is configured, sends report `False` gracefully — the
platform never fails on email.

## Database

### Architecture
- **Single database**: All data lives in `CommunicationIQ` on MongoDB Atlas
- **Tenant isolation**: Every document carries `tenant_id`; queries always filter by it
- **Question bank**: Shared across all institutions (reading, writing, listening, quiz, task items)
- **Control plane**: Tenants, platform users, provider registry, audit log

### Current Data (MongoDB Atlas)

| Collection | Count | Description |
|-----------|-------|-------------|
| tenants | 2 | stmarys, vignan |
| platform_users | 3 | Super admins |
| users | 10 | 2 admins + 8 students |
| simulation_profiles | 18 | Base + VERSANT + company rounds + exam tests |
| profile_sections | 100+ | 4-6 sections per profile |
| reading_passages | 752 | General + company-specific |
| writing_prompts | 591 | General + company-specific |
| listening_passages | 881 | General + company-specific |
| quiz_items | 3423 | Grammar, vocabulary, reading, listening |
| task_items | 929 | Speaking tasks (6 types) |
| question_sets | 3745 | Sets of 10 questions per module |
| exam_tests | 5 | Baseline, Professional, SVAR, SpeechX, Versant |
| exam_reviews | 16 | Student exam feedback |

### Question Categories

| Category | Items | Used In |
|----------|-------|---------|
| Reading Comprehension | 34 | Reading practice + exams |
| Audio Comprehension | 27 | Listening practice + exams |
| Grammar | 15 | Quiz practice |
| Vocabulary | 15 | Quiz practice |
| Read Aloud | 15 | Speaking sections |
| Repeat Sentence | 15 | Speaking sections |
| Short Answer | 15 | Speaking sections |
| Sentence Build | 15 | Speaking sections |
| Story Retell | 15 | Speaking sections |
| Open Response | 15 | Speaking sections |
| Writing Prompts | 15 | Writing practice + exams |
| Reading Passages | 6 | Reading practice (4 general + 2 company) |
| Listening Passages | 4 | Listening practice (general) |

## Features

### Exam System (LSRW + Grammar/Vocabulary)
- **Listening** — Audio played once, comprehension MCQs
- **Speaking** — Read Aloud, Repeat Sentence, Short Answer, Open Response, Story Retell, Sentence Build
- **Reading** — Timed passages with comprehension MCQs
- **Writing** — Essay and email prompts with scoring
- **Grammar** — Multiple-choice grammar exercises
- **Vocabulary** — Context-based vocabulary questions

### Company-Specific Rounds
- Accenture-style Communication Round
- TCS-family Communication Practice
- (More can be added via Platform Admin → Question Bank)

### Exam Flow
1. Student selects a test from the library
2. Microphone check (environment validation)
3. Timed assessment with one-shot audio prompts
4. Automatic scoring (open-source speech engine, deterministic rules)
5. Detailed results with diagnosis and recommendations
6. AI-generated explanation (optional)

### Anti-Proctoring
- Right-click, copy/paste, screenshot shortcuts disabled
- Text selection blocked during exams
- Browser navigation warning (beforeunload)
- Tab switching detection (visibilitychange + ProctorCamera)
- Fullscreen enforcement (exit counts as violation)
- Face detection via MediaPipe (multiple faces, looking away, mobile phone)
- Clipboard guard (copy/cut/paste blocked)
- Strike system with auto-submit after threshold
- Presence monitoring with "Still there?" pause overlay

### Question Bank (Platform Admin)
- Full CRUD for: Reading, Writing, Listening, Speaking, Grammar, Vocabulary
- Edit/delete individual questions from the bank
- Bulk upload via CSV, Excel, JSON, ZIP (with audio files)
- Company-specific questions
- Questions shared across all institutions
- Set management: create, activate, deactivate, delete sets
- Each set contains exactly 10 questions with no duplicates across active sets

### Student Features
- Home dashboard with next action, streak, skill progress
- Practice sessions (speaking, listening, reading, writing) with fullscreen prompt
- Grammar & vocabulary quizzes with auto-start
- Attempt history and detailed results
- Profile editing (name, roll number, branch, year)
- 17 theme options
- Writing submissions and scores
- Connectivity monitoring during exams

### Institution Admin Features
- User management (create, edit, deactivate, password reset)
- Cohort management with drive dates
- Assessment profile builder (create, clone, publish, retire)
- Student readiness overview
- Exam results tracking
- Invitation system for external candidates

### Platform Admin Features
- Multi-tenant overview (seats, activity, providers)
- Institution management (create, configure, suspend)
- Provider registry and capability configuration
- Audit log viewer
- Gamification configuration
- Database export

### Gamification
- XP system with daily streaks
- Badge earning and display
- Daily quests based on weakest skills

## API Endpoints

### Auth
- `POST /api/v1/auth/login` — Sign in (email + password)
- `POST /api/v1/auth/signup` — Student self-registration
- `GET /api/v1/auth/me` — Current session user
- `POST /api/v1/auth/change-password` — Change password
- `POST /api/v1/auth/preferences` — Save preferences

### Student
- `GET /api/v1/student/home` — Dashboard data
- `GET /api/v1/student/profiles` — Available assessments
- `GET /api/v1/student/attempts` — My attempts
- `GET /api/v1/student/exam-schedules` — Exams scheduled for my institution
- `GET /api/v1/student/leaderboard` — Student rankings (institution / global)
- `GET /api/v1/notifications` — In-app notifications (role-scoped feed)
- `POST /api/v1/student/consent` — Give recording consent

### Attempts
- `POST /api/v1/student/attempts` — Start attempt
- `GET /api/v1/student/attempts/{id}/runner` — Get runner payload (starts the sitting)
- `POST /api/v1/student/attempts/{id}/responses/{rid}/prompt` — Play prompt
- `POST /api/v1/student/attempts/{id}/responses/{rid}/audio` — Upload recording
- `POST /api/v1/student/attempts/{id}/responses/{rid}/answer` — Submit answer
- `POST /api/v1/student/attempts/{id}/responses/{rid}/skip` — Skip item
- `POST /api/v1/student/attempts/{id}/submit` — Submit attempt
- `GET /api/v1/student/attempts/{id}/result` — Get results

### Institution Admin
- `GET /api/v1/tenant/overview` — Institution overview
- `GET /api/v1/tenant/users` — List users
- `GET /api/v1/tenant/cohorts` — List cohorts
- `GET /api/v1/tenant/profiles` — List assessment profiles
- `POST /api/v1/tenant/profiles` — Create profile
- `PUT /api/v1/tenant/profiles/{id}` — Update profile

### Platform Admin
- `GET /api/v1/platform/overview` — Platform overview
- `GET /api/v1/platform/tenants` — List institutions
- `GET /api/v1/platform/questions/items` — Question bank
- `POST /api/v1/platform/questions/{category}` — Create question
- `DELETE /api/v1/platform/questions/{collection}/{id}` — Delete question
- `GET /api/v1/platform/exam-tests` — List exam tests
- `POST /api/v1/platform/exam-tests` — Create an exam test
- `GET /api/v1/platform/exam-schedules` — List scheduled exams
- `POST /api/v1/platform/exam-schedules` — Schedule an exam for institutions
- `PATCH /api/v1/platform/exam-schedules/{id}` — Update a schedule
- `DELETE /api/v1/platform/exam-schedules/{id}` — Delete a schedule
- `GET /api/v1/platform/audit` — Audit log

### Practice
- `GET /api/v1/practice/quiz/next` — Next quiz items
- `POST /api/v1/practice/quiz/submit` — Submit quiz answers
- `GET /api/v1/practice/mistakes` — Review mistakes
- `GET /api/v1/practice/skills` — Skills overview

## Project Structure

```
CommunicationIQ/
  backend/
    app/
      main.py              # FastAPI app + lifespan
      config.py            # Settings from env
      db.py                # MongoDB data layer (Beanie + Session bridge)
      deps.py              # Auth dependencies
      security.py          # JWT + password hashing
      audit.py             # Audit logging
      provisioning.py      # Institution management
      set_engine.py        # Set management (create, activate, assign)
      practice_engine.py   # Practice set rotation
      question_importer.py # CSV/Excel/JSON import
      tts.py               # Text-to-speech synthesis
      models/
        _common.py         # StrId type
        platform.py        # Control-plane document models
        tenant.py          # Institution document models (with tenant_id)
      routers/             # API route handlers
        auth.py            # Login, signup, session
        student.py         # Student home, profiles, attempts
        attempts.py        # Assessment lifecycle
        tenant_admin.py    # Institution overview, users, profiles
        tenant_writes.py   # User/cohort/profile CRUD
        platform_admin.py  # Platform console, questions, sets, audit
        platform_writes.py # Tenant/provider management, exam tests
        admin.py           # Cohort readiness, student results
        game.py            # Gamification state
        practice.py        # Quiz, drills, mistakes, speaking sets
        listening.py       # Listening practice
        reading.py         # Reading practice
        writing.py         # Writing practice
        invitations.py     # External candidate invitations
        report.py          # HTML report generation
      gamification/        # XP, quests, streaks, badges
      engine/              # Speech scoring engine (open source)
      prompt_audio/        # Pre-rendered TTS audio cache (149 files)
      assets/audio/        # Uploaded audio for listening/speaking
      storage/             # File storage abstraction
    validation_baselines/  # Scoring validation baselines
    requirements.txt
    .env.example
  frontend/
    app/
      (app)/               # Authenticated pages
        home/              # Student dashboard
        tests/             # Assessment library
        practise/          # Practice sessions
        results/           # Attempt results
        my-progress/       # Student progress
        settings/          # Account settings
        platform/          # Platform admin (13 pages)
        tenant/            # Institution admin (7 pages)
        quiz/              # Grammar/vocabulary quiz
        reading/           # Reading practice
        listening/         # Listening practice
        writing/           # Writing practice
        consent/           # Recording consent
        skills/            # Skills overview
        simulate/          # Simulation library
        season/            # Season/plan
        writing-reviews/   # Writing feedback
        leaderboard/       # Student rankings
        contact/           # Contact page
        plans/             # Pricing plans
      login/               # Sign in
      signup/              # Register
      forgot-password/     # Password reset
      attempt/             # Test runner (outside shell)
      invite/              # External candidate invite
      proctoring/          # ProctorCamera, detectors, ViolationToast
    components/            # React components
      shell/               # AppShell, navigation
      brand/               # Logo, hero mic, brand
      Report.tsx           # PDF report generation
      ui.tsx               # Shared UI primitives
    lib/
      api.ts               # API client (single source of truth)
      audio.ts             # Audio playback, TTS, mic recording
      nav.ts               # Navigation config
      roles.ts             # Role helpers
      setTracker.ts        # Client-side set deduplication
      proctoring/          # useProctoring hook
    package.json
  docker-compose.yml
  .gitignore
```

## Security

- **Never commit** `.env` or files containing `MONGO_URI`, `JWT_SECRET`, or API keys
- Tenant isolation by `tenant_id` on every document
- JWT tokens carry `scope` (platform/tenant) and `tenant_id`
- Audit logging on all write operations
- Recording consent required before any exam
- Rate limiting on login attempts
- Password hashing with bcrypt
- CORS configured to specific origins

# CommunicationIQ Frontend Requirements

## Tech Stack
- Next.js 14 (App Router)
- TypeScript
- Tailwind CSS with theme token system (17 themes)
- recharts for charts
- Lucide React for icons

## Roles
| Role | Description |
|------|-------------|
| student | Takes exams, practices, views results |
| tenant_admin | Manages institution users, cohorts, readiness |
| super_admin | Manages all institutions, question bank, audit |

## Pages (45 total)

### Public
| Route | File | Description |
|-------|------|-------------|
| `/` | `app/page.tsx` | Marketing landing page |
| `/login` | `app/login/page.tsx` | Sign in |
| `/signup` | `app/signup/page.tsx` | Student self-registration |
| `/forgot-password` | `app/forgot-password/page.tsx` | Password reset |
| `/invite/[token]` | `app/invite/[token]/page.tsx` | External candidate invitation |
| `/contact` | `app/(app)/contact/page.tsx` | Contact page |
| `/plans` | `app/(app)/plans/page.tsx` | Pricing plans |

### Student
| Route | File | Description |
|-------|------|-------------|
| `/home` | `app/(app)/home/page.tsx` | Dashboard with next actions |
| `/tests` | `app/(app)/tests/page.tsx` | Assessment library |
| `/practise` | `app/(app)/practise/page.tsx` | Practice hub (4 skills) |
| `/simulate` | `app/(app)/simulate/page.tsx` | Full-length exam library |
| `/quiz` | `app/(app)/quiz/page.tsx` | Grammar/vocabulary quiz |
| `/listening` | `app/(app)/listening/page.tsx` | Listening practice |
| `/reading` | `app/(app)/reading/page.tsx` | Reading practice |
| `/writing` | `app/(app)/writing/page.tsx` | Writing practice |
| `/results/[id]` | `app/(app)/results/[id]/page.tsx` | Exam results + review card |
| `/my-progress` | `app/(app)/my-progress/page.tsx` | Progress tracking |
| `/consent` | `app/(app)/consent/page.tsx` | Recording consent |
| `/skills` | `app/(app)/skills/page.tsx` | Skills overview |
| `/settings` | `app/(app)/settings/page.tsx` | Account settings |
| `/season` | `app/(app)/season/page.tsx` | Gamification |
| `/writing-reviews` | `app/(app)/writing-reviews/page.tsx` | Writing reviews |
| `/leaderboard` | `app/(app)/leaderboard/page.tsx` | Student rankings |

### Tenant Admin
| Route | File | Description |
|-------|------|-------------|
| `/tenant` | `app/(app)/tenant/page.tsx` | Institution overview + charts |
| `/tenant/users` | `app/(app)/tenant/users/page.tsx` | User management |
| `/tenant/profiles` | `app/(app)/tenant/profiles/page.tsx` | Assessment profiles |
| `/tenant/results` | `app/(app)/tenant/results/page.tsx` | Exam results |
| `/tenant/readiness` | `app/(app)/tenant/readiness/page.tsx` | Cohort readiness |

### Platform Admin
| Route | File | Description |
|-------|------|-------------|
| `/platform` | `app/(app)/platform/page.tsx` | Platform overview + charts |
| `/platform/tenants` | `app/(app)/platform/tenants/page.tsx` | Institution management |
| `/platform/plans` | `app/(app)/platform/plans/page.tsx` | Plans & pricing |
| `/platform/content` | `app/(app)/platform/content/page.tsx` | Question bank CRUD + sets |
| `/platform/exam-tests` | `app/(app)/platform/exam-tests/page.tsx` | Exam test management |
| `/platform/exam-schedules` | `app/(app)/platform/exam-schedules/page.tsx` | Exam scheduling |
| `/platform/companies` | `app/(app)/platform/companies/page.tsx` | Company management + sets |
| `/platform/results` | `app/(app)/platform/results/page.tsx` | Cross-institution results |
| `/platform/reviews` | `app/(app)/platform/reviews/page.tsx` | Student reviews |
| `/platform/audit` | `app/(app)/platform/audit/page.tsx` | Audit log |
| `/platform/messages` | `app/(app)/platform/messages/page.tsx` | Messages |
| `/platform/smtp` | `app/(app)/platform/smtp/page.tsx` | Email / SMTP config |
| `/platform/payments` | `app/(app)/platform/payments/page.tsx` | Payments |

### Tenant Admin
| Route | File | Description |
|-------|------|-------------|
| `/tenant` | `app/(app)/tenant/page.tsx` | Institution overview + charts |
| `/tenant/users` | `app/(app)/tenant/users/page.tsx` | User management |
| `/tenant/profiles` | `app/(app)/tenant/profiles/page.tsx` | Assessment profiles |
| `/tenant/results` | `app/(app)/tenant/results/page.tsx` | Exam results |
| `/tenant/readiness` | `app/(app)/tenant/readiness/page.tsx` | Cohort readiness |
| `/tenant/reviews` | `app/(app)/tenant/reviews/page.tsx` | Student reviews |
| `/tenant/audit` | `app/(app)/tenant/audit/page.tsx` | Audit log |

### Exam Runner (outside app shell)
| Route | File | Description |
|-------|------|-------------|
| `/attempt/[id]/run` | `app/attempt/[id]/run/page.tsx` | Full exam engine |

## Requirements

### R-LOADING: Loading States
- Every page must show a Skeleton component while data loads via `useData`
- Every async button must show disabled state + changing text (e.g. "Saving...")
- The global LoadingProvider overlay must show centered spinner for all API calls
- Loading overlay must be visible within 200ms of any action
- Every page transition must show the loading overlay for 400ms

### R-TOAST: Notifications
- Every success action must trigger a toast("success", message)
- Every error action must trigger a toast("error", message)
- Toast must auto-dismiss after 4 seconds
- Toast must be dismissible via X button

### R-FULLSCREEN: Exam Fullscreen
- Exam runner must prompt user to enter fullscreen before starting
- If user declines, exam can proceed in windowed mode
- Fullscreen toggle button must be visible at all times during exam
- Exiting fullscreen must not interrupt the exam

### R-REVIEW: Post-Exam Review Card
- After completing any exam, a review card must appear on the results page
- Review card must include: 5-star rating, difficulty selector, comment textarea
- Review must be visible to: student (who wrote it), tenant admin, super admin
- Admin views must show who wrote each review and their rating

### R-CHARTS: Admin Dashboard Charts
- Platform overview: pie chart (question distribution), bar chart (institutions), horizontal bar (questions by category)
- Tenant overview: institution-specific charts (students by cohort, readiness distribution, exam completion rates)

### R-UI: User Interface
- All pages must use the theme token system (no hardcoded colors)
- All buttons must be interactive and respond to clicks
- All forms must validate before submission
- All navigation links must resolve to existing pages
- No emojis, no mock data, no placeholder content in production UI


---

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
| 3 Sep | `0b5dcdf`, `93f68d1` | Seed/debug/test scripts removed from the repo; **Exam Tests** engine (weightage + per-section timing), **Question Sets** (10-question sets auto-created), **Companies** with question counts, **Plans & Pricing** (4 seeded plans), **Exam Schedules** groundwork, platform pages for Messages, Email/SMTP, Payments, Contact, Plans; student Plans page for general users; subscription gating for general users; audit log |
| 4 Sep | `7093b48` | Removed duplicate code blocks and fixed JSX structure / imports in all practice pages (quiz, reading, writing, listening, attempt runner) |

### Platforms pages now live under `/platform/…`
`Dashboard` · `All Institutions` (tenants) · `Plans & Pricing` · `Question Bank` ·
`Question Sets` · `Exam Tests` · **`Exam Schedules` (new)** · `Companies` ·
`All Results` · `Reviews` · `Audit Log` · `Messages` · `Email / SMTP` ·
`Payments` · `Settings`

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


---

## 6. Student Leaderboard

Students can compare themselves inside their own institution or across every
institution on the platform.

- `GET /api/v1/student/leaderboard?scope=institution|global` ranks students by
  **best overall exam score** (max of non-shadow `overall` score_records), ties
  broken by attempt count. Only students with at least one scored exam appear;
  the caller's own row is always included with their rank. Everything is
  computed live — nothing is stored.
- Frontend: **Leaderboard** page under the student rail with an *Institution /
  All institutions* toggle, free-text search, and institution filter on the
  global view.

## 7. In-app notification centre (all roles)

The header bell is fed by a backend feed (polls every 45s):

- `GET /api/v1/notifications` — role-scoped, computed live:
  - **student** → recent scored results + scheduled exams for their institution;
  - **tenant_admin** → reviews their students left in the last 7 days;
  - **super_admin** → open contact messages in the inbox.
- `PATCH /api/v1/notifications` and `POST /api/v1/notifications/read-all`
  persist read state in `notification_reads` per user + key.

## 8. Single database, admin-created accounts, email sender, cleanup

- **Single database.** All data lives in one MongoDB database (`CommunicationIQ`);
  tenant isolation is by `tenant_id` filters. Legacy per-tenant databases
  (`tenant_stmarys`, `tenant_vignan`) were dropped from the server.
- **No domain-based signup.** Self-registration always creates a general
  practice account; institution students are created by their tenant admin.
- **Email sender implemented.** `app/email_sender.py` (previously missing while
  two call sites imported it) sends via saved `smtp_configs` with built-in
  templates and `{{var}}` rendering; graceful when SMTP is unset. Emails are
  **system-triggered only** (student created, first login) — the manual admin
  Email Templates page, nav link and CRUD endpoints were removed.
- **Interview/CV content removed.** The platform is LSRW + company/Versant
  assessment only: the unused "HR questions" blueprint was renamed to spoken
  questions copy, the login word cloud no longer says "Interview", and the
  one-off `migrate_data.py` script was deleted.
- **Terms & Privacy pages** added (`/terms`, `/privacy`) with footer links on
  the landing page and app shell.
- **Results charts:** skill scoreboard now shows ring, radar, bar and pie
  (donut) breakdowns of the LSRW dimensions.
- **Dead code removed.** ~2,690 commented-out lines stripped from
  `app/routers/attempts.py`; vitest scaffolding (script, config, setup)
  removed — no test files remain.
- **Data checked for duplicates:** 22 users / 22 unique emails; attempt and
  score `_id`s unique. None found.
- **UI polish pass (Sep 2026).** Hardcoded Tailwind palette colours across 16
  pages converted to theme tokens (status pills via `status-ok/warn/bad/info/
  brand`, RAG for danger/delete); a broken `/15`-opacity pattern (which
  Tailwind cannot compile against `var()` colours — including the old
  `text-muted/30`) was replaced with real `color-mix()` classes; premium
  shared CSS in `globals.css` (button lift + glow, input hover, uppercase
  table headers + zebra rows, sticky blurred app header, card catch-light),
  `.card-interactive` hover lift on whole-card links, and staggered content
  reveal on the overviews. The platform overview's duplicate question chart
  was replaced with per-institution seat usage; the tenant overview's doubled
  seat-usage panels were merged into one.
- **Product name in the exam runner.** The runner header (standard and
  Versant-style), the intro screen, and the practice surfaces carry the
  CommunicationIQ wordmark so the platform name is consistent mid-exam.
- **Final dead-code sweep.** Orphaned `frontend/app/utils/*` (clearCache,
  fullscreenUtils, stripMarkdown, tabPreventionUtils, testProgressUtils) and
  standalone CLI modules with no importers (`app/silence.py`,
  `app/calibrate.py`) removed; duplicate/`dark:`-variant palette classes
  gone; no console.log/debugger/mock/lorem content remains.

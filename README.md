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
| Speech | faster-whisper, wav2vec2 (optional Tier 1) |
| AI Narration | Anthropic Claude / OpenAI-compatible / NVIDIA NIM |

## Quick Start

### Backend
```bash
cd backend
python -m venv .venv
.venv/Scripts/activate  # Windows
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8010
```

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

### Domain-Based Login

Login is determined by email domain:
- `@stmarys.edu` → St. Mary's Engineering College
- `@vignan.ac.in` → Vignan's Institute of Engineering
- `@saashx.ai` / `@platform.com` / `@fluenzee.com` → Platform admin

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
| simulation_profiles | 6 | Base + VERSANT + company rounds |
| profile_sections | 33 | 4-6 sections per profile |
| reading_passages | 6 | 4 general + 2 Accenture |
| writing_prompts | 15 | General practice prompts |
| listening_passages | 4 | General practice passages |
| quiz_items | 110+ | grammar, vocabulary, reading, listening |
| task_items | 90 | Speaking tasks (6 types × 15 each) |
| exam_reviews | 6 | Student exam feedback |
| writing_submission_row | 3 | Writing practice submissions |
| skill_mastery | 4 | Per-student skill tracking |

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
4. Automatic scoring (speech engine or Tier 0 timing)
5. Detailed results with diagnosis and recommendations
6. AI-generated explanation (optional)

### Anti-Proctoring
- Right-click, copy/paste, screenshot shortcuts disabled
- Text selection blocked during exams
- Browser navigation warning

### Question Bank (Platform Admin)
- Full CRUD for: Reading, Writing, Listening, Speaking, Grammar, Vocabulary
- Company-specific questions
- Questions shared across all institutions

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
- AI narration settings
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
        platform_admin.py  # Platform console, questions, audit
        platform_writes.py # Tenant/provider management
        admin.py         # Cohort readiness, student results
        game.py            # Gamification state
        practice.py        # Quiz, drills, mistakes
        listening.py       # Listening practice
        reading.py         # Reading practice
        writing.py         # Writing practice
        invitations.py     # External candidate invitations
        report.py          # HTML report generation
      gamification/        # XP, quests, streaks, badges
      engine/              # Speech scoring engine
      narration/           # AI feedback narrator
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
        platform/          # Platform admin
        tenant/            # Institution admin
        quiz/              # Grammar/vocabulary quiz
        reading/           # Reading practice
        listening/         # Listening practice
        writing/           # Writing practice
        consent/           # Recording consent
        skills/            # Skills overview
        simulate/          # Simulation library
        season/            # Season/plan
        writing-reviews/   # Writing feedback
      login/               # Sign in
      signup/              # Register
      attempt/             # Test runner (outside shell)
      invite/              # External candidate invite
    components/            # React components
      shell/               # AppShell, navigation
      brand/               # Logo, hero mic, brand
      ui.tsx               # Shared UI primitives
    lib/
      api.ts               # API client (single source of truth)
      nav.ts               # Navigation config
      roles.ts             # Role helpers
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

## Pages (31 total)

### Public
| Route | File | Description |
|-------|------|-------------|
| `/` | `app/page.tsx` | Marketing landing page |
| `/login` | `app/login/page.tsx` | Sign in |
| `/signup` | `app/signup/page.tsx` | Student self-registration |
| `/invite/[token]` | `app/invite/[token]/page.tsx` | External candidate invitation |

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
| `/platform/content` | `app/(app)/platform/content/page.tsx` | Question bank CRUD |
| `/platform/results` | `app/(app)/platform/results/page.tsx` | Cross-institution results |
| `/platform/audit` | `app/(app)/platform/audit/page.tsx` | Audit log |

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

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
| users | 9 | 2 admins + 7 students |
| tenant_user_directory | 9 | Email → institution mapping |
| simulation_profiles | 12 | 6 per institution |
| profile_sections | varies | Sections per profile |
| reading_passages | 54 | 44 shared + 10 company-specific |
| writing_prompts | 50 | 40 shared + 10 company-specific |
| listening_passages | 15 | 10 shared + 5 company-specific |
| quiz_items | 237 | 206 shared + 31 company-specific |
| task_items | 186 | 156 shared + 30 company-specific |
| audit_log | 50+ | Login and action tracking |

### Question Categories

| Category | Items | Used In |
|----------|-------|---------|
| Reading Comprehension | 110 | Reading sections |
| Audio Comprehension | 45 | Listening sections |
| Grammar | 30 | Quiz practice |
| Vocabulary | 30 | Quiz practice |
| Speaking (Quiz) | 12 | Speaking quiz sections |
| Read Aloud | 10 | Speaking sections |
| Repeat Sentence | 8 | Speaking sections |
| Short Answer | 12 | Speaking sections |
| Sentence Build | 6 | Speaking sections |
| Story Retell | 2 | Speaking sections |
| Open Response | 118 | Speaking sections |
| Reading Passages | 44 | Reading sections |
| Writing Prompts | 40 | Writing sections |
| Listening Passages | 10 | Listening sections |

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
- Practice sessions (speaking, listening, reading, writing)
- Grammar & vocabulary quizzes
- Attempt history and detailed results
- Profile editing (name, roll number, branch, year)
- 17 theme options
- Writing reviews

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
        trainer.py         # Cohort readiness, student results
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

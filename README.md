# CommunicationIQ

Communication assessment and training platform for placement readiness. AI-powered scoring of pronunciation, fluency, grammar, content, and listening comprehension with institution-level tenant isolation on MongoDB Atlas.

## Architecture

```
Frontend (Next.js)          Backend (FastAPI)           MongoDB Atlas
     |                           |                          |
  /login ──────────────────> /api/v1/auth/login            |
  /home ───────────────────> /api/v1/student/home           |
  /platform ───────────────> /api/v1/platform/*             |
     |                           |                          |
     └── API layer ────────> deps.py (auth) ─────────> MongoDB
                                |                    Motor + Beanie
                            routers/                  |
                                |                     |
                            services/                 |
                            security.py               |
                            gamification/             |
                                |                     |
                          ┌─────┴─────┐               |
                          │ db.py     │──────────────>│
                          │ Session   │   Beanie ODM  │
                          │ .find()   │──────────────>│
                          │ .execute()│               │
                          └───────────┘               |
                                                      │
                     ┌────────────────────────────────┤
                     │ CommunicationIQ (control plane) │
                     │   plans, tenants, users,        │
                     │   providers, audit              │
                     └────────────────────────────────┘
                     ┌────────────────────────────────┐
                     │ tenant_stmarys (institution DB) │
                     │   users, attempts, scores,      │
                     │   profiles, gamification        │
                     └────────────────────────────────┘
```

## Technology Stack

| Layer        | Technology                        |
|-------------|----------------------------------|
| Frontend    | Next.js 15, React 19, TypeScript, Tailwind CSS |
| Backend     | Python 3.12+, FastAPI, uvicorn   |
| Database    | MongoDB Atlas (Beanie ODM + Motor) |
| Auth        | JWT (python-jose)                |
| Speech      | faster-whisper, wav2vec2 (optional Tier 1) |

## Database Architecture

- **Database-per-tenant**: each institution has its own MongoDB database (`tenant_<slug>`)
- **Control plane**: `CommunicationIQ` database holds platform-wide data (plans, tenants, providers, audit)
- **Beanie ODM**: document models are in `app/models/platform.py` and `app/models/tenant.py`
- **SQLAlchemy query expressions**: service modules use `select()` / `delete()` which are translated to Beanie `.find()` calls by the `Session` class in `app/db.py`

### Collections (control plane)

| Collection            | Purpose                           |
|----------------------|-----------------------------------|
| plans                | Pricing templates                 |
| tenants              | Institution registry              |
| subscriptions        | Tenant-plan bindings              |
| platform_users       | Platform staff accounts           |
| provider_registry    | AI provider catalog               |
| provider_configs     | Active provider selections        |
| gamification_config  | XP/league/streak rules            |
| audit_log            | Immutable audit trail             |

## Environment Variables

Copy `backend/.env.example` to `backend/.env` and configure:

```bash
MONGO_URI=mongodb://localhost:27017/CommunicationIQ  # Atlas or local
JWT_SECRET=<your-secret>                             # Never commit
APP_URL=http://localhost:3010
CORS_ORIGINS=["http://localhost:3010"]
MEDIA_ROOT=../tmp
WHISPER_MODEL=small.en
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
WHISPER_WARM_ON_STARTUP=true
```

## Quick Start

### Option 1: Docker (Recommended)

```bash
docker-compose up --build
```

- Frontend: http://localhost:3010
- Backend API: http://localhost:8010
- API Docs: http://localhost:8010/docs
- MongoDB: localhost:27017

### Option 2: Manual Setup

**Prerequisites:** Python 3.12+, Node.js 18+, MongoDB (local or Atlas)

**Backend:**
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env       # edit MONGO_URI and JWT_SECRET
uvicorn app.main:app --host 0.0.0.0 --port 8010
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3010 — you should see the **Home page**.

### Login Credentials

**Platform Staff:**

| Email | Password | Role | Scope |
|-------|----------|------|-------|
| admin@saashx.ai | Password123! | super_admin | platform |
| finance@saashx.ai | Password123! | finance | platform |
| content@saashx.ai | Password123! | content | platform |

**St Mary's Institute (tenant: stmarys):**

| Email | Password | Role |
|-------|----------|------|
| admin@stmarys.edu | Password123! | admin |
| trainer@stmarys.edu | Password123! | trainer |
| student@stmarys.edu | Password123! | student |
| priya@stmarys.edu | Password123! | student |
| rahul@stmarys.edu | Password123! | student |
| anita@stmarys.edu | Password123! | student |

**Vignan University (tenant: vignan):**

| Email | Password | Role |
|-------|----------|------|
| admin@vignan.edu | Password123! | admin |
| trainer@vignan.edu | Password123! | trainer |
| student@vignan.edu | Password123! | student |
| priya@vignan.edu | Password123! | student |
| rahul@vignan.edu | Password123! | student |
| anita@vignan.edu | Password123! | student |

### Audit Logging

Every login and write operation (user create/update, cohort changes, profile modifications, etc.) is recorded in the `audit_log` collection. Platform super_admins can view the full audit trail at `/platform/audit`. Each entry records:
- **Actor**: who performed the action
- **Action**: what was done (e.g., `auth.login`, `user.created`)
- **Entity**: which model was affected
- **Timestamp**: when it happened
- **Before/After**: the state change

## Frontend Pages

| Route | Description | Auth Required |
|-------|-------------|---------------|
| `/` | Home / landing | No |
| `/login` | Sign in | No |
| `/home` | Student dashboard | Student |
| `/coaching` | Trainer overview | Trainer |
| `/cohorts` | Trainer cohorts | Trainer |
| `/momentum` | Trainer momentum | Trainer |
| `/flags` | At-risk flags | Trainer |
| `/practise` | Practice drills | Student |
| `/tests` | Take a test | Student |
| `/my-progress` | My progress | Student |
| `/quiz` | Quiz module | Student |
| `/listening` | Listening module | Student |
| `/reading` | Reading module | Student |
| `/writing` | Writing module | Student |
| `/skills` | Skills view | Student |
| `/settings` | Settings | All roles |
| `/tenant` | Tenant overview | Tenant admin |
| `/tenant/users` | People management | Tenant admin |
| `/tenant/cohorts` | Cohort management | Tenant admin |
| `/tenant/profiles` | Assessment profiles | Tenant admin |
| `/tenant/invitations` | Invitations | Tenant admin |
| `/tenant/season` | Placement season | Tenant admin |
| `/tenant/readiness` | Readiness dashboard | Tenant admin |
| `/tenant/import` | User import | Tenant admin |
| `/platform` | Platform overview | Platform staff |
| `/platform/tenants` | Institution management | Platform staff |
| `/platform/plans` | Pricing plans | Platform staff |
| `/platform/providers` | Engine capabilities | Platform staff |
| `/platform/gamification` | Game economy | Platform staff |
| `/platform/audit` | Audit log | Platform staff |
| `/platform/billing` | Billing | Platform staff |

## API Operations

### Auth (all roles)
- `POST /api/v1/auth/login` — Sign in with email/password → returns JWT + user
- `GET /api/v1/auth/me` — Current session user

### Student
- `GET /api/v1/student/home` — Dashboard (streak, XP, attempts, mastery)
- `GET /api/v1/student/profiles` — Available simulation profiles
- `GET /api/v1/student/attempts` — Past attempts
- `POST /api/v1/student/attempts` — Start a new attempt
- `POST /api/v1/student/attempts/{id}/submit` — Submit and score
- `GET /api/v1/student/attempts/{id}/result` — View results
- `GET /api/v1/student/attempts/{id}/export.csv` — Export results as CSV

### Trainer
- `GET /api/v1/trainer/cohorts` — List cohorts
- `GET /api/v1/trainer/cohorts/{id}/students` — Cohort student summaries
- `GET /api/v1/trainer/cohorts/{id}/readiness` — Cohort readiness
- `GET /api/v1/trainer/flags` — List at-risk flags
- `POST /api/v1/trainer/flags` — Raise flag (stored in DB)
- `POST /api/v1/trainer/flags/{id}/resolve` — Resolve flag

### Tenant Admin
- `GET /api/v1/tenant/overview` — Tenant stats
- `GET /api/v1/tenant/users` — List users (filterable by role)
- `POST /api/v1/tenant/users` — Create user
- `POST /api/v1/tenant/users/import` — Bulk import from CSV
- `GET /api/v1/tenant/cohorts` — List cohorts
- `POST /api/v1/tenant/cohorts` — Create cohort
- `GET /api/v1/tenant/profiles` — List assessment profiles
- `POST /api/v1/tenant/profiles` — Create profile
- `POST /api/v1/tenant/profiles/{id}/clone` — Clone profile
- `PUT /api/v1/tenant/profiles/{id}` — Update profile
- `POST /api/v1/tenant/profiles/{id}/status` — Publish/retire profile
- `GET /api/v1/tenant/invitations` — List invitations
- `POST /api/v1/tenant/invitations` — Create invitation
- `GET /api/v1/tenant/season` — Placement season data

### Platform Admin
- `GET /api/v1/platform/overview` — Platform stats
- `GET /api/v1/platform/tenants` — List institutions
- `POST /api/v1/platform/tenants` — Create institution
- `GET /api/v1/platform/plans` — List pricing plans
- `GET /api/v1/platform/capabilities` — Engine capabilities & providers
- `GET /api/v1/platform/audit` — Audit log (all actions stored)
- `GET /api/v1/platform/gamification` — Game economy config

### Data Storage
Every action is stored in MongoDB:
- **audit_log** — Every login, user create/update, flag, profile change
- **attempts** — Every test attempt with scores and status
- **responses** — Individual item responses with transcripts
- **score_records** — Per-dimension scores for each response
- **xp_ledger** — XP awards for completed activities
- **streak_states** — Daily streak tracking
- **skill_mastery** — Per-skill mastery levels
- **student_flags** — At-risk flags raised by trainers
- **consent_records** — Student consent for recording
- **cohort_members** — Student-cohort assignments

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
      models/
        platform.py        # Control-plane document models
        tenant.py          # Institution document models
      routers/             # API route handlers
      gamification/        # XP, quests, streaks, badges
      engine/              # Speech scoring engine
      narration/           # AI feedback narrator
      storage/             # File storage abstraction
      validation/          # Assessment validation
    requirements.txt
    .env.example
  frontend/
    app/                   # Next.js pages
    components/            # React components
    lib/                   # Utilities, API client, navigation
    package.json
  docs/                    # Documentation
  README.md
  .gitignore
```

## Known Limitations

- **Tier 0 only** by default: pronunciation, accuracy, grammar, and content scoring require the speech engine from `requirements-engine.txt`
- **Local storage only**: `MEDIA_ROOT` points to `../tmp`; S3-class object storage is not yet wired
- **Narration**: requires an OpenAI-compatible server or Anthropic API key

## Security

- **Never commit** `.env` or any file containing `MONGO_URI`, `JWT_SECRET`, or API keys
- Database credentials are rotated in Atlas, not in code
- Tenant isolation is structural: each institution has its own MongoDB database
- JWT tokens carry `scope` (platform/tenant) and `tenant_slug` — cross-tenant access is impossible by design

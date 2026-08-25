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
                            seed.py                   |
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

### Prerequisites
- Python 3.12+
- Node.js 18+
- MongoDB Atlas cluster (or local MongoDB)

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env       # edit MONGO_URI and JWT_SECRET
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3010 — you should see the **Home page**.

### Seed Data

The MongoDB Atlas cluster already contains seed data (plans, tenants, users, providers). To re-seed:

```bash
cd backend
python -m app.seed --reset
```

### Default Accounts

| Email | Password | Role |
|-------|----------|------|
| admin@saashx.ai | Password123! | Platform super_admin |
| finance@saashx.ai | Password123! | Platform finance |
| content@saashx.ai | Password123! | Platform content |

## Frontend Pages

| Route | Description | Auth Required |
|-------|-------------|---------------|
| `/` | Home / landing | No |
| `/login` | Sign in | No |
| `/home` | Student dashboard | Student |
| `/coaching` | AI coaching | Student |
| `/quiz` | Quiz module | Student |
| `/listening` | Listening module | Student |
| `/reading` | Reading module | Student |
| `/writing` | Writing module | Student |
| `/practise` | Practice drills | Student |
| `/skills` | Skills view | Student |
| `/progress` | My progress | Student |
| `/settings` | Settings | Student |
| `/tenant/*` | Tenant admin | Tenant admin |
| `/platform/*` | Platform admin | Platform staff |

## Testing

### Backend Tests
```bash
cd backend
.venv/Scripts/python -m pytest -v
```

### Frontend Tests
```bash
cd frontend
npx vitest run
```

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
    tests/                 # Backend test suite
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

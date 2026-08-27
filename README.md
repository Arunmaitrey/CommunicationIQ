# CommunicationIQ

Communication assessment and training platform for placement readiness. AI-powered scoring of pronunciation, fluency, grammar, content, and listening comprehension with institution-level tenant isolation on MongoDB Atlas.

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
                      │   tenants, users, providers,    │
                      │   audit, gamification           │
                      └────────────────────────────────┘
                      ┌────────────────────────────────┐
                      │ tenant_stmarys (institution DB) │
                      │   users, attempts, scores,      │
                      │   profiles, gamification        │
                      └────────────────────────────────┘
```

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14, React 18, TypeScript, Tailwind CSS |
| Backend | Python 3.14+, FastAPI, uvicorn |
| Database | MongoDB Atlas (Beanie ODM + Motor) |
| Auth | JWT (python-jose) |
| Speech | faster-whisper, wav2vec2 (optional Tier 1) |

## Roles (3)

| Role | Scope | Access |
|------|-------|--------|
| `super_admin` | Platform-wide | All institutions, users, audit logs, question bank management |
| `tenant_admin` | Single institution | Own institution's users, cohorts, profiles, results. Cannot see other institutions |
| `student` | Own account | Take assessments, view own results and progress |

## Quick Start

### Backend
```bash
cd backend
python -m venv .venv
.venv/Scripts/activate  # Windows
pip install -r requirements.txt
# Set MONGO_URI in .env to your Atlas connection string
uvicorn app.main:app --host 0.0.0.0 --port 8010
```

### Frontend
```bash
cd frontend
npm install
npm run dev  # Runs on port 3010
```

### Login Credentials

All passwords: `password123`

**Platform:**

| Email | Role |
|-------|------|
| admin@saashx.ai | super_admin |

**St Mary's Institute (stmarys):**

| Email | Role |
|-------|------|
| admin@stmarys.edu | tenant_admin |
| aarav.reddy1@stmarys.edu | student |
| (30 students total) | student |

**Vignan University (vignan):**

| Email | Role |
|-------|------|
| admin@vignan.edu | tenant_admin |
| aarav.reddy1@vignan.edu | student |
| (12 students total) | student |

## Features

### Exam Types (LSRW)
- **Listening** — Audio played once, comprehension MCQs
- **Speaking** — Read Aloud, Repeat Sentence, Short Answer, Open Response, Story Retell, Sentence Build
- **Reading** — Timed passages with MCQs
- **Writing** — Essay and email prompts with 5-dimension scoring

### Company-Specific Rounds
- Accenture-style Communication Round
- Cognizant-style Communication Assessment
- Infosys-style Communication Practice
- TCS-family Communication Practice
- Wipro-style Voice Round

### Anti-Proctoring
- Right-click disabled during exams
- Copy/paste/cut blocked
- Screenshot shortcuts blocked (PrintScreen, Ctrl+P/S/U, F12)
- Text selection disabled
- Visual proctoring notice banner
- Browser navigation warning (beforeunload)
- Presence detection

### Exam Resume
- In-progress attempts detected on tests page
- Resume button with "In Progress" badge
- Runner recovers from any interruption (page reload, network, crash)
- IndexedDB audio queue survives browser restarts

### Student Review/Rating
- 5-star rating after every exam
- Optional comment and difficulty feedback
- Read-only view if already submitted

### Question Bank Management
- Full CRUD (add/edit/delete) for 6 categories: Reading, Writing, Listening, Speaking, Grammar, Vocabulary
- Company-specific questions (TCS, Infosys, Wipro, Accenture, Cognizant)
- Questions visible to all tenants via question bank API

### User Management (Tenant Admin)
- Create/edit/deactivate students
- Reset passwords
- View user list with status

### Profile & Settings
- Student profile editing (Full Name, Roll Number, Branch, Year, L1 Language)
- Notification preferences (Practice Reminders, Exam Deadline Alerts)
- Password change with visibility toggle

### Home Page
- Quick Actions grid (6 cards)
- Recent Activity (last 3 attempts)
- Improvement Tips

### Gamification
- XP system with daily streaks
- Badge earning and display
- Daily quests and challenges
- Season/league system

## Database

### Architecture
- **Database-per-tenant**: each institution has its own MongoDB database (`tenant_<slug>`)
- **Control plane**: `CommunicationIQ` database holds platform-wide data
- **Beanie ODM**: document models in `app/models/platform.py` and `app/models/tenant.py`
- **SQL bridge**: `app/sqlbridge.py` translates SQLAlchemy-shaped queries to Beanie

### Data Counts

| Collection | stmarys | vignan |
|-----------|---------|--------|
| users | 31 | 13 |
| simulation_profiles | 21 | 21 |
| reading_passages | 119 | 102 |
| listening_passages | 19 | 14 |
| writing_prompts | 104 | 100 |
| quiz_items | 643 | 570 |
| task_items | 180 | 162 |
| attempts | 34 | 8 |
| consent_records | 30 | 12 |
| cohorts | 3 | 1 |

## Project Structure

```
CommunicationIQ/
  backend/
    app/
      main.py              # FastAPI app + lifespan
      config.py            # Settings from env
      db.py                # MongoDB data layer (Beanie + Session bridge)
      sqlbridge.py         # SQLAlchemy query expressions over Beanie
      deps.py              # Auth dependencies
      security.py          # JWT + password hashing
      models/
        _common.py         # StrId type for ObjectId tolerance
        platform.py        # Control-plane document models
        tenant.py          # Institution document models
      routers/             # API route handlers
      gamification/        # XP, quests, streaks, badges
      engine/              # Speech scoring engine
      narration/           # AI feedback narrator
    requirements.txt
    .env.example
  frontend/
    app/                   # Next.js pages (App Router)
    components/            # React components
    lib/                   # Utilities, API client, navigation
    package.json
  Documentation/           # Project documentation
  README.md
  .gitignore
```

## Security

- **Never commit** `.env` or any file containing `MONGO_URI`, `JWT_SECRET`, or API keys
- Tenant isolation is structural: each institution has its own MongoDB database
- JWT tokens carry `scope` (platform/tenant) and `tenant_slug` — cross-tenant access is impossible by design
- Audit logging on all write operations
- Recording consent required before any exam

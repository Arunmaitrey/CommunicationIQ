# System Architecture

## Overview

CommunicationIQ is a full-stack communication assessment platform. It evaluates students on pronunciation, fluency, grammar, content recall, listening comprehension, and reading comprehension using AI-powered scoring.

## High-Level Flow

```
Student → Browser (Next.js) → FastAPI Backend → MongoDB Atlas
                                    ↓
                              Speech Engine (Tier 0/1)
                                    ↓
                              Score + AI Narration
```

## Backend Architecture

### Request Lifecycle

1. **HTTP request** arrives at FastAPI
2. **deps.py** extracts JWT, resolves Principal (platform/tenant scope)
3. **Router** handles the endpoint (e.g., `routers/attempts.py`)
4. **Services** (gamification, engine, scoring) process business logic
5. **db.py Session** translates SQLAlchemy `select()` to Beanie `.find()`
6. **Beanie/Motor** executes against MongoDB
7. **Response** returned to client

### Module Map

| Module | Purpose |
|--------|---------|
| `main.py` | FastAPI app, lifespan, route registration |
| `config.py` | Pydantic Settings from environment |
| `db.py` | MongoDB connection, Beanie init, Session bridge |
| `sqlbridge.py` | SQLAlchemy query expressions over Beanie |
| `deps.py` | Auth dependencies (Principal, TenantModels, etc.) |
| `security.py` | JWT encode/decode, password hashing |
| `provisioning.py` | Tenant database creation/indexes |

### Routers

| Router | Prefix | Scope | Purpose |
|--------|--------|-------|---------|
| `auth` | `/auth` | Public | Login, signup, token refresh, preferences |
| `student` | `/student` | Student | Profile, home, skills, consent |
| `attempts` | `/student/attempts` | Student | Create attempt, answer, submit, score, resume |
| `listening` | `/student/listening` | Student | Listening comprehension |
| `reading` | `/student/reading` | Student | Reading comprehension |
| `writing` | `/student/writing` | Student | Writing prompts and submissions |
| `game` | `/student/game` | Student | XP, badges, quests, streaks |
| `practice` | `/student/quiz` | Student | Quiz and drills |
| `trainer` | `/trainer` | Tenant Admin | Cohort readiness, student mastery, flags |
| `trainer_ops` | `/trainer` | Tenant Admin | Drill creation, intervention flags |
| `tenant_admin` | `/tenant` | Tenant Admin | Users, cohorts, profiles, invitations |
| `tenant_writes` | `/tenant` | Tenant Admin | User creation, cohort management |
| `platform_admin` | `/platform` | Platform | Overview, tenants, providers, question bank |
| `platform_writes` | `/platform` | Platform | Create/update tenants, plans |
| `platform_export` | `/platform` | Platform | DB export, tenant data export |
| `invitations` | `/invite` | Public | Token-based invite flow |

### Database Layer

- **Beanie ODM**: Document models in `app/models/platform.py` and `app/models/tenant.py`
- **Session bridge**: `db.py` provides `Session` class that translates `select(Model).where(...)` to `Model.find(...).to_list()`
- **Database-per-tenant**: each institution gets `tenant_<slug>` database — no shared collections
- **StrId type**: `app/models/_common.py` provides ObjectId→str coercion for robustness

### Engine Architecture

```
Audio Input → VAD → ASR (faster-whisper)
                   → Accuracy (reference match)
                   → Pronunciation (wav2vec2 GOP)
                   → Fluency (feature-based)
                   → Disfluency (transcript-based)
                   → Grammar (rule-based)
                   → Content (rubric coverage)
                   ↓
              Score Aggregation → Narration (AI explanation)
```

### Tier System

- **Tier 0** (default): VAD, fluency, storage, notifications — always available
- **Tier 1** (optional): ASR, pronunciation, accuracy, grammar, content — requires `requirements-engine.txt`

## Frontend Architecture

- **Next.js 14** with App Router
- **Tailwind CSS** for styling
- **Role-based routing**: home page loads first, login only for protected resources
- **API client** in `lib/api.ts` with automatic JWT token injection
- **Navigation** in `lib/nav.ts` with `landingFor(role)` for post-login redirect
- **Anti-proctoring**: clipboard, keyboard shortcuts, right-click disabled during exams
- **Exam resume**: in-progress attempt detection and recovery
- **IndexedDB queue**: audio uploads survive browser restarts

## Security Model

1. **JWT tokens** carry `scope` (platform/tenant), `role`, `tenant_slug`, `user_id`
2. **Tenant isolation**: each institution has its own MongoDB database — cross-tenant queries are structurally impossible
3. **Platform staff** cannot access student data — only business metrics
4. **Recording consent** required before any exam attempt
5. **Audit logging** on all write operations
6. **Anti-proctoring** measures during exam execution

## Roles

| Role | Scope | Access |
|------|-------|--------|
| `super_admin` | Platform-wide | All institutions, users, audit logs, question bank management |
| `tenant_admin` | Single institution | Own institution's users, cohorts, profiles, results |
| `student` | Own account | Take assessments, view own results and progress |

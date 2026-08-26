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
| `deps.py` | Auth dependencies (Principal, TenantModels, etc.) |
| `security.py` | JWT encode/decode, password hashing |
| `provisioning.py` | Tenant database creation/indexes |

### Routers

| Router | Prefix | Scope | Purpose |
|--------|--------|-------|---------|
| `auth` | `/auth` | Public | Login, token refresh |
| `student` | `/student` | Tenant | Profile, home, skills |
| `attempts` | `/student/attempts` | Tenant | Create attempt, answer, submit, score |
| `listening` | `/student/listening` | Tenant | Listening comprehension |
| `reading` | `/student/reading` | Tenant | Reading comprehension |
| `writing` | `/student/writing` | Tenant | Writing prompts and submissions |
| `game` | `/student/game` | Tenant | XP, badges, quests, streaks |
| `practice` | `/student/quiz` | Tenant | Quiz and drills |
| `trainer` | `/trainer` | Tenant (admin) | Cohort readiness, student mastery |
| `tenant_admin` | `/tenant` | Tenant (admin) | Users, cohorts, profiles, invitations |
| `platform_admin` | `/platform` | Platform | Overview, tenants, plans, providers |
| `platform_writes` | `/platform` | Platform | Create/update tenants, plans |
| `invitations` | `/invite` | Public | Token-based invite flow |

### Database Layer

- **Beanie ODM**: Document models in `app/models/platform.py` and `app/models/tenant.py`
- **Session bridge**: `db.py` provides `Session` class that translates `select(Model).where(...)` to `Model.find(...).to_list()` so service modules work without rewriting
- **Database-per-tenant**: each institution gets `tenant_<slug>` database — no shared collections

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

- **Next.js 15** with App Router
- **Tailwind CSS** for styling
- **Role-based routing**: home page loads first, login only for protected resources
- **API client** in `lib/api.ts` with automatic JWT token injection
- **Navigation** in `lib/nav.ts` with `landingFor(role)` for post-login redirect

## Security Model

1. **JWT tokens** carry `scope` (platform/tenant), `role`, `tenant_slug`, `user_id`
2. **Tenant isolation**: each institution has its own MongoDB database — cross-tenant queries are structurally impossible
3. **Platform staff** cannot access student data — only business metrics
4. **Candidates** access via token-only flow — no account required

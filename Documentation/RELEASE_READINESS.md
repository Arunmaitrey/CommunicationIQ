# Release Readiness

**Database:** MongoDB Atlas (shared cluster, `CommunicationIQ` control plane + `tenant_<slug>` per institution)
**Status:** All services connect to Atlas. No local MongoDB required.

---

## Database Setup (Atlas Only)

The application uses **MongoDB Atlas** exclusively. No local MongoDB installation is needed.

### Connection String

Set `MONGO_URI` in `backend/.env`:

```
MONGO_URI=mongodb+srv://<user>:<password>@<cluster>.mongodb.net/CommunicationIQ?retryWrites=true&w=majority
```

### Architecture

- **Control plane** (`CommunicationIQ` DB): platform users, tenants, plans, providers, configs, audit logs
- **Tenant DBs** (`tenant_<slug>`): users, profiles, sections, task items, attempts, scores, etc.
- Each institution is fully isolated in its own database

---

## Login Credentials

All passwords: `password123`

### Platform Staff

| Email | Role | Redirect |
|---|---|---|
| admin@saashx.ai | super_admin | /platform |

### St Mary's Institute (stmarys)

| Email | Role | Redirect |
|---|---|---|
| admin@stmarys.edu | tenant_admin | /tenant |
| aarav.reddy1@stmarys.edu | student | /home |
| (30 students total) | student | /home |

### Vignan University (vignan)

| Email | Role | Redirect |
|---|---|---|
| admin@vignan.edu | tenant_admin | /tenant |
| aarav.reddy1@vignan.edu | student | /home |
| (12 students total) | student | /home |

---

## Running on Another System

### Prerequisites
- Python 3.12+
- Node.js 18+
- MongoDB Atlas connection (no local DB needed)

### Backend
```bash
cd backend
python -m venv .venv
.venv/Scripts/activate  # Windows
pip install -r requirements.txt
# Set MONGO_URI in .env to your Atlas connection string
uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload
```

### Frontend
```bash
cd frontend
npm install
npm run dev  # Runs on port 3010
```

---

## What's Shipped

| Area | Status |
|---|---|
| Authentication | Login, signup, JWT tokens, password change, preferences |
| Roles | 3 roles: super_admin, tenant_admin, student |
| Exam Engine | LSRW (Listening, Speaking, Reading, Writing) with AI scoring |
| Company Rounds | Accenture, Cognizant, Infosys, TCS, Wipro style rounds |
| Anti-Proctoring | Right-click disable, copy/paste block, screenshot shortcuts, visual notice |
| Exam Resume | In-progress detection, resume button, runner recovery |
| Student Review | 5-star rating, comment, difficulty feedback after exams |
| Question Bank | CRUD for 6 categories (reading, writing, listening, speaking, grammar, vocabulary) |
| Company Questions | TCS, Infosys, Wipro, Accenture, Cognizant specific content |
| User Management | Create/edit/deactivate users, reset passwords (tenant admin) |
| Profile Editing | Student profile with full name, roll number, branch, year, L1 language |
| Home Page | Quick actions, recent activity, tips |
| Gamification | XP, badges, streaks, daily quests |
| Audit Logging | All write operations logged |
| Tenant Isolation | Database-per-tenant, cross-tenant queries impossible |

---

## Frontend Pages (31 routes)

### Public
| Route | Description |
|-------|-------------|
| `/` | Home / landing page |
| `/login` | Sign in |
| `/signup` | Student self-registration |
| `/invite/[token]` | Invitation claim flow |

### Student
| Route | Description |
|-------|-------------|
| `/home` | Dashboard with quick actions, recent activity, tips |
| `/tests` | Take a test (with resume for in-progress attempts) |
| `/practise` | Practice drills |
| `/my-progress` | Progress and mastery |
| `/quiz` | Quiz module |
| `/listening` | Listening module |
| `/reading` | Reading module |
| `/writing` | Writing module |
| `/skills` | Skills view |
| `/settings` | Profile editing, notification preferences, password change |
| `/consent` | Recording consent |
| `/results/[id]` | Exam results with review/rating |
| `/attempt/[id]/check` | Mic check before exam |
| `/attempt/[id]/run` | Exam runner with anti-proctoring |
| `/simulate` | Test selection |
| `/season` | Season/league view |
| `/progress` | Progress view |

### Tenant Admin
| Route | Description |
|-------|-------------|
| `/tenant` | Institution overview |
| `/tenant/users` | User management (create, edit, deactivate, reset password) |
| `/tenant/profiles` | Assessment profiles |
| `/tenant/results` | Exam results |
| `/tenant/readiness` | Readiness dashboard |

### Platform Super Admin
| Route | Description |
|-------|-------------|
| `/platform` | Platform overview |
| `/platform/tenants` | Institution management |
| `/platform/results` | Cross-tenant exam results |
| `/platform/content` | Question bank (add/edit/delete for all 6 categories) |
| `/platform/audit` | Audit log |

---

## Verification

- **Backend:** 36/36 modules compile clean
- **Frontend:** 31 pages build successfully, zero TypeScript errors
- **Roles:** 3 roles only (super_admin, tenant_admin, student)
- **Data:** All users have consent, profiles, and linked data
- **DB Export:** `communicationiq_full_export.json` available

---

## Known Limitations

- **Tier 0 only** by default: pronunciation, accuracy, grammar, and content scoring require the speech engine from `requirements-engine.txt`
- **Local storage only**: `MEDIA_ROOT` points to `../tmp`; S3-class object storage is not yet wired
- **Narration**: requires an OpenAI-compatible server or Anthropic API key
- **IRT adaptive selection**: implemented, dormant until score data accrues

# Database Documentation

## MongoDB Architecture

CommunicationIQ uses **MongoDB Atlas** with a database-per-tenant architecture for structural tenant isolation.

### Databases

| Database | Purpose | Contents |
|----------|---------|----------|
| `CommunicationIQ` | Control plane | Plans, tenants, providers, platform users, audit |
| `tenant_stmarys` | St Mary's Institute | Students, attempts, scores, profiles, gamification |
| `tenant_vignan` | Vignan Degree College | Students, attempts, scores, profiles, gamification |

Each institution database contains the same collections — they are isolated at the database level.

### Control Plane Collections

| Collection | Purpose |
|-----------|---------|
| `tenants` | Institution registry (slug, name, status, plan, branding) |
| `platform_users` | Platform staff accounts (email, password_hash, role) |
| `plans` | Pricing templates (code, billing_model, price, features) |
| `provider_registry` | AI provider catalog (capability, tier, active) |
| `provider_configs` | Active provider selections (per capability, per tenant) |
| `audit_log` | Immutable audit trail (actor, action, entity, before/after) |
| `gamification_config` | XP/league/streak rules |
| `tenant_user_directory` | Cross-tenant user directory for lookups |

### Tenant Database Collections

Each `tenant_<slug>` database contains:

| Collection | Purpose |
|-----------|---------|
| `users` | Student/teacher accounts (email, full_name, role, password_hash) |
| `profiles` | Simulation profiles (name, description, section list, published) |
| `profile_sections` | Section definitions within profiles |
| `task_items` | Item bank (read-aloud, repeat sentence, short answer, etc.) |
| `quiz_items` | Grammar/vocabulary quiz questions (stem, options, correct) |
| `reading_passages` | Reading comprehension passages with MCQs |
| `listening_passages` | Listening comprehension passages with MCQs |
| `writing_prompts` | Writing prompts (essay, email) |
| `attempts` | Simulation attempt records (status, scores, timestamps) |
| `responses` | Individual response records |
| `response_audio` | Audio file references |
| `section_results` | Per-section scoring |
| `score_records` | Dimension scores |
| `skill_mastery` | Per-skill mastery tracking |
| `consent_records` | Student consent tracking (recording, AI explanation) |
| `cohorts` | Student cohorts (branch, year, section) |
| `cohort_members` | Cohort membership |
| `invitations` | Student invitation tokens |
| `drills` | Practice drill definitions |
| `mistake_bank_entries` | Common mistakes for remediation |
| `xp_ledger` | Experience point transactions |
| `streak_states` | Daily engagement streaks |
| `quests` | Daily challenge definitions |
| `badges` | Achievement badges |
| `earned_badges` | Badge awards |
| `engagement_events` | Student engagement tracking |
| `season_plans` | Placement season planning |
| `student_flags` | Trainer flags for intervention |

### Indexes

Beanie handles indexes via the `Settings` inner class on each Document. Additional indexes are created by `ensure_indexes()` at startup and during provisioning.

### Data Lifecycle

- **Students** are created on first login via the invitation flow or self-signup
- **Attempts** are created when a student starts a simulation
- **Scores** are computed after submission (synchronous + background)
- **Recordings** are retained per `RECORDING_RETENTION_DAYS` and cleaned by `retention.py`
- **Narrations** are generated asynchronously after scoring
- **Consent** must be granted before any recording begins

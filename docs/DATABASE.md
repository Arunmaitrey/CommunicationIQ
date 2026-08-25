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

#### plans
Pricing templates for institutions.
- `code` (string, indexed): plan identifier (e.g., "pilot", "seat_standard")
- `name`: display name
- `billing_model`: per_seat | flat | usage | pilot
- `price_per_seat`, `price_flat`: pricing
- `attempt_allowance`: simulations per cycle
- `features`: JSON map of enabled features

#### tenants
Institution registry.
- `slug` (string, unique, indexed): database routing key
- `name`: institution name
- `status`: active | trial | suspended | offboarding | closed
- `plan_id`: FK to plans
- `seat_limit`: max concurrent students
- `branding`: JSON (theme, logo)
- `season_start`, `season_end`: placement season dates

#### platform_users
Platform staff accounts.
- `email` (string): login identifier
- `password_hash`: bcrypt hash
- `role`: super_admin | finance | content

#### provider_registry
AI provider catalog.
- `capability`: vad | asr | pronunciation | accuracy | grammar | content_relevance | fluency
- `provider_key`: unique identifier
- `tier`: 0 (always available) or 1 (requires models)
- `active`: whether provider is enabled

#### provider_configs
Active provider selections (per capability, optionally per tenant).
- `capability`, `tenant_id`: routing key
- `primary_provider_id`, `fallback_provider_id`: provider routing

#### subscriptions
Tenant-plan bindings.
- `tenant_id`, `plan_id`: relationship
- `status`: trialing | active | past_due | cancelled

#### audit_log
Immutable audit trail.
- `actor_type`, `actor_id`, `actor_label`: who
- `action`: event name (e.g., "tenant.created")
- `entity`, `entity_id`: what was affected
- `before`, `after`: JSON snapshots

### Tenant Database Collections

Each `tenant_<slug>` database contains:

| Collection | Purpose |
|-----------|---------|
| users | Student accounts |
| simulation_profiles | Test blueprints |
| profile_sections | Section definitions within profiles |
| task_items | Item bank (read-aloud, repeat sentence, etc.) |
| quiz_items | Grammar/vocabulary quiz questions |
| attempts | Simulation attempt records |
| responses | Individual response records |
| response_audio | Audio file references |
| section_results | Per-section scoring |
| score_records | Dimension scores |
| skill_mastery | Per-skill mastery tracking |
| listening_passages | Listening comprehension passages |
| reading_passages | Reading comprehension passages |
| writing_prompts | Writing prompts |
| invitations | Candidate invitation tokens |
| consent_records | Student consent tracking |
| cohorts | Student cohorts |
| cohort_members | Cohort membership |
| drills | Practice drill definitions |
| mistake_bank | Common mistakes for remediation |
| xp_ledger | Experience point transactions |
| streak_state | Daily engagement streaks |
| quests | Daily challenge definitions |
| badges | Achievement badges |
| earned_badges | Badge awards |
| league_memberships | Competitive league assignments |
| gamification_configs | Institution gamification settings |
| student_flags | Trainer flags for intervention |

### Indexes

Beanie handles indexes via the `Settings` inner class on each Document. Additional indexes are created by `ensure_indexes()` at startup and during provisioning.

### Data Lifecycle

- **Students** are created on first login via the invitation flow
- **Attempts** are created when a student starts a simulation
- **Scores** are computed after submission (synchronous + background)
- **Recordings** are retained per `RECORDING_RETENTION_DAYS` and cleaned by `retention.py`
- **Narrations** are generated asynchronously after scoring

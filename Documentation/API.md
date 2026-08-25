# API Documentation

Base URL: `http://localhost:8000/api/v1`

## Authentication

All protected endpoints require `Authorization: Bearer <token>` header.

Tokens are obtained via `POST /api/v1/auth/login`.

### Token Payload

```json
{
  "scope": "tenant",
  "role": "student",
  "tenant_slug": "stmarys",
  "user_id": "uuid"
}
```

---

## Auth

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/auth/login` | No | Login with email/password, returns JWT |

---

## Student

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/student/home` | Student | Dashboard data |
| GET | `/student/skills` | Student | Skill mastery breakdown |
| GET | `/student/profiles` | Student | Available simulation profiles |
| POST | `/student/consent` | Student | Grant recording consent |

---

## Attempts

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/student/attempts` | Student | Create new attempt |
| GET | `/student/attempts/resume` | Student | Resume pending attempt |
| GET | `/student/attempts` | Student | List attempts |
| GET | `/student/attempts/{id}/runner` | Student | Get attempt configuration for frontend runner |
| POST | `/student/attempts/{id}/env-check` | Student | Pre-flight environment check |
| POST | `/student/attempts/{id}/responses/{rid}/prompt` | Student | Serve next prompt audio |
| POST | `/student/attempts/{id}/responses/{rid}/audio` | Student | Upload recorded audio |
| POST | `/student/attempts/{id}/responses/{rid}/answer` | Student | Submit text answer |
| POST | `/student/attempts/{id}/responses/{rid}/skip` | Student | Skip question |
| POST | `/student/attempts/{id}/submit` | Student | Submit attempt for scoring |
| GET | `/student/attempts/{id}/result` | Student | Get scored results |
| GET | `/student/attempts/{id}/export.csv` | Student | Export results as CSV |

---

## Listening

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/student/listening/passages` | Student | List listening passages |
| POST | `/student/listening/passages/{id}/start` | Student | Start listening attempt |
| GET | `/student/listening/attempts/{id}/questions` | Student | Get listening questions |
| POST | `/student/listening/attempts/{id}/submit` | Student | Submit listening answers |

---

## Reading

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/student/reading/passages` | Student | List reading passages |
| POST | `/student/reading/passages/{id}/start` | Student | Start reading attempt |
| GET | `/student/reading/attempts/{id}/questions` | Student | Get reading questions |
| POST | `/student/reading/attempts/{id}/submit` | Student | Submit reading answers |

---

## Writing

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/student/writing/prompts` | Student | List writing prompts |
| POST | `/student/writing/prompts/{id}/submit` | Student | Submit writing response |
| GET | `/student/writing/submissions` | Student | List writing submissions |

---

## Game / Gamification

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/student/game` | Student | Full game state (XP, streak, badges, quests) |
| GET | `/student/game/ledger` | Student | XP transaction history |
| GET | `/student/game/badges` | Student | Earned badges |

---

## Quiz / Practice

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/student/quiz/next` | Student | Next quiz question |
| POST | `/student/quiz/submit` | Student | Submit quiz answer |
| GET | `/student/mistakes` | Student | Mistake bank entries |
| GET | `/student/drills` | Student | Practice drills |
| POST | `/student/drills` | Student | Create custom drill |
| POST | `/student/drills/{id}/complete` | Student | Mark drill complete |

---

## Trainer

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/trainer/cohorts` | Admin | List cohorts |
| GET | `/trainer/cohorts/{id}/readiness` | Admin | Cohort readiness metrics |
| GET | `/trainer/cohorts/{id}/students` | Admin | Students in cohort |
| GET | `/trainer/students/{id}/attempts` | Admin | Student attempt history |
| GET | `/trainer/attempts/{id}/result` | Admin | Detailed attempt result |
| GET | `/trainer/students/{id}/mastery` | Admin | Skill mastery breakdown |
| GET | `/trainer/flags` | Admin | Student intervention flags |
| POST | `/trainer/flags` | Admin | Create flag |
| POST | `/trainer/flags/{id}/resolve` | Admin | Resolve flag |
| GET | `/trainer/momentum` | Admin | Cohort momentum overview |

---

## Tenant Admin

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/tenant/overview` | Tenant admin | Institution overview |
| GET | `/tenant/users` | Tenant admin | List users |
| POST | `/tenant/users` | Tenant admin | Create user |
| PATCH | `/tenant/users/{id}` | Tenant admin | Update user |
| POST | `/tenant/users/{id}/reset-password` | Tenant admin | Reset password |
| POST | `/tenant/users/import/preview` | Tenant admin | Preview CSV import |
| POST | `/tenant/users/import` | Tenant admin | Execute CSV import |
| GET | `/tenant/cohorts` | Tenant admin | List cohorts |
| POST | `/tenant/cohorts` | Tenant admin | Create cohort |
| PATCH | `/tenant/cohorts/{id}` | Tenant admin | Update cohort |
| POST | `/tenant/cohorts/{id}/members` | Tenant admin | Add member to cohort |
| GET | `/tenant/profiles` | Tenant admin | List simulation profiles |
| POST | `/tenant/profiles` | Tenant admin | Create profile |
| PUT | `/tenant/profiles/{id}` | Tenant admin | Update profile |
| POST | `/tenant/profiles/{id}/clone` | Tenant admin | Clone profile |
| POST | `/tenant/profiles/{id}/status` | Tenant admin | Publish/unpublish profile |
| GET | `/tenant/season` | Tenant admin | Season status |
| GET | `/tenant/seats` | Tenant admin | Seat usage |
| GET | `/tenant/assignments` | Tenant admin | List assignments |
| POST | `/tenant/assignments` | Tenant admin | Create assignment |
| DELETE | `/tenant/assignments/{id}` | Tenant admin | Remove assignment |
| GET | `/tenant/invitations` | Tenant admin | List invitations |
| POST | `/tenant/invitations` | Tenant admin | Create invitation |
| POST | `/tenant/invitations/{id}/withdraw` | Tenant admin | Withdraw invitation |
| GET | `/tenant/invitations/{id}/result` | Tenant admin | Invitation result |

---

## Platform Admin

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/platform/overview` | Platform | Dashboard overview |
| GET | `/platform/tenants` | Platform | List all tenants |
| POST | `/platform/tenants` | Platform | Create tenant |
| PATCH | `/platform/tenants/{id}` | Platform | Update tenant |
| GET | `/platform/plans` | Platform | List plans |
| POST | `/platform/plans` | Platform | Create plan |
| PATCH | `/platform/plans/{id}` | Platform | Update plan |
| POST | `/platform/plans/{id}/version` | Platform | Version plan |
| GET | `/platform/capabilities` | Platform | AI provider capabilities |
| PUT | `/platform/capabilities/{cap}` | Platform | Update provider config |
| GET | `/platform/audit` | Platform | Audit log |
| GET | `/platform/gamification` | Platform | Gamification config |
| PUT | `/platform/gamification` | Platform | Update gamification config |
| GET | `/platform/narration/settings` | Platform | Narration settings |
| PUT | `/platform/narration/settings` | Platform | Update narration settings |
| GET | `/platform/narration/metrics` | Platform | Narration job metrics |
| POST | `/platform/providers` | Platform | Register provider |
| PATCH | `/platform/providers/{id}` | Platform | Update provider |
| POST | `/platform/providers/{id}/active` | Platform | Toggle provider |
| GET | `/platform/tenant-types` | Platform | Tenant type catalog |
| GET | `/platform/tenants/{id}/export.zip` | Platform | Export tenant data |
| GET | `/platform/assets/{key}` | Public | Serve static assets |

---

## Public (Unauthenticated)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/invite/{token}` | No | Validate invitation token |
| POST | `/invite/{token}/claim` | No | Claim invitation |
| GET | `/healthz` | No | Health check |
| GET | `/meta/capability` | No | Engine tier capability |

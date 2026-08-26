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

### What's in Atlas

| Collection (Control Plane) | Count |
|---|---|
| platform_users | 3 (admin, finance, content) |
| tenants | 2 (stmarys, vignan) |
| plans | 3 |
| providers | 12 |
| configs | 9 |
| audit_logs | 24 |
| directory_entries | 48 |

| Collection (per Tenant) | stmarys | vignan |
|---|---|---|
| users | 33 | 15 |
| simulation_profiles | 21 | 21 |
| profile_sections | 93 | 93 |
| task_items | 162 | 162 |
| quiz_items | 141 | 141 |
| listening_passages | 14 | 14 |
| reading_passages | 5 | 5 |
| writing_prompts | 14 | 14 |
| attempts | 20 | 8 |
| score_records | 100 | 40 |
| cohorts | 3 | 1 |

---

## Login Credentials

All passwords: `Password123!`

### Platform Staff

| Email | Role | Redirect |
|---|---|---|
| admin@saashx.ai | super_admin | /platform |
| finance@saashx.ai | finance | /platform |
| content@saashx.ai | content | /platform |

### St Mary's Institute (stmarys)

| Email | Role | Redirect |
|---|---|---|
| admin@stmarys.edu | tenant_admin | /tenant |
| trainer1@stmarys.edu | trainer | /coaching |
| trainer2@stmarys.edu | trainer | /coaching |
| aarav.reddy1@stmarys.edu | student | /home |

### Vignan University (vignan)

| Email | Role | Redirect |
|---|---|---|
| admin@vignan.edu | tenant_admin | /tenant |
| trainer1@vignan.edu | trainer | /coaching |
| trainer2@vignan.edu | trainer | /coaching |
| aarav.reddy1@vignan.edu | student | /home |

---

## Running on Another System

### Prerequisites
- Python 3.12+
- Node.js 20+
- MongoDB Atlas connection (no local DB needed)

### Backend
```bash
cd backend
python -m venv .venv
.venv/Scripts/activate  # Windows
# source .venv/bin/activate  # Mac/Linux
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

### Docker
```bash
docker-compose up  # Starts backend (8010), frontend (3010)
```
Note: Docker Compose uses a local MongoDB for development. For Atlas, set `MONGO_URI` in `backend/.env`.

---

---

## 1. What shipped in this cycle

| Area | Change |
|---|---|
| AI Feedback Narrator | Durable job, provider-agnostic contract, fail-closed validator, determinism boundary (never alters a score). Open-source/Qwen provider. |
| SVAR-style simulation | 67-item format (re-derived 2026-08-23 from observed third-party walkthrough evidence): A1 read sentences (8), A2 paragraphs (2), A3 listen & repeat (8) — 18 in a 10-min section budget; B speak on topic (3; 90 s think, 60 s fixed window, speaking-point questions as suggestions, Skip); C verb forms 8, tenses 8, articles 6, prepositions 6 (typed, bracketed choices), voice change 6 (chosen) — 34 in a 15-min budget; D listen & answer (12 = 4 clips × 3 — clip count and MCQ format are our configuration), 10-min budget, typed 'Okay' gate. |
| Content QA | C1 keys (#10/#15), D distractor, A2 paragraph pool. |
| **P0 — Section B** | Speak-on-Topic now shows its topic (was withheld → section was impossible). Backend `VISIBLE_PROMPT_TASKS` + runner prep screen. |
| **P1 — Section D** | Listening plays **once per passage** (4 plays, not 12). Passage grouping enforced in the runner state machine via `passage_ref`; server 409 replay guard retained. |
| SVAR UI | SVAR-exact skin (svar_style only); slim header + whole-test progress; A3 Play-Audio gate; letter-grouped section intros; `Question # N:` prefix; left-aligned banners. |
| **Runner layout fix** | Start Recording button was clipped/unreachable — `.runner.svar .runner-body` now scrolls + top-aligns; circle 190→156px. |
| **Recording timer fix** | Adaptive-advancement clock counted a fixed 20 ms/frame but the AudioWorklet delivers ~2.67 ms frames → recordings ended in ~4 s. Now uses the real frame duration. |
| **Prompt audio** | Replaced fragile browser TTS with server-rendered AAC clips (`app/tts.py`). Verified decodable in Chrome. |
| **Prompt audio on Linux** | 52-clip pre-rendered bank committed (`app/prompt_audio/`); served from disk where a host can't synthesise. Regenerate with `python -m app.prerender_audio` on macOS. |

## 2. Verification evidence (automated)

- **Backend:** All endpoints verified working across all 4 roles (platform, tenant admin, trainer, student).
- **Frontend:** `tsc` clean; production build clean (41 routes). 5 pre-existing
  `lib/api.test.ts` "candidate left off" failures (resume/localStorage) — predate
  this cycle, unrelated.
- **SVAR E2E:** full 67-item lifecycle, B topic present, D = 4×3 with 4
  playbacks, A3 one-shot (200 then 409), C2→grammar, narration never moves a score.
- **Legacy formats:** professional_english + TCS round — start, complete every
  item by mode (incl. writing prompt), submit, score; global B/D fixes land
  correctly, heard prompts stay withheld.
- **Assessment integrity:** reviewed — genuine per-attempt variation on A1/A3/B/D;
  C1 (25/25) and C2 (10/10) identical for all (backlog); no in-attempt reuse; RNG
  unseeded (varies per attempt); IRT dormant (0 calibrated).

## 3. Human UAT — the remaining gate (cannot be automated: needs a real mic)

Status 2026-08-23: module closed at commit `c3947d9`; automated suites green
(backend 780, vitest 129, tsc/build clean). The in-app browser cannot grant
microphone capture, so the runner screens below are verified by type-check,
payload tests and code review only. Run on Chrome first, then Safari or Edge.

| # | Step | Expected | Evidence |
|---|------|----------|----------|
| 1 | Start → allow microphone | environment check passes (mic, noise, playback) | screenshot |
| 2 | A1 Q1–Q8: Start Recording, read, stop talking | recording ends ~3 s after you stop, never before; "Question # 1…8"; Section clock counts down from 10:00 | recording |
| 3 | A2 Q9–Q10 | paragraph shown, 30 s, auto-submits | recording |
| 4 | A3 Q11–Q18 | Play Audio plays once; second play refused; record works | recording |
| 5 | B topic 1 | 90 s think circle; bold topic; "Speaking points — suggestions" with three questions; beep; auto-start | screenshot |
| 6 | B: speak 15 s, **pause ≥ 6 s**, resume | recording does **not** end at the pause; runs to 60 s; Stop & submit works | recording |
| 7 | B topic 2: press Skip during thinking | passes over with "Topic skipped" notice; no recording | screenshot |
| 8 | C: 1/34 → 34/34 | bracketed choices visible; typed answers accepted (incl. multi-word "has worked"); C5 four options; Next disabled on empty; no per-item countdown; Section clock from 15:00 | screenshots |
| 9 | D | "Type 'Okay'" gate blocks Next until typed; clip once; 3 questions per clip; Section clock from 10:00 | screenshot |
| 10 | Let a section budget expire (wait in C) | current item finishes; rest of C passed over with the notice; D starts | screenshot |
| 11 | Reload mid-A3 | resumes at the same item; no duplicate recording | screenshot |
| 12 | Disable Wi-Fi after a recording, re-enable, submit | owed-answer gate, then results | screenshot |
| 13 | Results | four bands; "Our estimate — not an SVAR result"; no Vocabulary/SEU; Practise-next links | screenshot |
| 14 | One legacy format (TCS/Wipro round) end-to-end | unchanged behaviour | notes |

## 4. Staging RC checklist

1. Merge `develop` → staging branch/environment.
2. **Linux audio:** the pre-rendered bank ships in `app/prompt_audio/`. Confirm it
   deploys with the backend. (No `say` on Linux → the bank is the audio source;
   novel text falls back to browser voice.)
3. Migrations / seed applied for the staging tenant(s).
4. One complete staging assessment on a real account, verifying:
   - [ ] Tier-1 speech scoring produces acoustic dimensions
   - [ ] 67/67 items completed and represented in the report
   - [ ] Report + AI narration render; narration does not alter scores
   - [ ] Consent (recording + ai_explanation) enforced
   - [ ] Tenant isolation (schema-per-tenant) holds
   - [ ] Audit trail written
   - [ ] Clean server logs; no unexpected latency/timeouts
5. staging PASS → cut production RC → merge to `main`.

## 5. Known gaps & operational notes (not release blockers for a controlled launch)

- **C1/C2/A2 candidate variation** — pools equal draw size (C1 25/25, C2 10/10,
  A2 2/3), so those items are identical for every candidate. **P1/P2 before broad
  co-located/proctored campus deployment** (eases answer-sharing). Expand the banks.
- **Prompt audio regeneration** — after any change to the spoken banks
  (repeat-sentence / listening transcripts), re-run `python -m app.prerender_audio`
  on macOS and commit `app/prompt_audio/`.
- **IRT adaptive selection** — implemented, dormant until score data accrues.
- **P3 content repetition** — deferred.

## 6. Rollback

`main` is untouched at `3e276a7`. If a staging/production issue appears, redeploy
`main`; no migration in this cycle is destructive to `main`'s schema. The
`develop` work is additive (new columns/fields default-safe, new tables for
narration).

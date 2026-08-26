# Communication IQ

Placement-readiness assessment and training. Versant-, SVAR- and SpeechX-*style*
simulations with the real thing's timing and one-shot pressure — then the part
the real thing never gives you: why the score is what it is, and the one change
that moves it most.

Requirements live in [`Documentation/BRD_FRS_v1.0.md`](Documentation/BRD_FRS_v1.0.md).
The build plan lives in [`PLAN.md`](PLAN.md). This file is how to run it.

**Current state: M0 through M6 built.** A student consents,
passes an environment check, takes a timed simulation with one-shot prompts,
and gets a report built from a real transcript: what they said, where they
paused, which words did not come back, and their own recording played back
with the words on the timeline. M0 (four consoles, sixteen themes,
per-institution schemas, provider contracts) and M1 (the attempt lifecycle)
are underneath it.

---

## Prerequisites

- PostgreSQL 18 on `localhost:5432` (user `postgres`, password `password`)
- Python 3.12
- Node 20+

## Run it

```bash
# backend — http://localhost:8010
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt   # Linux/macOS: .venv/bin/pip
cp .env.example .env       # edit MONGO_URI and JWT_SECRET
.venv/Scripts/python -m uvicorn app.main:app --port 8010 --reload
```

```bash
# frontend — http://localhost:3010
cd frontend
npm install
npm run dev
```

API docs: <http://localhost:8010/docs>

### Demo accounts

Password for all: `Password123!`

| Role | Email |
|---|---|
| Student | `aarav.reddy1@stmarys.edu` |
| Trainer | `trainer1@stmarys.edu` |
| Institution admin | `admin@stmarys.edu` |
| Platform | `admin@saashx.ai` |
| Second institution | `admin@vignan.edu` |

Two institutions exist on purpose. With one, cross-tenant isolation would
pass no matter what the code did.

## What the engine measures — and what it does not

| Scored | From |
|---|---|
| **Pronunciation** | goodness-of-pronunciation: wav2vec2 posteriors under forced alignment to the target text |
| **Word accuracy** | the transcript aligned against the item's reference text |
| **Fluency** | syllable-nuclei rate, phonation ratio, pause structure |
| **Response speed** | milliseconds from the tone to the first speech frame |
| **Hesitation** | fillers, repeated words and false starts in the transcript |
| **Grammar** | high-frequency error patterns, on free speech only |
| **Content** | key-point coverage against the rubric the item author wrote |

**Every score is labelled uncalibrated, and that is enforced in code.**
`app/engine/calibration.py` holds the state; nothing is calibrated until a
validation study produces a fit clearing every gate — rater agreement ICC
≥0.70, correlation ≥0.60, MAE ≤8 points, and L1-group bias ≤3 points. Until
then the composite overall renders greyed and badged, and the report leads
with what has not been checked. Moving to "calibrated" is not a config flag;
it requires the ratings.

Run the study with `python -m app.validate` — see "Validation" below.
Protocols: [MIC_SMOKE_TEST.md](Documentation/MIC_SMOKE_TEST.md) then
[VALIDATION_PROTOCOL.md](Documentation/VALIDATION_PROTOCOL.md).

Four more things about how the measures work:

**Pronunciation scores clarity, not nativeness.** It asks how confidently an
English recogniser heard each word — close to "would a listener catch it".
An accented speaker who articulates clearly scores well. It is character-level,
so it cannot yet name the specific sounds; per-phoneme confusion pairs
(DIAG-03) need a phoneme-output model.

**Accuracy is not pronunciation.** Accuracy asks whether the right words came
out; pronunciation asks how clearly they were said. A word can be recovered
correctly and still be mumbled.

**Grammar never flags Indian English.** "Prepone", "do the needful", "cousin
brother", "passed out of college" are features of a legitimate variety, not
mistakes. The exclusion list is as load-bearing as the rule list, and the tests
cover it. The check is a high-precision rule set, not a model, and the report
says so.

**Content is rubric-bound.** Retell coverage is measured against key points a
human author wrote down. An open response gets no content score at all —
there is no defensible way to grade an opinion — only a flag for whether the
prompt was addressed.

### The speech model

faster-whisper `small.en`, int8, on CPU. No API key, no audio leaving the host
— which is what keeps it compatible with the India-residency requirement
without a hosting decision attached. Set `WHISPER_MODEL=base.en` for roughly
three times the speed at some cost in accented-speech accuracy.

**Answers are scored as they arrive, not in a batch at submit.** A local model
runs at about 0.6× real time, so eight items scored at the end would be twenty
seconds of spinner. Scored on ingest, item four is transcribed while item five
is being spoken, and submit only composes what is already there.

Tier 0 stays registered as the automatic fallback. On a host where the model
will not load, latency and pause structure are still measured, the provider
console shows what actually served, and every score records which
implementation produced it.

## Validation

The question everything waits on: *does the AI score intelligibility the way
human listeners do?* Nothing in the codebase can answer it — only recordings
and raters can.

**Freeze the engine before collecting anything.** A study measures one version
of the scorer; if the scoring path changes while data is being collected, the
report refuses to emit a calibration and names what moved. That is mechanical
rather than procedural — it catches a nudged threshold nobody remembered to
mention, which is how a validation study quietly becomes a search for a number
you like.

Current baseline: **`validation-baseline-v2` — `7cb4b39ddff4056b`** (19 scoring
files plus model identities). Supersedes v1, which was frozen before timer
truncation was detected; no scoring arithmetic changed between them.

```bash
cd backend
.venv/Scripts/python -m app.validate freeze --study pilot-2026   # pin the engine
.venv/Scripts/python -m app.validate sheet  --study pilot-2026   # blank rating sheet
.venv/Scripts/python -m app.validate score  --study pilot-2026   # engine scores
.venv/Scripts/python -m app.validate report --study pilot-2026   # verdict
```

Recordings go in `tmp/validation/<study>/` with a `manifest.csv` giving
speaker, L1 and recording condition. The rating sheet deliberately contains no
machine score — a rater who can see the engine's answer is not an independent
check.

The report is built to be able to say no:

- **Rater agreement is checked first.** Below ICC 0.70 the verdict is
  *inconclusive*, not *fail* — if the humans do not agree with each other,
  nothing can be concluded about the machine either way.
- **Group bias is a hard gate.** An engine that correlates at 0.85 overall and
  sits five points low on every Tamil-L1 speaker fails, and the report says
  "fairness failure" in those words. Aggregate accuracy cannot buy past it.
- **No calibration is emitted for a dimension that missed any gate.**

Target set: 60 speakers (20 Telugu, 20 Hindi, 15 Tamil, 5 other), 8 recordings
each, 70% quiet / 20% realistic noise / 10% poor mic, on real budget Android
handsets. Five raters with hiring or training experience, 30% overlap for
agreement.

## Retention

Recordings carry a delete-by date taken from the student's own consent record.

```bash
cd backend && .venv/Scripts/python -m app.retention --dry-run
```

Drop `--dry-run` to delete. The audio goes; the feature record — transcript,
timings, pause structure — stays, so a student's diagnosis and progress history
outlive their voice. Offboarding an institution (`drop_tenant_schema`) removes
its recordings along with its schema.

---

## How it is put together

```
backend/app/
  db.py            two declarative bases; tenant tables address a `tenant`
                   placeholder that the session translates per request
  models/          platform.py (public) · tenant.py (per institution)
  routers/         auth · student · trainer · tenant_admin · platform_admin
  engine/
    contracts/     what every capability must do — written before any of them
    registry.py    which implementation runs, what happens when it fails
    providers/     tier0 (heuristic) · tier1 (local models) · tier2 (vendor)
  storage/         Storage contract + local `tmp/` implementation
  provisioning.py  the only code allowed to name a real schema

frontend/
  app/globals.css  16 themes as CSS variables — the design source of truth
  components/      ThemeProvider · ui.tsx · shell/
  lib/api.ts       the only file that knows the backend exists
```

### Three rules this codebase keeps

**One institution per schema, resolved from the token.** The application only
ever says `tenant`; the session translates it to `tenant_<slug>` using the slug
in the signed token. No endpoint accepts an institution identifier, so no
endpoint can be given the wrong one. There is deliberately no default tenant.

**No capability without its contract.** ASR, pronunciation, payments,
notifications and storage all sit behind versioned Protocols. Which
implementation serves a capability — and its fallback, its timeout, whether a
shadow copy runs — is a configuration row. Every score records the provider and
version that produced it.

**No literal colours in components.** Everything reads the CSS variables in
`globals.css`. A hardcoded hex is a bug in fifteen themes nobody looked at.

## Storage while we are in development

Recordings, prompt audio and exports go to `tmp/` at the repo root, gitignored,
behind the `Storage` contract. Audio is addressed by key and never by path, so
object storage later is a provider swap rather than a rewrite. Retention is
recorded per recording from the consent record, and the sweeper that acts on it
is live — see the Retention section above.

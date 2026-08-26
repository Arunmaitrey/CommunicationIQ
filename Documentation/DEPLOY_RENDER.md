# Deploying to Render

The whole stack is described in [`render.yaml`](../render.yaml) at the
repository root. Render reads it and creates the database and both services;
you set three values it cannot know in advance.

---

## The blueprint ships free-tier by default

`render.yaml` uses free plans throughout: no card, no disks, no paid
instances. **It deliberately leaves out the speech models**, and that is the
one thing to understand before you show it to anyone.

### What a free deployment does and does not do

**Works.** Sign-in and roles, the tenant and platform consoles, tenant
branding and logo upload, simulation profiles and company rounds, quizzes,
drills, gamification, the attempt runner end to end, and timing-based scoring
— response latency, speech rate, pauses.

**Does not work.** Transcription, pronunciation, accuracy, grammar, content.
Those need faster-whisper plus a wav2vec2 model through PyTorch: **2.5–3.5 GB
resident**. A 512 MB free instance is OOM-killed mid-request, which reaches a
student as a lost attempt. So the engine is omitted rather than installed and
killed.

**It says so.** Each affected dimension reports itself *unscored* with a
reason — never guessed. `GET /healthz` returns `engine.tier: 0` and lists what
is missing. The API logs a warning at boot. A free deployment is an honest
demo of the product's flows, not of its scoring.

### Two more free-tier facts

- Free services **sleep after ~15 minutes** idle; the next request waits
  30–60 seconds. Fine for a link you send someone, visibly wrong in front of
  a room of students.
- Free Postgres **expires after 30 days** and is deleted. Export anything you
  care about, or move to a paid database first.

### Turning scoring on

Three changes to `render.yaml`, all on `fluenzee-api`:

```yaml
plan: pro                       # standard (2 GB) is the floor; pro (4 GB) realistic
buildCommand: pip install --upgrade pip && pip install -r requirements.txt -r requirements-engine.txt
disk:
  name: fluenzee-media
  mountPath: /var/data
  sizeGB: 10
```

and set `MEDIA_ROOT=/var/data/media`, `HF_HOME=/var/data/hf`,
`WHISPER_WARM_ON_STARTUP=true`.

The disk is not optional once scoring is on. Render wipes the filesystem on
every deploy, so without it every recording disappears at the next push — and
listen-back, the retention sweeper and the validation study all read them
back. It also caches the model weights; without it, ~900 MB is re-downloaded
from Hugging Face on **every** deploy.

A disk pins the API to one instance. Scaling horizontally means moving audio
to object storage — which `app/storage` was built for, so it is a provider
swap rather than a rewrite.

---

## 1. Connect the repository

Render → **New → Blueprint** → connect GitHub → pick
`saashxailabs/CommunicationIQ` → it finds `render.yaml` and shows three
resources: `fluenzee-db`, `fluenzee-api`, `fluenzee-web`.

Approve. On free plans the build is quick — the heavy speech
dependencies are in a separate file that is not installed here.

## 2. Fill in the three values Render cannot infer

The blueprint marks these `sync: false`, which means "ask, do not commit".

**On `fluenzee-api`:**

| Variable | Value |
|---|---|
| `CORS_ORIGINS` | `["https://fluenzee-web.onrender.com"]` — a JSON array, using the web service's real URL |
| `APP_URL` | `https://fluenzee-web.onrender.com` |

**On `fluenzee-web`:**

| Variable | Value |
|---|---|
| `NEXT_PUBLIC_API_URL` | `https://fluenzee-api.onrender.com/api/v1` |

`JWT_SECRET` and `DATABASE_URL` are handled for you — generated and wired from
the database respectively.

> **`NEXT_PUBLIC_` values are baked in at build time, not read at runtime.**
> After setting it, use **Manual Deploy → Clear build cache & deploy**. A plain
> restart keeps serving the old value and the symptom is a frontend that
> cannot reach its API for no visible reason.

## 3. Set up demo data

The API connects to MongoDB Atlas on start and initializes the control plane.
Demo institutions and content are set up during initial deployment.

## 4. Check it came up

- `https://fluenzee-api.onrender.com/healthz` → `{"status":"ok",...}`
- `https://fluenzee-web.onrender.com/login` → the sign-in page
- `healthz` also reports the engine tier. On a free deployment expect
  `"engine": {"tier": 0, ...}` — that is correct, not a fault.

On a paid deployment with the engine installed, the check that matters is:
sign in, take a Read Aloud, and confirm a **pronunciation score comes back**.
If `healthz` says tier 1 but the dimension is still unscored, the model failed
to load at runtime — read the API logs rather than assuming the audio was bad.

---

## Things that will bite

**The database URL scheme.** Render publishes `postgres://`; the app speaks
asyncpg and needs `postgresql+asyncpg://`. `app/config.py` rewrites it, so
pasting Render's URL as-is is fine. Nothing to do — noted because the failure
it prevents is a driver error that names neither cause nor fix.

**`$PORT` is not optional.** Render assigns it. The frontend's `npm start`
script pins 3010, which is why the blueprint overrides the start command. Bind
anything else and the health check fails while the service runs perfectly.

**Region.** The blueprint uses `singapore` — closest Render region to India,
and the product is DPDP-facing. Moving the database without the services, or
vice versa, adds a round trip to every query.

**Certificates are not deployed.** `backend/certs/` is gitignored; it exists
only for LAN smoke testing, where `run-smoke-test.ps1` generates it. Render
terminates TLS itself.

---

## What is not covered here

**Object storage.** The single-instance limit above is the trade for keeping
audio on a disk. Swapping to S3 or R2 means implementing the `StorageProvider`
protocol in `app/storage/` and registering it — the contract exists precisely
so this does not touch any consumer.

**Backups.** Render backs up the database on paid plans. It does **not** back
up the disk, and that is where every student recording lives. Under DPDP the
retention sweeper deletes them on schedule anyway, but a disk failure between
a recording and its rating loses validation data that cannot be recollected.

**The scoring engine is still uncalibrated.** Deploying does not change that.
Every score remains labelled uncalibrated in the API and greyed in the UI
until the validation study runs — see
[VALIDATION_PROTOCOL.md](VALIDATION_PROTOCOL.md). Putting it on the internet
makes it reachable, not correct.

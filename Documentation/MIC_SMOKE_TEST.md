# Microphone smoke test — before recruiting anyone

**Purpose:** find out whether the capture path works on real hardware, with
5–10 people, before committing 60 speakers and 5 raters to a study.

This is the biggest remaining *engineering* unknown. The browser UI and live
microphone have never been exercised: every recording the engine has scored
so far was synthesised text-to-speech uploaded through the API. The runner,
the AudioWorklet capture, the WAV encoding, the one-shot prompt playback and
the listen-back are verified only by type-check, build and unit tests.

**Do not start the validation study until this passes.** A capture bug found
after 480 recordings means 480 wasted recordings.

---

## Setup

From the repository root:

```powershell
./run-smoke-test.ps1              # this machine only
./run-smoke-test.ps1 -Network     # HTTPS on the LAN, so phones can connect
```

Testers sign in as a seeded student (`aarav.reddy1@stmarys.edu` /
`Password123!`) or an account you create.

**`-Network` is required for phone testing, and it is not optional dressing.**
Browsers do not expose the microphone on a plain-HTTP origin, so a tester on a
phone pointed at your laptop's IP fails at the permission step for a reason
that has nothing to do with the product — and that failure looks exactly like
a real bug. The script generates a self-signed certificate; each device shows
a warning once. If `openssl` is unavailable it will tell you and suggest
`npx localtunnel --port 3010` instead.

**Each tester must accept the certificate twice, API first.** The script prints
the order. The API is a separate origin on port 8010 with the same self-signed
certificate, and a browser refuses background requests to an untrusted
certificate *silently* — no warning page, just a sign-in button that does
nothing. Visiting `https://<ip>:8010/healthz` and accepting the warning before
opening the app removes that failure entirely. Skip it and you will spend the
session debugging a phantom.

### Preflight — verified 18 Aug 2026

The launcher itself was broken in four ways, all found before any tester was
recruited, all fixed:

| What | Effect if it had reached a tester |
|---|---|
| Script was UTF-8 without a BOM; PowerShell 5.1 read it as Windows-1252, and the em dashes decoded to a smart quote that silently terminated strings mid-parse | `-Network` was honoured for the certificate and ignored for the servers: HTTP, bound to localhost, unreachable from any phone. The script is ASCII-only now |
| `OPENSSL_CONF` left pointing at a PostgreSQL path by an unrelated installer | No certificate at all |
| Address picked by lowest interface metric | Certificate issued for the Tailscale address `100.x`, which no phone on the office Wi-Fi can reach. Private LAN ranges are preferred now, and every local address goes into the certificate's SAN |
| `npx next dev` run from the repository root, which has no `package.json` | npx downloaded Next 16 and served an empty directory instead of the app |

Two more blockers sat behind them:

- **CORS.** `backend/.env` allows `http://localhost:3010` only, so every call
  from `https://<lan-ip>:3010` failed preflight with *Disallowed CORS origin* —
  the tester would have seen an unexplained network error at sign-in. The
  launcher now sets `CORS_ORIGINS` for the LAN origins in the environment,
  which takes precedence over the file without changing anything on disk.
- **Certificate acceptance order**, above.

With those fixed, a complete attempt was driven through the LAN HTTPS API —
sign-in, consent, attempt creation, environment check, one-shot prompts, eight
audio uploads, submit, report. All eight items scored; the transcript came back
exact; the report carried its uncalibrated labelling, a biggest lever and word
timings for listen-back.

**That verifies the server path, not the capture path.** The audio was
synthesised and pushed at the API. Nothing below still needs a real
microphone, a real device and a real person, which is the whole point of this
document.

The environment-check screen now warns about an insecure origin *before* the
tester presses anything, and shows which capture path the browser gave it
(`audioworklet` or `scriptprocessor`), the sample rate and the device name.
Those land in the database with the attempt, so a failure report arrives with
the facts attached.

## Who

5–10 people. At least:

- 2 on a laptop with its built-in microphone
- 2 on a budget Android phone (₹8–15K class — not a flagship)
- 1 on a phone with wired earphones
- 1 in a genuinely noisy room

Colleagues are fine for this. It is a capture test, not a language test.

## The path each tester walks

Sign in → consent screen → start a simulation → environment check → grant
microphone → speak the items → submit → wait for scoring → read the report →
open the listen-back and press play.

---

## Scenarios

Run each and record what happened. The "watch for" column is where I would
expect this to break first.

| # | Scenario | Watch for |
|---|---|---|
| 1 | **Laptop mic, quiet room** — the happy path | Does the level meter move while speaking? Is a transcript produced? |
| 2 | **Budget Android, quiet** | Does AudioWorklet initialise, or does it fall back to ScriptProcessor? Any silent failure? |
| 3 | **Fan / background voices** | Does the environment check warn? Does the report attribute it to the room rather than the speaker? |
| 4 | **Very short answer** — two words, then stop | Any dimension scored that should have said "too short to judge"? |
| 5 | **Long answer** — talk for the full 40s on Open Response | Does capture hold up? Does scoring stay under a few seconds? |
| 6 | **Silence** — say nothing at all | Does it report "nothing was recorded" rather than a low score? |
| 7 | **Stop exactly at the timer** — still speaking when it cuts | **The padding fix's real test.** Is the last word scored normally? |
| 8 | **Keep talking past the sentence** on Read Aloud | Does word accuracy penalise the extra words? Is that the behaviour you want? |
| 9 | **Deny the microphone permission** | Clear message with a way back, or a dead end? |
| 10 | **Revoke permission mid-attempt** (browser settings) | Does the runner say the microphone went, or fail obscurely? |
| 11 | **Reload the page mid-attempt** | Does the one-shot prompt refuse to replay? It should — that is server-enforced. |
| 12 | **Listen-back** | Does audio play? Do words highlight in time? Does tapping a word seek correctly? |

## Record for each run

Fill one of these per attempt. The first four fields come straight off the
environment-check screen, which prints them for exactly this reason.

| Field | |
|---|---|
| Tester, device model, browser, OS | |
| Scenario (1–12 below) | |
| Capture path | `audioworklet` / `scriptprocessor` / `none` |
| Sample rate | Hz, as shown on the check screen |
| Microphone | device label shown, and built-in / wired / Bluetooth |
| Permission granted? | yes / no — and what the prompt looked like |
| Recording start and stop | did the timer and the level meter both behave? |
| Did audio reach the API? | the upload returns `stored: true` with a duration — network tab, `/audio` request |
| Final report | overall, per-dimension, and whether it reads sensibly |
| Console errors | paste them |
| Network errors | status codes and which request |
| Notes | |

Keep the browser console open. A JavaScript error that does not surface in the
UI is exactly the class of bug this test exists to find.

### Classify every failure before fixing it

Which layer failed matters more than the symptom, because only one of these
categories is allowed to change the engine:

| Category | Looks like |
|---|---|
| **Environment / network** | wrong address, certificate not accepted, CORS, phone on a different network |
| **Browser permission** | the microphone was never granted, or was revoked |
| **Recorder / capture** | permission granted but no samples, silence, wrong sample rate, worklet failed to load |
| **API** | upload rejected, 4xx/5xx, timeout, attempt in the wrong state |
| **UI / reporting** | audio scored fine but the screen shows the wrong thing, or nothing |
| **Scoring / engine** | audio is good, transcript is good, and the number is still wrong |

The first five are fixed here and now. **A scoring/engine finding is not fixed
during the smoke test** — write it down, finish the session, and take it to the
validation study, which is the only thing that can tell you whether the number
is actually wrong or merely surprising. If a fix does end up touching the
scoring path, the frozen baseline has to be re-cut and said so out loud.

## What counts as passing

All twelve scenarios complete without a dead end, **and**:

- Scenario 7 produces a normal score for the final word. If the last word is
  consistently marked unclear, the padding fix is not working in the real
  capture path and everything about pronunciation is suspect.
- Scenario 6 says nothing was recorded rather than scoring silence low.
- Scenario 9 and 10 leave the tester with something to do next.
- Scenario 11 refuses the replay.
- No scenario produces a score with no audio behind it.

## What to do with failures

Fix them **before** freezing for the study — or, if a fix touches the scoring
path, re-freeze afterwards. `python -m app.validate freeze --study <name>`
will tell you the new fingerprint. Capture and UI fixes that leave the scoring
modules alone do not require a re-freeze, and the drift check will confirm
that rather than you having to reason about it.

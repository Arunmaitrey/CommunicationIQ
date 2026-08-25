# Release limitations

What this build has been proven to do, and what it has not. Written so nobody
has to infer the difference from a green test suite.

## The speech pipeline has been proven technically, not linguistically

The end-to-end tests drive a real `MediaStream` through `MediaRecorder`, encode
it, upload it, and score it. That proves the **path**:

- a browser can capture audio and encode it
- the upload survives a failure, a reload and a retry (`test_recovery_e2e.py`)
- the server decodes it, runs VAD, ASR, and every provider that follows
- responses, dimensions, skills and a report come out of the other end
- nothing 500s, and unmeasurable dimensions are reported as unmeasured rather
  than scored zero

The audio in those tests is a synthesised tone. It is not speech. So the
following are **unproven** and must not be described as working:

| Unproven | Why the synthetic path cannot show it |
|---|---|
| Real human speech reaches ASR intact | A tone exercises the codec, not the recogniser |
| ASR returns usable transcription | faster-whisper returns nothing usable from a tone, which is correct |
| Pronunciation and accuracy score sensibly | Both need a real transcript to align against |
| Completeness behaves correctly on real answers | Reference coverage needs recognised words |
| The trailing-silence threshold is right | `TRAILING_SILENCE_MS = 1800` is a guess; see below |

**What would settle it:** recordings of people reading the bank's prompts, put
through `app.silence` and through a normal attempt. Nothing in the codebase
needs to change first — the harness is built and refuses to answer on the
audio it has (`app/silence.py` detects a synthetic corpus and says so).

The synthetic E2E stays. It validates the upload and recovery path, which is
the part that silently loses a candidate's answer when it breaks.

## Nothing is validated against human judgement

No study has been run. In force until one is:

- **The engine weights** are not validated against human raters. Every report
  says so, and `calibrated` is `false` in every payload.
- **CEFR is indicative.** The band ships with a caveat stating that no
  concordance study exists and that it must not be accepted in place of a
  certificate.
- **`completeness` at `0.08`** in the weight set is a judgement, not a
  finding, and is documented as one beside the constant.
- **The `0.2 / 0.8` coverage/order split** in the Sentence Build construction
  scorer is likewise a judgement.

A ~60-speaker study with human ratings is what moves any of these. Until then
the numbers are useful for tracking a candidate against themselves and are not
a score to quote to a third party — which is what the product says on every
report.

## Prompt audio is synthesised

Every heard prompt is browser speech synthesis, not a recorded person. This
affects face validity in a customer demo and it affects listening items most.

## Deliberately deferred

Not built, on purpose, with the reasoning recorded in the code: typing,
spelling, professional tone, intelligibility.

## Retired assessments are hidden, not deleted

1,466 retired profiles remain in the demo estate. Retiring is how an assessment
leaves circulation and deleting one would orphan the results that name it, so
they stay, hidden from the library by default and reachable through "Show
retired". This is deliberate and is not cleanup that was skipped.

## Deployment

`autoDeploy: false` on both Render services, enforced by a test. Render's free
tier is 512 MB, which OOM-kills the Tier 1 speech models — a deployment there
returns blank scores, and that is the instance being too small rather than the
engine being broken. Deploying is a deliberate act from the dashboard.

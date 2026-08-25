# Validation study protocol

**The question:** does the engine score intelligibility the way human listeners do,
on real Indian English, fairly across L1 groups?

Everything in the product is gated on the answer. Until this runs, every score
is labelled uncalibrated in the API and greyed in the UI, and that is enforced
in `app/engine/calibration.py` rather than left to whoever writes the deck.

**Prerequisite:** the [microphone smoke test](MIC_SMOKE_TEST.md) must pass first.
Do not collect 480 recordings through an unproven capture path.

**Frozen engine:** `validation-baseline-v2` — `7cb4b39ddff4056b`.
Do not change the scoring path until the report is run. The drift check will
refuse to emit a calibration if it moves, and will name the file.

---

## 1. Participants

**60 speakers.**

| L1 | Speakers | Why |
|---|---|---|
| Telugu | 20 | Primary pilot geography |
| Hindi | 20 | Largest national group |
| Tamil | 15 | Distinct phonology — the group most likely to expose bias |
| Other (Kannada, Malayalam, Marathi, Bengali) | 5 | Breadth check |

Balance gender. Spread proficiency deliberately — roughly 20 weak, 25 middle,
15 strong by their trainer's judgement. A sample clustered in the middle
cannot show whether the engine separates anybody.

Final-year students from the pilot colleges are the right population: they are
who the product is for, and their scores are about to matter to them.

## 2. Consent

**Before any recording.** This is voice data under the DPDP Act and it is
being collected for research rather than for the participant's own benefit,
which makes the consent bar higher, not lower.

Each participant is told, in a language they read comfortably:

- what is recorded, and that they can stop at any point
- that recordings will be heard by up to five human raters
- how long recordings are kept and when they are deleted
- that participation is voluntary and refusing costs them nothing —
  **state explicitly that it does not affect placement support**, because a
  student asked by their own college will assume otherwise
- how to withdraw afterwards, and that withdrawal removes their recordings

Written consent, retained. A participant who withdraws has their recordings
deleted and their rows dropped from the analysis.

## 3. Recordings

**8 per speaker, 480 total.**

| Task | Count | Notes |
|---|---|---|
| Read Aloud | 3 | one easy, one medium, one long sentence |
| Repeat Sentence | 2 | 8-word and 16-word |
| Short Answer | 1 | |
| Story Retell | 1 | |
| Open Response | 1 | 40 seconds |

**Conditions:** 70% quiet room, 20% realistic background (corridor, ceiling
fan, other people), 10% deliberately poor microphone. Use the devices students
actually own — budget Android handsets, not a laptop in a meeting room. The
noisy subset is what tells you whether the SNR handling works or whether the
engine is quietly marking down anyone without a quiet room.

Capture through the product itself, so the study tests the real path.

**Manifest** at `tmp/validation/<study>/manifest.csv`:

```csv
recording_id,speaker_id,l1_language,task_type,reference_text,condition,file
r001_ra1,sp01,telugu,read_aloud,"The training session begins at nine.",quiet,r001_ra1.wav
```

## 4. Raters

**Five.** Indian English speakers with hiring, training or placement
experience — the people whose judgement the product claims to approximate.
Not linguists: the question is whether a hiring panel would follow the
candidate, not whether a phonetician approves.

**Every rater rates every recording** where the schedule allows; at minimum a
30% overlapping subset, which is what inter-rater agreement is computed on.
Agreement is computed only on recordings all five covered — a ragged matrix
would quietly become a different statistic.

**Rating is blind.** The sheet contains no machine score, enforced in code and
covered by a test. Randomise the order so raters do not drift in step with the
speaker sequence.

**Calibration session before rating starts:** all five rate the same 10
recordings together, discuss disagreements, then discard those ratings. This
is the cheapest way to lift ICC above the 0.70 gate, and without it the study
is likely to come back *inconclusive*.

### Rubric

Each recording, four dimensions, 1–5. Anchors are about the listener's
experience, not linguistic properties.

**Intelligibility** — *could you follow it?*

| | |
|---|---|
| 1 | Could not follow. Would ask them to repeat most of it. |
| 2 | Followed some, with effort and guessing. |
| 3 | Followed it, but had to concentrate. |
| 4 | Easy to follow. An occasional word took a moment. |
| 5 | Effortless. Would not think about it. |

**Pronunciation clarity** — *were the words distinct?*

| | |
|---|---|
| 1 | Individual words often unrecognisable. |
| 2 | Several words unclear enough to interrupt you. |
| 3 | Mostly clear; a few words needed working out. |
| 4 | Clear throughout. Accent present, comprehension unaffected. |
| 5 | Consistently crisp and easy to catch. |

**Fluency** — *did it flow?*

| | |
|---|---|
| 1 | Halting. Long pauses; hard to hold the thread. |
| 2 | Frequent hesitation that got in the way. |
| 3 | Some hesitation, thread intact. |
| 4 | Mostly smooth; natural pauses only. |
| 5 | Even and unforced. |

**Overall** — *would you pass them on communication?*

| | |
|---|---|
| 1 | Not ready for a communication round. |
| 2 | Would struggle. |
| 3 | Borderline. Could go either way on the day. |
| 4 | Would pass. |
| 5 | Would do well. |

**Brief the raters explicitly: accent is not a defect.** A strong regional
accent that you follow without effort is a 5. If the rating panel penalises
accent, the engine will be calibrated to penalise accent, and the study will
have installed the exact bias the product exists to avoid.

## 5. Running it

```bash
cd backend
.venv/Scripts/python -m app.validate freeze  --study pilot-2026   # already done
.venv/Scripts/python -m app.validate sheet   --study pilot-2026
# distribute rating_sheet.csv, collect completed sheets as ratings.csv
.venv/Scripts/python -m app.validate score   --study pilot-2026
.venv/Scripts/python -m app.validate report  --study pilot-2026
```

## 6. Gates

Every one is hard. A miss on any is a fail.

| Gate | Threshold | Why |
|---|---|---|
| Inter-rater agreement | ICC(2,k) ≥ 0.70 | Below this the ground truth is unusable and nothing else can be concluded — the report returns **inconclusive**, not fail |
| Pronunciation vs human clarity | r ≥ 0.60 | |
| Overall vs human overall | r ≥ 0.65 | |
| Error after calibration | MAE ≤ 8 points | Measured after the linear fit: an engine sitting 10 points low but tracking perfectly is calibratable |
| **L1 group fairness** | mean residual spread ≤ 3 points | An engine can correlate at 0.85 and still sit 5 points low on every Tamil speaker. Aggregate accuracy cannot buy past this |
| Noise degradation | < 10 points versus the same speaker's clean recording | |

## 7. Reading the outcome

**Pass** → calibrations are emitted for the dimensions that cleared every
gate. Install them, and those dimensions stop being labelled uncalibrated.
Dimensions that failed stay uncalibrated; the fits are per-dimension and
partial success is a real result.

**Fail** → useful information, not a disaster. The report names which gate and
by how much:

- *Low correlation, good agreement* → the engine measures something other than
  what listeners hear. Look at pronunciation first, then the composite weights.
- *Group bias* → the most serious outcome. Check whether ASR word-error rate
  differs by L1 group; accuracy inherits every ASR error, and that is the most
  likely channel.
- *High MAE, good correlation* → a scaling problem. The `POSTERIOR_FLOOR` and
  `POSTERIOR_CEILING` constants in the pronunciation provider were chosen by
  eye and are the first thing to refit.

**Inconclusive** → the raters did not agree. Re-run the calibration session,
tighten the anchors, and rate again. Do not touch the engine: nothing about it
has been measured.

## 8. Afterwards

Whatever the outcome, publish the report internally with the engine hash
attached, and keep the dataset. It becomes the regression set for every later
change to the scoring path — the second study is far cheaper than the first,
and the point of freezing is that the comparison stays meaningful.

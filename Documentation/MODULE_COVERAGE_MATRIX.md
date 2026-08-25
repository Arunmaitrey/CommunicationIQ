# Module Coverage Matrix

One row per assessment module. A module is **Working** only when all seven
stages hold on the running build:

`Question → Interaction → Capture → Processing → Evaluation → Scoring →
Persistence → Reporting`

`—` means the stage does not apply to that module (a written module has no
ASR).

---

## Speaking

| Module | Question | Interaction | Capture | Processing | Evaluation | Scoring | Persist | Report | Verdict |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|---|
| Read Aloud | ✅ 24 | ✅ | ✅ | ✅ ASR+align | ✅ | ✅ 5 dims | ✅ | ✅ | **Working** |
| Repeat | ✅ 28 | ✅ audio-only | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **Working** |
| Short Answer | ✅ 18 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **Working** |
| Sentence Build | ✅ 16 | ✅ | ✅ | ✅ | ⚠️ generic | ⚠️ no word-order dim | ✅ | ✅ | **Partial** |
| Story Retell | ✅ 6 | ✅ | ✅ | ✅ | ❗ merged | ❗ one axis | ✅ | ✅ | **Incorrect** |
| Open / Extempore | ✅ 8 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **Working** |
| Conversation Questions | ✅ 4 | ✅ audio-only | ✅ | ✅ | ✅ | ✅ 5 dims | ✅ | ✅ | **Working** |
| Passage Questions (spoken) | ✅ 4 | ✅ audio-only | ✅ | ✅ | ✅ | ✅ 5 dims | ✅ | ✅ | **Working** |

## Listening

| Module | Question | Interaction | Capture | Processing | Evaluation | Scoring | Persist | Report | Verdict |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|---|
| Listening Comprehension | ✅ 17 | ✅ play-once | ✅ MCQ | — | ✅ | ✅ | ✅ | ✅ | **Working** |
| Passage Comprehension | ✅ | ✅ | ✅ | — | ✅ | ✅ | ✅ | ⚠️ | **Working (unassessed)** |
| Conversation Comprehension | ⚠️ 1 passage | ✅ | ✅ | — | ⚠️ shared | ⚠️ shared | ✅ | ⚠️ | **Partial** |
| Dictation | ✅ 28 shared | ✅ play-once | ✅ typed | — | ✅ | ✅ accuracy | ✅ | ✅ | **Working** |
| Response Selection | ✅ 8 | ✅ play-once | ✅ MCQ | — | ✅ | ✅ appropriacy | ✅ | ✅ | **Working** |

## Reading

| Module | Question | Interaction | Capture | Processing | Evaluation | Scoring | Persist | Report | Verdict |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|---|
| Reading Comprehension | ✅ 17 | ✅ passage withdrawn | ✅ MCQ | — | ✅ | ✅ | ✅ | ✅ | **Working** |
| Reading Rate | ✅ | ✅ client-timed | ✅ | — | ✅ | ✅ separate | ✅ | ⚠️ | **Working (unassessed)** |
| Vocabulary in Context | ✅ 12 | ✅ | ✅ MCQ | — | ✅ | ✅ vocabulary | ✅ | ✅ | **Working** |

## Writing

| Module | Question | Interaction | Capture | Processing | Evaluation | Scoring | Persist | Report | Verdict |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|---|
| Email Writing | ✅ 4 | ✅ editor, draft saved | ✅ | — | ✅ 5 measures | ✅ | ✅ full text | ✅ | **Working** |
| Short Written Response | ✅ | ✅ | ✅ | — | ✅ | ✅ | ✅ | ⚠️ | **Working (unassessed)** |
| Summary / Opinion | ✅ 1 | ✅ | ✅ | — | ✅ | ✅ | ✅ | ⚠️ | **Working (unassessed)** |
| Sentence Completion | ✅ 18 | ✅ typed | ✅ | — | ✅ | ✅ grammar | ✅ | ✅ | **Working** |
| Dictation (written) | ✅ | ✅ | ✅ | — | ✅ | ✅ | ✅ | ✅ | **Working** (the Listening row above) |
| Passage Reconstruction | ✅ 8 | ✅ shown then withdrawn | ✅ typed | — | ✅ recall + form | ✅ 2 dims | ✅ full text | ✅ | **Working** |
| Typing | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | **Missing** |

---

## "Working (unassessed)" — the category that matters

*The finding, as the audit recorded it:* six modules across Listening,
Reading and Writing passed every stage **except the last**. They were
reachable, executable, persisted, evaluated, scored and reproducible — on
their own practice screen. No assessment template included them, so no
assessment report had ever shown a Listening, Reading or Writing section. The
four-skill capability existed as **practice** and did not exist as
**assessment**.

*Closed in Phases 3 and 4.* Every module above can now be a section of an
assessment: one attempt lifecycle carries three response modes, each section
is scored and stored, and the report rolls the sections up by skill. Two
things found while closing it are worth recording, because both had been
invisible for the same reason — nothing had ever run the path:

* **A writing section could not start at all.** A WritingPrompt id was stored
  in `Response.quiz_item_id`, a column with a foreign key to `quiz_items`. The
  database rejected the insert. Written answers now have their own
  `prompt_id`.
* **A listening section played nothing.** The prompt endpoint looked its item
  up in `task_items` only, so a passage-backed question 404ed and the runner
  reported that the audio could not be played. Candidates would have answered
  four questions about an announcement they never heard.

---

## Evaluation dimensions actually produced

| Dimension | Produced by | In report | Notes |
|---|---|:--:|---|
| pronunciation | wav2vec2 GOP | ✅ | Per-phoneme evidence stored. SNR-penalised. |
| accuracy | reference alignment | ✅ | |
| fluency | VAD metrics | ✅ | |
| latency | VAD onset | ✅ | |
| disfluency | transcript | ✅ | Fillers. |
| grammar | rule set | ✅ | Indian English never flagged. |
| content | rubric coverage | ✅ | |
| intelligibility | — | ❌ | Named in comments, never produced. Needs human raters. |
| vocabulary | word-sense choice, lexical range | ✅ | Vocabulary in Context and the writing scorer. |
| comprehension | listening/reading | ✅ | Now a section dimension in the assessment report. |
| appropriacy | response selection | ✅ | Deliberately not comprehension: every distractor is correct English. |
| coherence | writing only | ⚠️ | Folded into `content` in the report; separate on the writing screen. |
| professionalism | — | ❌ | Not measured anywhere. |

---

## Template coverage

*As the audit found it:*

| Template | Exists | Duration | Sections | Skills covered | Verdict |
|---|:--:|---|---|---|---|
| SVAR-style Spoken English | ⚠️ | 18 min (target 15) | 4 | Speaking | **Partial** — no Listening, no Short Answer; only 4 of 6 required sub-scores; description contradicts contents |
| Versant-style Speaking & Listening | ⚠️ | 22 min (target 17–20) | 6 | Speaking | **Partial** — no Conversation, no Passage Questions |
| Versant-style 4 Skills | ❌ | — | — | — | **Missing** |
| Professional English | ❌ | — | — | — | **Missing** |
| Company Communication Round | ⚠️ | 11–16 min | 2–4 | Speaking | **Partial** — five seeded; no weights, thresholds, role or difficulty |

*After Phase 5:*

| Template | Exists | Duration | Sections | Skills covered | Verdict |
|---|:--:|---|---|---|---|
| SVAR-style Spoken English | ✅ | 18 min (target 15) | 7 | Speaking, Listening, Reading | **Working** — all six sub-scores reportable. Over target; see below |
| Versant-style Speaking & Listening | ✅ | 19 min (target 17–20) | 6 | Speaking | **Working** — Conversation and Passage Questions included, no Read Aloud |
| Versant-style 4 Skills | ✅ | 31 min (target 30) | 7 | All four | **Working** — reports one score per skill |
| Professional English | ✅ | 61 min (target 60) | 10 | All four | **Working** |
| Company Communication Round | ⚠️ | 6–15 min | 2–4 | Speaking | **Partial** — five seeded; no weights, thresholds, role or difficulty. Durations corrected: Cognizant-style said 13 minutes and runs 6 |

Durations are computed from the sections now rather than typed in, and a test
asserts the stated figure matches. The one template still over target is
SVAR-style, because the runner waits out every response window in full where
the test it imitates advances when the candidate stops speaking — a Phase 7
change, recorded rather than papered over.

Two properties are now enforced by tests rather than intention: **every
section of every template can be filled from the bank**, and **every section
feeds at least one sub-score the format publishes** — no part of a test is
work the report ignores.

---

## Item bank classification (Phase 6)

| Column | Values | Backfilled | Filterable from |
|---|---|:--:|---|
| `topic` | free text | no — nobody decided one when the items were written | Speaking sections |
| `role` | free text | no | Speaking sections |
| `industry` | bpo · it · banking · healthcare · retail · general | yes, to `general` | Speaking sections |
| `language` | ISO 639-1 | yes, to `en` | Speaking sections |
| `difficulty` | float, banded easy/medium/hard | already existed | every bank |

Only `TaskItem` carries the four classification columns, so only a speaking
section can filter on them. A section that asks a quiz or writing bank for one
is refused by the builder *and* by the publish guard — the failure mode being
guarded against is a section that quietly serves nothing.

Two rules that had to be decided rather than inherited: an **unclassified item
stays eligible** for every filter, because the bank predates the columns and
excluding the untagged would make one optional filter a mandatory tagging
exercise; and **general material belongs to every vertical**, because a
banking round built only from banking sentences would be a five-item test.

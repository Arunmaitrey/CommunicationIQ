# Assessment Gap Analysis

Audited against the SVAR/Versant-comparable requirement set, on the running
build at `http://localhost:3010` (commit `3da28830fdc7`, engine tier 1).

**Method.** Signed in through the UI as a student, listed the nine live
assessment profiles from the API, started a real Versant-style attempt and
inspected the exact runner payload per task type, then read the models,
routers and scoring path behind each claim. Nothing below is marked
implemented because a file or a card exists.

**The bar used.** Accessible → executable → persisted → evaluated → in the
report → end-to-end. Anything failing one of the six is *Partial* at best.

---

## Summary counts

| | Count |
|---|---|
| Requirements audited | 61 |
| Existing (end-to-end) | 23 |
| Partial | 14 |
| Missing | 21 |
| Incorrect (built, but wrong or dead) | 3 |

**As of the end of Phase 9**, forty-one of those rows have moved to Existing and
are marked in place below. The counts above are left as the audit found them:
a gap analysis that quietly restates itself as work proceeds stops being a
record of what was true.

---

## 3. Three-concept separation

| Requirement | Existing | Partial | Missing | Incorrect | Action |
|---|---|---|---|---|---|
| A. Assessment Module as a reusable capability | ✅ | | | | `TaskItem.task_type` + `ProfileSection.task_type` already separate capability from test. Six speaking types registered. No change. |
| B. Assessment Template assembled from modules | ✅ | | | | `SimulationProfile` + `ProfileSection` rows. Nine exist and are not hard-coded together. No change. |
| C. Company-specific builder | | ⚠️ | | | Admin can create a profile and pick sections/counts/timings via `ProfileRequest`. Cannot set weights, thresholds, difficulty, role or department. Extend `ProfileRequest`. |

**Finding:** the three-concept separation the brief asks for **already exists
structurally.** The gap is not architectural, it is that the builder exposes
only half the fields.

---

## 4. Speaking module catalog

| Requirement | Existing | Partial | Missing | Incorrect | Action |
|---|---|---|---|---|---|
| 4.1 Read Aloud | ✅ | | | | 24 items, prep 5s / response 20s, scored on pronunciation, accuracy, fluency, latency, disfluency. |
| — pronunciation | ✅ | | | | wav2vec2 GOP, `phoneme_scores` persisted. |
| — fluency, speech rate, pauses | ✅ | | | | VAD-derived, in `FeatureRecord.metrics`. |
| — word accuracy, omissions, substitutions | ✅ | | | | Reference alignment in `tier1/accuracy.py`. |
| — intelligibility | | | ❌ | | Named in `ScoreRecord.dimension` comments, never produced. Needs the human rater panel. Leave unscored and say so. |
| — repetitions | | ⚠️ | | | Disfluency detector counts fillers; repetitions not separated out. |
| 4.2 Repeat — text hidden | ✅ | | | | **Verified in payload:** `prompt_text: ''`, `has_prompt_audio: true`. Text released only by `POST .../prompt`, server-enforced play count, 409 on replay. |
| 4.2 Repeat — TTS/recorded audio | | ⚠️ | | | Browser `speechSynthesis`, not recorded audio. `prompt_audio_key` column exists and is empty everywhere. Also: the words reach the client to be spoken, so they are readable from the network tab. |
| 4.2 Repeat — ASR → compare → score | ✅ | | | | Full path exists. |
| — word order, added words | | ⚠️ | | | Alignment computes edit distance; order and insertions not reported separately. |
| 4.3 Short Answer | ✅ | | | | 18 items. Relevance, grammar, fluency, pronunciation scored. |
| — completeness | | | ❌ | | Not a dimension. |
| 4.4 Sentence Builds | ✅ | | | | 16 items, fragments joined by `/`, prep 8s / response 25s. |
| — word order scoring | | ⚠️ | | | Scored via generic accuracy, not as a construction task. |
| 4.5 Conversation Questions | ✅ | | | | **Closed in Phase 4.** 4 items, played once, answered aloud. Content scored from the item rubric above the frozen path (`app/spoken_content.py`). |
| 4.6 Passage Questions (spoken answer) | ✅ | | | | **Closed in Phase 4.** 4 items. Deliberately separate from the MCQ listening module: choosing shows recognition, saying it shows comprehension you can act on. |
| 4.7 Story Retelling | ✅ | | | | 6 items. |
| 4.7 — content and language scored **separately** | | | | ❗ | Currently collapsed: one `content` dimension plus the shared language dimensions. Requirement is two explicit axes. Must split. |
| 4.8 Open Questions / Extempore | ✅ | | | | 8 items, prep and response configurable per section. |
| — min/max response time | | ⚠️ | | | Max enforced by the response timer. No minimum. |

---

## 5. Listening modules

| Requirement | Existing | Partial | Missing | Incorrect | Action |
|---|---|---|---|---|---|
| Listening Comprehension | ✅ | | | | 6 passages, 17 questions, own scorer, own mastery update, `/listening`. |
| Conversation Comprehension | | ⚠️ | | | One passage is a two-speaker exchange; not a distinct module with its own logic. |
| Passage Comprehension | ✅ | | | | Same engine as above. |
| Dictation | ✅ | | | | **Closed in Phase 4.** Heard once, typed back; word accuracy against the sentence. Shares the Repeat Sentence bank rather than duplicating it. |
| Response Selection | ✅ | | | | **Closed in Phase 4.** 8 exchanges, one passage each. Scored as `appropriacy`, not comprehension — every distractor is correct English. |
| Each has its own scoring logic | | ⚠️ | | | Comprehension and Response Selection now take different dimensions from `DIMENSIONS_BY_TASK`. The marking arithmetic is still shared, which is correct — right-or-wrong is right-or-wrong. |
| **Listening is in no assessment template** | ✅ | | | | **Closed in Phases 3–4.** A template can hold a Listening section and the report rolls it up as a skill. Phase 4 also found that such a section played nothing — the prompt endpoint knew only about `task_items`. |

---

## 6. Reading modules

| Requirement | Existing | Partial | Missing | Incorrect | Action |
|---|---|---|---|---|---|
| Read Aloud (speaking) | ✅ | | | | See 4.1. |
| Reading Comprehension, no speaking | ✅ | | | | 5 passages, 17 questions, `/reading`. |
| — main idea, detail, inference | ✅ | | | | Question set covers all three by design. |
| — vocabulary in context | ✅ | | | | **Closed in Phase 4.** 12 items; every distractor is a real sense of the word, so only the sentence decides. |
| Reading rate | ✅ | | | | Client-timed, implausible rates flagged. Beyond requirement. |
| **Reading is in no assessment template** | ✅ | | | | **Closed in Phases 3–4.** |

---

## 7. Writing modules

| Requirement | Existing | Partial | Missing | Incorrect | Action |
|---|---|---|---|---|---|
| Email Writing | ✅ | | | | 4 of the 6 prompts are email tasks. |
| Short Written Response | ✅ | | | | Same engine. |
| Summary / Opinion | ✅ | | | | One summary prompt. |
| Typing | | | ❌ | | No speed/accuracy measure. |
| Sentence Completion | ✅ | | | | **Closed in Phase 4.** 18 gaps, typed. A set of accepted words per gap, because English usually allows more than one. |
| Dictation (written) | ✅ | | | | **Closed in Phase 4.** The Listening row above — it is one module measured through writing. |
| Passage Reconstruction | ✅ | | | | **Closed in Phase 4.** 8 passages, shown for a computed window then withdrawn. Own scorer: idea recall through cues plus form. Not the essay scorer — see `app/reconstruction.py`. |
| Grammar, vocabulary, organization, relevance, coherence | ✅ | | | | Five measures, each with a stated basis. |
| Spelling | | | ❌ | | No dictionary check. |
| Punctuation | ✅ | | | | In `mechanics`. |
| Professional tone | | | ❌ | | Not measured. |
| Completeness | | ⚠️ | | | Approximated by task-response coverage. |
| **Writing is in no assessment template** | ✅ | | | | **Closed in Phases 3–4.** Phase 4 also found that a writing section could not start at all: a WritingPrompt id was stored in a column with a foreign key to `quiz_items`. |

---

## 8–11. Predefined templates

| Requirement | Existing | Partial | Missing | Incorrect | Action |
|---|---|---|---|---|---|
| T1 SVAR-style Spoken English ~15 min | ✅ | | | | **Closed in Phase 5.** Seven sections: Read Aloud, Repeat, Listening, Short Answer, Conversation, Word in Context, Open. Computes to 18 min against a 15 target -- the runner waits out every response window, which is a Phase 7 fix and is recorded rather than rounded away. |
| T1 — six named sub-scores | ✅ | | | | **Closed in Phase 5.** All six reportable, asserted by test. Active Listening comes from the listening section, Spoken English Understanding from the spoken answers, Vocabulary from its own section rather than from content coverage wearing the label. |
| T2 Versant-style Speaking & Listening ~17–20 min | ✅ | | | | **Closed in Phase 5.** 19 min, six parts: Short Answer, Repeat, Conversations, Passage Questions, Story Retell, Open. No Read Aloud. |
| T3 Versant-style 4 Skills ~30 min | ✅ | | | | **Closed in Phase 5.** 31 min, seven parts, all four skills. Reports one score per skill rather than vendor sub-scores -- two numbers labelled Listening on one page is worse than one. |
| T4 Professional English ~60 min | ✅ | | | | **Closed in Phase 5.** 61 min, ten parts, all four skills, workplace material throughout. |
| Workplace-oriented content | | ⚠️ | | | Reading and Writing banks are workplace-oriented. Speaking bank is general. |

---

## 12. Company-specific builder

| Requirement | Existing | Partial | Missing | Incorrect | Action |
|---|---|---|---|---|---|
| Name, description, duration | ✅ | | | | In `ProfileRequest`. |
| Modules, question count | ✅ | | | | Per section. |
| Preparation / response time | ✅ | | | | Per section, 0–300s / 5–600s. |
| Target role, department, difficulty | ✅ | | | | **Closed in Phase 6.** Columns existed since Phase 3 and the builder screen did not offer them, so the only way to set one was the API — and opening the profile in the UI wiped it again. Both halves fixed. |
| Skill weight | | | | ❗ | **`SimulationProfile.scoring_weights` column exists, is never written by any endpoint and never read by the scorer.** Composition uses the global `WEIGHTS` constant in `pipeline.py`. This is a dead column that looks like a feature. |
| Pass threshold | ✅ | | | | **Closed in Phase 6.** Read by `weighting.apply` and shown on the report. Cloning a round used to drop it. |
| Minimum skill threshold | ✅ | | | | **Closed in Phase 6.** Per-dimension floors; failing any one fails the assessment even when the weighted overall clears the bar. |

---

## 13. Question bank

| Requirement | Existing | Partial | Missing | Incorrect | Action |
|---|---|---|---|---|---|
| Bank independent of assessments | ✅ | | | | `TaskItem` is standalone; sections select from it at attempt start. |
| Module, skill, difficulty | ✅ | | | | `task_type`, `skill_tags`, `difficulty` (IRT-calibrated). |
| Expected answer, evaluation criteria | ✅ | | | | `reference_text`, `rubric`. |
| Audio, text | ✅ | | | | `prompt_audio_key` (unused), `prompt_text`. |
| Preparation / response time | | | | ❗ | On the **section**, not the item. The brief puts them on the question. Section-level is arguably better; flagged as a deliberate divergence, not an omission. |
| Topic | ✅ | | | | **Closed in Phase 6.** `TaskItem.topic`, optional. Backfilled only on items authored with one — a keyword guess in a column an admin filters on is worse than an empty one. |
| Role | ✅ | | | | **Closed in Phase 6.** `TaskItem.role`, optional. |
| Industry | ✅ | | | | **Closed in Phase 6.** `TaskItem.industry`, one of `app.selection.INDUSTRIES`. |
| Language | ✅ | | | | **Closed in Phase 6.** `TaskItem.language`, ISO 639-1, backfilled to `en` because that is true of every item. |
| Industry verticals (BPO, IT, Banking…) | ✅ | | | | **Closed in Phase 6.** Six values: bpo, it, banking, healthcare, retail, general. Short on purpose — a forty-entry taxonomy nobody tags against is worse than five that get used. 27 genuinely industry-specific items authored so the filter discriminates. |

---

## 14. Randomization

| Requirement | Existing | Partial | Missing | Incorrect | Action |
|---|---|---|---|---|---|
| Random selection per attempt | ✅ | | | | `random.sample(pool, count)`. |
| Adaptive selection | ✅ | | | | 2PL IRT by ability when enough items are calibrated. Exceeds the requirement. |
| Difficulty filter | ✅ | | | | **Closed in Phase 6.** `difficulty_min` / `difficulty_max` per section. An explicit mix beats adaptive selection: both control difficulty and only one can be in charge. |
| Skill / role filter | ✅ | | | | **Closed in Phase 6.** Role, topic, industry and language, all optional, all any-of. Only the TaskItem bank carries them, and a section that asks a bank for a filter it cannot honour is refused at build time rather than serving nothing. |
| Configurable pool size, difficulty distribution | ✅ | | | | **Closed in Phase 6.** `min_pool` is a floor on eligible items, checked at publish — a bank the size of the section serves the same test on every retake. `mix` is a relative share per difficulty band, honoured by `selection.draw` and verified by deterministic tests, with any shortfall reported rather than absorbed. |

---

## 15. Timing engine

| Requirement | Existing | Partial | Missing | Incorrect | Action |
|---|---|---|---|---|---|
| Preparation timer | ✅ | | | | Per section, counts down on screen. |
| Response timer | ✅ | | | | Per section, with warn/critical states. |
| Auto start recording | ✅ | | | | Starts on beep. |
| Auto stop, auto advance, auto save | ✅ | | | | `await countdown(response_seconds)` then stop/submit/advance. No Stop button dependency. |
| Section timer | ✅ | | | | **Closed in Phase 7.** Advisory by design: it warns and never ends an item. The item timer already bounds every recording, and a second authority over one recording is how answers get cut in half. |
| Assessment timer | ✅ | | | | **Closed in Phase 7.** Server-computed from `started_at` plus grace; the client is sent the deadline *and* the server's clock so a wrong device clock cannot expire an attempt early. Expiry submits the work that exists — it never discards it. |
| Timeout handling | ✅ | | | | Truncation detected and reported separately from poor speech. |

---

## 16. Candidate experience

| Requirement | Existing | Partial | Missing | Incorrect | Action |
|---|---|---|---|---|---|
| Microphone check | ✅ | | | | Live level meter, permission handling, blocked-state recovery. |
| Speaker check | ✅ | | | | Test tone with confirmation. |
| Background-noise check | ✅ | | | | SNR measured; feeds the pronunciation confidence penalty. |
| Instructions | ✅ | | | | Per section. |
| Assessment → section → question → prep → record → next → completion | ✅ | | | | Verified in the runner. |
| Camera check | ✅ | | | | **Closed in Phase 9.** Per assessment, off by default. Confirms a working, permitted camera and records nothing — no video is captured or scored, and the refusal message says so. Demanding it of a student practising at home would be collecting a permission for no reason. |
| Assessment invitation | ✅ | | | | **Closed in Phase 9.** Single-use tokens with an expiry, resolved through a control-plane directory so the institution never appears in the link. Previewing costs nothing; claiming spends it, once, inside a transaction. |
| Candidate details capture | ✅ | | | | **Closed in Phase 9.** Name, and email if they give one. Nothing else — no date of birth, no gender, nothing an employer might be tempted to collect through a testing tool. A redeemed session is role `candidate`: one assessment, not an account. |
| Practice item before the real one | ✅ | | | | **Closed in Phase 9.** One unscored item first, per assessment. Its audio is never stored, which is how it stays out of every score without exclusion logic in four places. |

---

## 17. Recording engine

| Requirement | Existing | Partial | Missing | Incorrect | Action |
|---|---|---|---|---|---|
| Permission, start/stop, auto-stop | ✅ | | | | |
| Audio upload | ✅ | | | | Multipart to the response endpoint. |
| Duration, sample rate, channels, size | ✅ | | | | On `ResponseAudio`. |
| Audio validation | ✅ | | | | WAV-only, stereo downmixed, clipping detected. |
| Upload retry | ✅ | | | | **Closed in Phase 7.** Exponential backoff, bounded by attempts and elapsed time. Retryable vs terminal statuses are classified explicitly, and 409 counts as *stored* — the server refuses a second upload for a response it holds, so that refusal is proof the first landed. |
| Failed upload recovery | ✅ | | | | **Closed in Phase 7.** The WAV goes into IndexedDB before the first POST and is removed only on acknowledgement, so a reload or a crash loses nothing. Submission is blocked while anything is owed; finishing without it is an explicit choice that says what it costs. |
| Silence detection at capture | ✅ | | | | **Closed in Phase 7.** A client-side energy gate offers one re-record before the item is committed. It produces no score, touches no dimension and alters no uploaded byte — the server's VAD scores exactly the same samples and remains the only authority. |
| Processing status | ✅ | | | | Attempt status + pending-response polling. |

---

## 18. Speech scoring

| Requirement | Existing | Partial | Missing | Incorrect | Action |
|---|---|---|---|---|---|
| Not audio→LLM→score | ✅ | | | | No LLM anywhere in scoring. |
| ASR → transcript | ✅ | | | | faster-whisper `small.en`. |
| Word alignment | ✅ | | | | wav2vec2 CTC forced alignment. |
| Speech metrics | ✅ | | | | WPM, articulation rate, pauses, onset. |
| Pronunciation analysis | ✅ | | | | GOP per phoneme. |
| Fluency, grammar analysis | ✅ | | | | |
| Semantic evaluation | ✅ | | | | Rubric key-point coverage. |
| Objective/AI separation | ✅ | | | | Objective metrics in `FeatureRecord`; rubric scoring is separate and rule-based. |
| Word error rate | | ⚠️ | | | Accuracy computed; WER not reported as such. |
| Filler words | ✅ | | | | Disfluency detector. |

---

## 19–21. Reporting, transparency, result model

| Requirement | Existing | Partial | Missing | Incorrect | Action |
|---|---|---|---|---|---|
| Per-dimension scores | ✅ | | | | Seven dimensions. |
| Strengths / weaknesses | ✅ | | | | **Closed in Phase 8.** Both, measured against the student's own average rather than a cohort — this product has no population norms, and "ahead of your own average" needs none while "good" would be a claim about people nobody has measured. |
| Detected errors + evidence | ✅ | | | | Stored since M2 — but `grammar_errors` and `phoneme_scores` **never reached the client** until Phase 8, so the report could assert a grammar score with nothing behind it. Now surfaced per dimension, with a test asserting every dimension's named evidence actually exists in the payload. |
| Recommendations | ✅ | | | | **Closed in Phase 8.** Up to three, ordered by computed gain — what the overall would become if that measure matched the student's own best. Nothing is suggested whose gain rounds to nothing. |
| Module-by-module results | ✅ | | | | Per-response scores in the result payload. |
| Speaking / Listening / Reading / Writing rollup | ✅ | | | | **Closed in Phases 3–5 and surfaced in Phase 8.** Templates span four skills, section results are stored, and the summary names the stronger skill when the gap is real. |
| score, confidence, evaluation_method | ✅ | | | | `confidence`, `provider_key`, `provider_version`, `computed_ms` per `ScoreRecord`. |
| raw_metrics, evidence | ✅ | | | | `FeatureRecord`. |
| No fake precision | ✅ | | | | Uncalibrated composite withheld; `anchored` gate; IELTS as a band range. Exceeds the requirement. |
| Attempt → section → question → response → metrics → score | ✅ | | | | **Closed in Phase 3.** `SectionResult` is stored, so a report a student was shown does not change when the scorer does. |
| Report reproducible from stored evidence | ✅ | | | | Audio, transcript, features and scores all retained. |
| Export | ✅ | | | | **Closed in Phase 8.** CSV in long format — one row per measurement, so an attempt producing fewer dimensions still exports cleanly, which every tier-0 attempt does. PDF via the browser's own print rather than a server renderer: a second layout to keep in step with the screen is a second thing to get wrong. |

---

## 22. Company Communication Round

| Requirement | Existing | Partial | Missing | Incorrect | Action |
|---|---|---|---|---|---|
| Company round template concept | ✅ | | | | `style="company_round"`, five seeded (TCS, Infosys, Wipro, Accenture, Cognizant). |
| Company, role, duration, difficulty | | ⚠️ | | | Company yes. Role, department, CEFR difficulty no. |
| Configurable module weight / thresholds | | | ❌ | | As §12. |

---

## 25. Testing

| Requirement | Existing | Partial | Missing | Incorrect | Action |
|---|---|---|---|---|---|
| Current suite | ✅ | | | | 399 passing across 19 files. |
| Template creation, module/question selection | ✅ | | | | `test_company_rounds.py`, `test_formats_vendor.py`. |
| Randomization | | | ❌ | | Not tested. |
| Timing | | ⚠️ | | | Section config tested; countdown behaviour not. |
| Recording, upload, ASR, alignment, metrics | ✅ | | | | `test_attempt_flow.py`, `test_engine_tier1.py`. |
| Module scoring, weighting, overall, threshold | | ⚠️ | | | Scoring and overall tested. Weighting and thresholds do not exist to test. |
| CEFR mapping | | | ❌ | | No CEFR anywhere. IELTS bands exist; CEFR does not. |
| Report persistence, export | | ⚠️ | | | Persistence tested; export does not exist. |

---

## The three "Incorrect" findings, restated

These matter more than the missing items, because each one currently reads as
working:

1. **`scoring_weights` is a dead column.** It exists on `SimulationProfile`,
   no endpoint writes it, and the scorer ignores it in favour of a global
   constant. Anyone reading the schema would conclude per-assessment
   weighting is supported. It is not.

2. **Story Retell collapses content and language.** The brief is explicit
   that these are two axes. One `content` dimension plus shared language
   dimensions is not the same thing, and a trainer cannot see whether a
   student remembered the story but spoke badly, or spoke well and remembered
   nothing.

3. **Listening, Reading and Writing are orphaned from assessment.** All three
   work end-to-end as practice modules with their own scorers and their own
   persistence. **No assessment template includes any of them**, so no
   assessment report has ever contained a Listening, Reading or Writing
   section score. The four-skill capability exists as practice and does not
   exist as assessment — which is precisely the distinction this brief is
   drawing.

Plus one description bug: the SVAR profile's own text claims "six-section
simulation including grammar and error-ID sections" and it has four sections
with neither.

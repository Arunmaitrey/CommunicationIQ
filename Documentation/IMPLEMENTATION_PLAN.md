# Implementation Plan

Ordered by what unblocks the most, not by what is easiest. Each phase ends
with something demonstrable end-to-end, because a phase that ends with "the
model exists" is the failure mode this whole audit is about.

Nothing here rebuilds a working engine. Where an engine exists it is lifted
and reused.

---

## Phase 0 — Make the journey obvious (2 days)

Raised directly: *"user journey is bloody confusing, make it layman friendly
and stupid proof."* It goes first because every later phase adds surface, and
adding surface to a confusing product makes it worse.

### The problem, concretely

A student currently sees **eight** destinations:

```
Today · Four skills · IELTS profile · Simulations · Progress · Drills ·
Quiz · Season
```

Four of those are practice (Four skills, Simulations, Drills, Quiz). Three are
progress (Today, Progress, Season). Nobody outside this team can say what
separates a Drill from a Quiz from a Simulation, and the words are ours, not
theirs.

### The fix

Collapse to **three verbs and a settings page**:

```
  Practise          one place. Pick a skill or accept today's suggestion.
                    Absorbs: Four skills, Drills, Quiz
  Take a test       the assessment library. Real tests, timed, one shot.
                    Absorbs: Simulations
  My progress       everything about how you are doing.
                    Absorbs: Today, Progress, Season, IELTS profile
  Settings
```

Rules:

- **One primary action per screen.** The home screen answers one question:
  *what should I do right now?* One button. Everything else is secondary.
- **No internal vocabulary.** "Drill", "quest", "simulation profile",
  "diagnostic", "baseline" are our words. Use: *practise*, *today's goal*,
  *test*, *first test*.
- **Never a dead end.** Every empty state names the next action and links to
  it. Every unfinished module already does this; extend it everywhere.
- **Say what a thing costs before it starts.** "18 minutes, 26 questions, you
  cannot pause" on the card, not after the first question.
- **Plain-language results.** Lead each report with one sentence a parent
  could read, then the numbers underneath for whoever wants them.

Deliverable: nav reduced to four items, home screen with a single primary
action, a first-run path that does not require reading anything.

---

## Phase 1 — Wire the dead weighting and split Story Retell (3 days)

The two "Incorrect" findings. Both currently read as working.

1. **`scoring_weights` becomes real.** Add to `ProfileRequest`, validate it
   sums to 1, read it in composition, show it beside the score. Add
   `pass_threshold` and `skill_thresholds`.
2. **Story Retell reports two axes.** `content_recall` (key facts, sequence,
   main idea, completeness) and the existing language dimensions, reported
   separately and never averaged into one number.
3. Fix the SVAR profile description, which claims six sections and grammar
   content it does not have.

Tests: weights change the composite; thresholds gate pass/fail; a retell with
good language and no facts scores high on one axis and low on the other.

---

## Phase 2 — Section results, the missing persistence layer (3 days)

`SectionResult` between `Attempt` and `Response`:

```
skill · task_type · raw · scaled · weight · confidence · computed_at
```

Section scores are currently recomputed on read. Storing them is what makes a
report reproducible when the scorer changes, and it is the join point every
later phase needs.

Tests: a stored report is byte-identical after a scorer version bump.

---

## Phase 3 — One runner, three response modes (5 days)

The keystone. Lets a template contain a non-speaking section.

- `ProfileSection.skill` and a `response_mode` derived from `task_type`:
  `speak` | `select` | `write`.
- Lift the three existing scorers into module handlers. The practice screens
  call the same handlers, so nothing regresses.
- Runner dispatches on mode. One attempt lifecycle, one timing engine, one
  upload path.

**This is where Listening, Reading and Writing stop being orphaned.**

Tests: a two-section attempt with one speaking and one listening section
produces both section results and one report.

---

## Phase 4 — The missing modules (6 days)

Each is a handler plus a bank, not an engine.

| Module | Mode | Reuses |
|---|---|---|
| Conversation Questions | speak | prompt audio + short answer scorer |
| Passage Questions (spoken) | speak | listening passages + open response scorer |
| Dictation | write | listening passages + string alignment |
| Response Selection | select | listening scorer |
| Sentence Completion | write | grammar rules |
| Passage Reconstruction | write | essay scorer + key-point coverage |
| Vocabulary in Context | select | reading scorer |

Deferred with reasons: **Typing** (a speed measure, not an English measure —
say so rather than pad the count). **Professional tone** and **spelling**
need a lexicon; scoped separately.

### As built — where the plan's "reuses" column was wrong

Three of the seven could not reuse what this table said they would, and
finding out why was most of the work.

* **Conversation and Passage Questions** do reuse the content-relevance
  scorer, but it could not be reached from inside the engine. The pipeline
  gates content on a hard-coded set of three task types, and
  `app/engine/pipeline.py` is on `SCORING_PATH` — editing it would retire the
  frozen validation baseline. The same provider with the same rubric is
  invoked from `app/spoken_content.py`, above the freeze, at submit. A test
  asserts the pipeline's gate still excludes them, so the module gets deleted
  rather than double-scoring when a new baseline moves them in.
* **Response Selection** does not reuse "the listening scorer". It shares the
  marking code and takes its own dimension, `appropriacy`. Every distractor
  is correct English, so what it measures is whether a reply lands — telling
  a candidate their listening comprehension is weak would point them at the
  wrong practice.
* **Passage Reconstruction** does not reuse the essay scorer. Three of its
  five measures would score the passage's author (lexical range, coherence)
  or refuse to score a short reconstruction at all (a forty-word floor). It
  has its own two measures in `app/reconstruction.py`.

Two faults surfaced that predate the phase and had never been run: a writing
section could not start (foreign-key violation) and a listening section played
nothing (the prompt endpoint knew only about `task_items`). Both are recorded
in the coverage matrix.

---

## Phase 5 — The four templates (3 days)

Only possible after Phase 3. Assembled from modules, not hard-coded.

| Template | Target | Sections |
|---|---|---|
| SVAR-style Spoken English | 15 min | Read Aloud, Repeat, Listening, Short Answer, Conversation, Open |
| Versant-style Speaking & Listening | 18 min | Short Answer, Repeat, Conversation, Passage Questions, Story Retell, Open |
| Versant-style 4 Skills | 30 min | Repeat, Sentence Builds, Conversations, Sentence Completion, Dictation, Passage Reconstruction |
| Professional English | 60 min | the ten listed modules, workplace content throughout |

SVAR's six named sub-scores (Pronunciation, Fluency, Active Listening, Spoken
English Understanding, Vocabulary, Grammar) come from the section-to-skill
map, the same mechanism `evaluation.py` already uses for vendor sub-scores.

### As built — three corrections to the table above

**The 4 Skills row had no reading section.** Six modules were listed and none
of them was reading, so a template called "4 Skills" would have produced
three. Reading Comprehension added; a test now asserts both four-skill
templates cover all four.

**SVAR needed a seventh section to report its sixth sub-score.** Vocabulary
had nothing behind it in the six listed modules. The alternative was to
relabel content coverage as Vocabulary, which puts a number on the report
measuring something else, so the template carries a Vocabulary in Context
section instead.

**`versant_style_full` and `svar_style_full` are withdrawn, not kept
alongside.** They were the same two formats built when a template could
contain nothing but speaking. Two SVAR simulations in the picker, one of them
missing half the test, is not a choice a student can make sensibly. The
seeder retires them by name — `formats.WITHDRAWN_CODES` — because the
inferred rule ("any code that is not a blueprint code") also matches every
admin-authored profile, and did retire two dozen of them on its first run.

### Durations are computed now, not typed

`estimated_minutes` was a hand-typed guess and the audit caught what that
leads to. It is derived from the sections — `formats.duration_minutes` —
including per-item play time, per-section overhead and the one-off setup, and
a test asserts the field matches. Correcting the existing formats moved
Cognizant-style from a stated 13 minutes to a computed 6.

Three of the four templates land on target. **SVAR-style computes to 18
against a 15-minute target**, and the cause is structural: our runner waits
out the full response window on every item where the test it imitates advances
as soon as the candidate stops speaking. Seven sections plus setup is four and
a half minutes before a single answer. Publishing 15 and running 18 was the
other option. Making the clock adaptive is Phase 7.

---

## Phase 6 — Builder, bank classification, randomisation controls (4 days)

- Builder exposes role, department, difficulty, weights, thresholds.
- `TaskItem` gains `topic`, `role`, `industry`, `language`; selection filters
  widen, all optional.
- Configurable pool size and difficulty distribution.
- **Assessment Library** screen: the four templates, the company rounds, and
  *Create custom assessment*.

### As built

**Item 1 was half-done and looked finished.** Every field the audit called
missing — target role, department, difficulty band, pass threshold, minimum
skill thresholds — had existed on `SimulationProfile` since Phase 3, was
written by the API, and was read by `weighting.apply` on the result path. What
did not exist was any way to set them: the builder screen offered six fields
and the client type carried six, so the PUT that replaces a profile reset the
other five to their defaults every time somebody edited one. Opening a hiring
round to fix a typo removed its pass mark, and the screen looked identical
afterwards. `clone_profile` had the same shape of fault, copying
`scoring_weights` and none of the rest.

That is worth stating plainly: the audit row said "no fields" and the truth
was "fields nothing could reach, and an edit path that silently emptied them",
which is the more dangerous of the two.

**The taxonomy is six values, not forty.** `bpo`, `it`, `banking`,
`healthcare`, `retail`, `general`. A value nobody ever writes is
indistinguishable from a column that does not exist, and 27 genuinely
industry-specific speaking items were authored so the filter has something to
discriminate on.

**Two rules that had to be decided rather than assumed**, both instances of
the pattern this project keeps hitting:

* *An unclassified item stays eligible.* The bank predates these columns, so
  nearly every item has an empty topic and role. Excluding the untagged would
  have turned one optional filter into a mandatory tagging exercise across a
  hundred items, and the first admin to tick "banking" would have got an empty
  section.
* *General material belongs to every vertical.* "The training session begins
  at nine" is as true in a bank as in a call centre. A banking round built
  only from banking sentences would be a five-item test.

**Only `TaskItem` carries the classification columns**, so only a speaking
section can filter on them. `selection.FILTERS_FOR` states that per source,
the builder refuses an impossible combination at validation time, and the
publish guard refuses it again — rather than the section quietly serving
nothing, which is how this class of fault has always presented.

**Pool size is a floor, not a cap.** `min_pool` refuses to publish a section
whose eligible bank is too thin to survive a retake. Capping the pool would
have worked against the thing the control is named for.

**The Assessment Library reuses `SimulationProfile`.** A "template" is a
seeded profile whose code matches a blueprint, which is what it already was in
the database. Introducing an Assessment entity beside it would have meant two
things to keep in step and two places to publish from.

---

## Phase 7 — Recording robustness and timers (3 days)

- **Upload retry with backoff, and recovery.** Today a failed upload silently
  loses the item. This is the highest-severity reliability gap in the audit.
- Silence detection at capture, so a candidate is told they recorded nothing
  while they can still fix it.
- Section and assessment timers above the working item timers.

### As built

**The invariant.** A transient upload failure must never silently become a
skipped answer. It did: one POST, and on any error the runner called `skip`
and moved on, so a dropped Wi-Fi frame wrote "did not answer" into a result
somebody is judged on. The recording now goes into IndexedDB *before* the
first attempt and leaves only on acknowledgement. `skip` survives on exactly
one path — nothing was captured at all, where there is no audio to lose.

**409 is success.** The server refuses a second upload for a response it
already holds. From the client that refusal is proof the first one landed, and
reading it as a failure is how a *successful* upload becomes a skipped item on
the retry.

**A correction made during implementation, and the most important thing in
this phase.** The first version applied the deadline to uploads as well as to
answers. That would have refused a retry carrying audio recorded *before* the
bell — discarding an answer the candidate gave inside their own time, which is
the exact silent loss the queue was written to prevent, arriving through the
door built to prevent it. The two paths now have different rules: an answer is
composed when it is sent, so lateness is real; a recording existed already, so
it gets a bounded recovery window. Both directions are tested, and putting the
single rule back fails two of them.

**Two VADs, one authority.** The client detector is RMS energy over 20 ms
frames — deliberately cruder than the server's, because a cheap detector that
is occasionally wrong is fine for a gate that offers a re-record and would not
be fine for a measurement. It never scores, never writes a dimension and never
alters an uploaded byte. `SCORING_PATH` is untouched and the engine hash has
not moved.

**Four clocks, kept distinct.** Prep and item response are unchanged. The
section clock warns and *cannot* end an item — a test asserts the module
exposes no function that could, because the item timer already bounds every
recording and two authorities over one recording is how answers get cut in
half. The assessment clock is the only hard stop, computed by the server and
displayed by the client with the skew corrected.

**The SVAR fix was adaptive advancement, not shorter windows.** An item ends
when the candidate has spoken and then been silent for 1.8 seconds; the
configured window remains the ceiling, and silence *before* speech never
advances anything — that is somebody thinking. Measured against the runner's
own loop: SVAR-style now runs 15 minutes for a brief speaker, 16 for a
typical one, 18 for somebody who uses every window. The target was 15.

`estimated_minutes` was **not** adjusted. It states the ceiling, which is the
number a candidate can safely budget; publishing the typical figure would make
the estimate optimistic, which is precisely the fault the computed duration
replaced. `typical_minutes()` sits beside it for anywhere that wants to say
"about sixteen minutes, up to eighteen".

---

## Phase 8 — Reporting (4 days)

- Four-skill rollup in the assessment report.
- Strengths as well as weaknesses; recommendations as a set.
- Evidence panel per dimension, from data already stored.
- PDF/CSV export.
- Plain-language summary at the top (Phase 0 rule).

### As built

All of it in `app/reporting.py`, above the frozen path. `biggest_lever` is
inside `SCORING_PATH` and is untouched, so the weights are mirrored here and a
test asserts the two agree — a drift would silently reorder the
recommendations without changing a number, which is the kind of wrong nobody
notices.

**Strengths are measured against the student, not a cohort.** "Ahead of your
own average" is a fact about one person and needs no calibration. "Good" would
be a claim about a population this product has never measured, and the same
restraint that keeps the composite uncalibrated applies here.

**The report gave one weakness and nothing else, every time.** Somebody
reading that after each attempt learns that practising produces criticism.
What they are ahead on was measured just as precisely and was simply never
shown.

**Recommendations are capped at three.** Seven is not a plan; it is the chart,
retyped. Each carries the gain it would actually be worth, computed the same
way the frozen lever's is, and nothing is suggested whose gain rounds to
nothing — a suggestion that changes nothing still costs a week of somebody's
practice.

**The evidence panel found a real gap.** `grammar_errors` and
`phoneme_scores` had been stored on `FeatureRecord` since M2 and neither ever
left the server, so the report could say "your grammar was 44" and show
nothing it was counted from. Both now reach the client, and a test walks
`EVIDENCE_FOR` against the response schema so a dimension cannot promise
evidence that does not exist.

**Export is CSV plus the browser's print.** Long format, one row per
measurement: a wide row with seven dimension columns stops working the moment
an attempt produces six, which every attempt on a server without speech models
does. A server-rendered PDF would mean a new dependency and a second layout to
keep in step with the screen, and what most people mean by "PDF" is the page
they are looking at.

---

## Phase 9 — Candidate flow for external hiring (4 days)

- Invitation tokens, candidate details capture, no enrolled account needed.
- Practice item before the first scored one.
- Camera check where a client requires it.

### As built

**A token is a key to one assessment, not an account.** Redemption mints a
session with role `candidate`, admitted to exactly two places: the attempts
router and consent. Every other student surface still names `student` alone,
and a test asserts a candidate is refused by `/student/home`,
`/student/profiles` and `/student/attempts`.

**Looking is free, claiming is once.** `GET /invite/{token}` previews without
consuming — a link scanner in a mail client, or a candidate checking on the
train, must not burn the invitation. The claim re-checks inside the
transaction under `SELECT … FOR UPDATE`, so two people opening one link do not
both get in.

**Refusals name which of the three things went wrong.** "Invalid link" is
useless to somebody holding a link. An *unknown* token still reveals nothing:
no institution, no assessment.

**The link carries no institution.** A control-plane directory resolves token
→ schema, mirroring how sign-in resolves email → schema. Putting the slug in
the URL would leak who is hiring and invite enumeration.

**Consent had to move.** It lived on the student-only router, so a candidate
could be admitted, handed an assessment, and blocked at the first item by a
permission they had no way to give. It is now its own router — one endpoint
wide, not the whole of `/student`.

**The practice item's audio is never stored.** `pending_responses` is inside
the frozen path, so rather than score the warm-up and remember to exclude it
in four places, nothing is kept: no `ResponseAudio`, nothing pending, no
`ScoreRecord` to filter later. The candidate still gets what it is for — they
spoke, the meter moved, they know the microphone works.

**The camera check confirms and records nothing.** Per assessment, because it
is a client's requirement rather than ours.

### A note on the isolation test that failed

`test_two_institutions_see_different_people` failed on this phase, and it is
worth recording why it was not a leak. The isolation assertion — no user
visible in both institutions — passed throughout. What failed was
`all(e.endswith("@stmarys.edu"))`, true only while every user was enrolled.

The first fix filtered candidates by email suffix and *still* failed, because
candidates from earlier runs carried three different address shapes. What
makes a candidate different is what they are, not what their address looks
like; the test and the suite's cleanup both key on the role now. The test also
gained the assertion this phase could genuinely have broken and which the old
one never covered: a candidate admitted to one institution is invisible in the
other.

---

## Sequencing

```
Phase 0  ██                      journey (do first — everything else adds surface)
Phase 1  ███                     dead weighting, retell split
Phase 2  ███                     section results
Phase 3  █████                   one runner, three modes   ← keystone
Phase 4  ██████                  missing modules
Phase 5  ███                     four templates
Phase 6  ████                    builder + bank
Phase 7  ███                     recording + timers
Phase 8  ████                    reporting
Phase 9  ████                    external candidates
```

Roughly 37 working days. Phases 0–3 (13 days) are the ones that change what
the product *is*; the rest is coverage on top of a correct spine.

---

## Standing constraints

- The frozen speech engine does not move. Hash `11c513c58922dc43`. All
  weighting and rollup happens above `SCORING_PATH`.
- No LLM in scoring. Nothing here asks a model for a number.
- Every new score carries `confidence`, a stated basis and its evidence.
- No unearned equivalence claims: no CEFR ability score, no IELTS band point
  estimate, no vendor-score concordance, until a study exists.
- Every phase ships with tests that fail against the previous commit.

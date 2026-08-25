# Assessment Architecture

What exists, and the smallest set of changes that reaches the target. The
brief is explicit that there must be **one** engine, so this document is
mostly about what *not* to build.

---

## 1. What is already right

The three-concept separation the brief asks for is present:

```
TaskItem                    the question bank, standalone
   │  task_type
   ▼
ProfileSection              a module used inside one template
   │  item_count, prep_seconds, response_seconds, prompt_plays_allowed
   ▼
SimulationProfile           the template
```

Selection happens at attempt start, not at authoring time, so no template
holds questions. Randomisation and IRT-adaptive selection already run here.

The scoring path is a provider registry with versioned contracts:

```
audio → VAD → ASR → alignment → {pronunciation, accuracy, fluency,
        disfluency, grammar, content} → composite → ScoreRecord
                                                  → FeatureRecord (evidence)
```

Every score carries `confidence`, `provider_key`, `provider_version` and
`computed_ms`. Every response carries transcript, word timings, speech
segments, phoneme scores and grammar errors. Reports are reproducible from
stored evidence today.

**None of this should be rebuilt.**

---

## 2. The structural problem

Three parallel worlds evolved:

```
  ASSESSMENT WORLD                    PRACTICE WORLD
  ────────────────                    ──────────────
  SimulationProfile                   ListeningPassage  → ListeningAttempt
    └ ProfileSection                  ReadingPassage    → ReadingAttempt
        └ TaskItem                    WritingPrompt     → WritingSubmissionRow
            └ Response
                └ ScoreRecord         (separate routers, separate scorers,
                └ FeatureRecord        separate persistence, own screens)
```

Both work. Neither knows about the other. A template can only assemble things
from the left column, which is why every template is speaking-only and why no
report has ever contained a Listening, Reading or Writing section.

**The fix is not a second engine.** It is to let a `ProfileSection` reference
a non-speaking module, and to give the existing attempt a place to record a
section result.

---

## 3. Target architecture

Two additions, both to the assessment world:

```
SimulationProfile
  ├── scoring_weights       EXISTS, currently dead — wire it
  ├── pass_threshold        NEW
  ├── skill_thresholds      NEW
  ├── target_role           NEW
  ├── department            NEW
  └── difficulty_band       NEW  (CEFR)
       │
  ProfileSection
    ├── task_type           EXISTS — widen the vocabulary
    │     speaking: read_aloud, repeat_sentence, sentence_build,
    │               short_answer, story_retell, open_response,
    │               conversation_question ★, passage_question ★
    │     listening: listening_comprehension ★, dictation ★,
    │                response_selection ★
    │     reading:   reading_comprehension ★
    │     writing:   email_writing ★, sentence_completion ★,
    │                passage_reconstruction ★
    ├── skill               NEW — speaking|listening|reading|writing
    └── weight              NEW — this section's share of its skill score

  Attempt
    └── SectionResult       NEW — the missing persistence layer
          skill, task_type, raw, scaled, weight, confidence
          └── Response  (existing, for speaking)
              or item answers (for MCQ / written sections)
```

`★` = new task type. Each is a **handler registered against the existing
runner**, not a new engine.

---

## 4. How a non-speaking section runs inside one runner

The runner currently assumes every item is record-audio. Generalise it to
dispatch on a *response mode* while keeping one attempt lifecycle:

```
ProfileSection.task_type
        │
        ▼
  response_mode
        ├── "speak"   → existing path: prep → prompt → beep → record →
        │                upload → ASR → align → score
        ├── "select"  → play/show stimulus → options → answer → mark
        └── "write"   → prompt → editor → submit → essay scorer
```

The three scorers already exist:

| mode | scorer | source |
|---|---|---|
| speak | `engine/pipeline.py` | frozen, untouched |
| select | listening/reading correct-total + explanations | `routers/listening.py`, `routers/reading.py` |
| write | `app/writing.py`, five measures | new this week |

They are lifted into module handlers and called by the runner. The practice
screens keep working because they call the same handlers.

**This is the load-bearing decision: reuse the scorers, retire the duplicate
attempt tables over time, and never write a second pipeline.**

---

## 5. Score composition

Today: seven dimensions → global `WEIGHTS` constant → one composite.

Target: two levels, with the existing dimensions untouched underneath.

```
per response  →  dimensions (unchanged, frozen engine)
                      │
per section   →  SectionResult.scaled
                      │
per skill     →  Speaking / Listening / Reading / Writing
                      │   (weights from profile.scoring_weights)
                      ▼
overall       →  composite + pass/fail against pass_threshold
                             + per-skill floors from skill_thresholds
```

Rules carried forward from the existing honesty guards:

- A skill with no measured section is **absent**, not zero.
- `MIN_DIMENSIONS_FOR_OVERALL` still applies; too few measures means no
  overall rather than a thin one.
- Weights are shown next to the score they produced.
- The frozen engine hash must not move. Weighting and rollup happen *above*
  `SCORING_PATH`, in the same way `evaluation.py` already does.

---

## 6. Question bank extension

`TaskItem` gains classification only — no behaviour change:

```
topic         str    "customer escalation", "project delay"
role          str    "customer support", "developer"
industry      str    "bpo" | "it" | "banking" | "healthcare" | ...
language      str    default "en"
```

Selection filters widen from `(task_type, status)` to
`(task_type, status, [difficulty band], [role], [industry])`, with every
filter optional so existing templates behave identically.

Prep/response time stay on the **section**, not the item. The brief puts them
on the question; section-level is deliberate — it is what makes a section
uniform, which is what makes it comparable. Recorded as a divergence.

---

## 7. Timing

Section and assessment timers are added **above** the existing per-item
countdown, which already auto-starts, auto-stops, auto-saves and auto-advances
without a Stop button.

```
assessment timer   profile.estimated_minutes, hard stop → submit what exists
   section timer   sum of section item budgets, advisory
      item timers  prep + response   ← already working
```

---

## 8. What must not be built

- A second scoring engine. Three exist; they get lifted, not cloned.
- A second recording component. The existing one is sound; it needs upload
  retry and silence detection, which are additions to it.
- A second report component. The result screen gains skill sections.
- A second question bank. `TaskItem` gains columns.
- An LLM scorer. Nothing in this product scores by asking a model for a
  number, and that stays true.

---

## 9. Deliberate divergences from the brief

Recorded so they are choices rather than omissions:

1. **Prep/response on the section, not the item** — §6 above.
2. **No CEFR score, only a CEFR difficulty label.** Mapping an uncalibrated
   composite onto CEFR is the same unearned equivalence claim as an IELTS
   band. The IELTS profile already publishes a two-band range for exactly
   this reason. CEFR will label item difficulty, not candidate ability, until
   a concordance study exists.
3. **Intelligibility stays unscored.** It needs the human rater panel. It
   will keep appearing in reports as explicitly not measured.
4. **Story Retell will report two axes, not one blended score** — this is the
   brief's own requirement and the current implementation is wrong.

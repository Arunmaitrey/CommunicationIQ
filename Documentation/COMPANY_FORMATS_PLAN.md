# Company & Tool Formats — Product Plan (SVAR-parity for 6 more assessments)

Goal: replicate the SVAR-exact treatment (authentic structure + format-specific
UI skin + content + tests) for **TCS, Infosys, Wipro, Cognizant, Versant, and
SpeechX**, from the supplied research decks/mockups.

## 1. What the research shows — the six formats

| Format | Platform look | Structure (from the mockups) |
|---|---|---|
| **SVAR-style** ✅ done (re-derived 2026-08-23 from the reference walkthrough) | Navy, section banners | A1 read sentences (8) · A2 paragraphs (2) · A3 listen&repeat (8) = 18, 10-min budget · B speak (3, 90 s think / 60 s, speaking-point questions) · C verb forms 8 / tenses 8 / articles 6 / prepositions 6 / voice change 6 = 34, 15-min budget · D listen&answer (12 = 4 clips × 3, our clip count), 10-min budget, 'Okay' gate |
| **Cognizant** | Navy, "Do's/Don'ts" guidelines, section dividers | A Reading&Listening: read sentences (10) + **read word-lists (5)** + listen&repeat (8) · B Speaking: 3 topics · C Grammar: 8 (articles/tense/prepositions MCQ + text + active/passive) · D Passages: 2 audio × MCQ |
| **TCS** | **TCS iON blue** window chrome | A Short Questions (spoken) · B Read Aloud · C Conversation (respond to situation) · D Listen & Repeat · E Fill in the Blanks · F Correct the Sentence · G Free Speech |
| **Infosys** | Same iON-family blue | Identical 7-section set to TCS (A–G) |
| **Wipro** | **SHL/SVAR** platform, device-test flow | A Short Questions + Read&Speak · B Conversation · C Read&Speak · D Listen&Repeat · E Fill in the Blanks (spoken) · F Correct the Sentence (spoken) · G Free Speech (30s prep→45s) + a Listening-Comprehension MCQ |
| **Versant** | **Teal / halftone-dots**, headphones, "Now …" cues | A Reading (read on cue, stop at beep) · B Repeat (16 word-for-word) · C Questions (1–4 word spoken answers) · D Sentence Builds (rearrange heard words, say it) · E Story Retelling (hear once → retell 30s) · F Open Questions (heard twice → speak 40s) |
| **SpeechX** | **Mercer \| Mettl** dark-navy + gold ring, section picker | A read&record (18) · B speak topics (3–4, 30s think→1 min) · C grammar (34) · D passages (16) — section picker, "Revisit later", section+total timers |

## 2. Module mapping — what we already have vs. what's new

**Already supported task types** (no new engine work): `read_aloud`, `repeat_sentence`,
`short_answer` (spoken answer to a heard question), `conversation_question`,
`story_retell`, `sentence_build`, `open_response`, `sentence_completion`,
`voice_change`, `listening_comprehension`, `reading_comprehension`,
`vocabulary_in_context`. Content banks exist for all of these except
`conversation_question`.

**New task types for exact fidelity (optional, phased):**
- `read_words` — read a list of isolated words aloud (Cognizant Q11–15). A
  `read_aloud` variant with word-list content and word-clarity scoring.
- `spoken_completion` — hear a sentence with a gap, say the **whole** sentence
  with the word filled (Wipro/TCS/Infosys E). Spoken, not the typed C1.
- `spoken_correction` — hear a sentence with an error, say the corrected
  sentence (TCS/Infosys/Wipro F). Spoken.

Where a new type isn't built yet, the format uses the closest existing type
(e.g. E/F render as typed `sentence_completion`/`voice_change`) and is upgraded
to the spoken variant in a later phase — never shipped silently shorter.

## 3. UI-skin strategy — three families, one engine

The runner already themes SVAR via a `style` flag + `.svar` CSS. Generalise
that into **per-style skins**, so each format renders its authentic chrome
while reusing the one recording/timer/one-shot engine:

1. **`svar_style` family** (navy banners) — SVAR ✅, **Cognizant**, **SpeechX**
   (dark-navy + gold ring variant, section picker). Fastest wins: reuse the
   SVAR runner, restyle tokens, add the SpeechX section picker + Mettl top bar.
2. **`company_round` family** (**TCS iON blue** window chrome) — TCS, Infosys,
   Wipro. One skin, three formats. Blue section banner, iON-style card.
3. **`versant_style` family** (teal + halftone dots, headphones, "Now …" cues) —
   Versant. Distinct skin; story-retell + sentence-build spoken screens.

Each skin is verified the SVAR way: a throwaway harness renders every screen at
laptop viewports and is compared to the mockups before shipping.

## 4. Phased build

- **Phase 1 — authentic structure (backend, testable now).** Rebuild all six
  blueprints to match the researched section sets/counts/timings using existing
  task types; add the `conversation_question` content bank; smoke-test each
  format start→complete→score. *Formats become structurally real immediately,
  in the current (generic) skin.*
- **Phase 2 — UI skins.** Build the three skin families and wire each format's
  `style`. Verify against mockups via the harness. This is the bulk of the
  visual "SVAR-exact" work.
- **Phase 3 — exact task types + content depth.** `read_words`,
  `spoken_completion`, `spoken_correction`; expand content banks so questions
  vary candidate-to-candidate (ties into the SVAR C1/C2/A2 backlog).

## 5. Guardrails (unchanged from SVAR)

Deterministic scoring stays authoritative; no real assessment content is copied
(names are descriptive only, "-style"); one-shot audio and the whole-sitting
clock are server-enforced; every format is smoke-tested through the real
endpoints; `main` stays untouched until UAT + staging pass.


---

## 6. Implementation record (updated as delivered)

**Decisions taken (and why):**
- Cognizant keeps `style=company_round` (results present as a round verdict,
  not a vendor scale) and wears the navy SVAR skin via a company-based skin
  override in the runner (`skinFor`). Style = presentation family; skin = look.
- SpeechX reports four sub-scores (Pronunciation, Fluency, Grammar,
  Comprehension), equal weights. The researched A–D format has no
  content-bearing section, so the earlier Vocabulary sub-score was dropped
  rather than fed with an invented number. Grammar draws from the typed/chosen
  grammar rounds as well as speech; Comprehension from the passage round.
- TCS/Infosys/Wipro E ("Fill in the Blanks") and F ("Correct the Sentence")
  are served as the typed/chosen grammar tasks (`sentence_completion`,
  `voice_change`) until the spoken variants exist (Phase 3) — same grammar
  signal by a different channel, documented on the format card.
- The JAM section (no researched round has one) was removed with its test;
  the researched free-speech section (30s prep → 60s) replaced it.
- Company-round conversation sections play their situation once
  (`prompt_plays_allowed=1`) because the bank stores it as heard audio.
- The company-round task-type whitelist test now derives from
  `DIMENSIONS_BY_TASK`: rounds legitimately contain select/write sections.

**Seeding:** `python -m app.reseed_formats` (dev-only) force-applies the six
canonical blueprints despite the attempts guard, purging only those profiles'
dev attempts in FK order. SVAR and every other profile untouched. Applied to
stmarys + vignan; verified section-by-section.

**Skins:** one shell (`.svar` markup) + token-override classes
`skin-ion` / `skin-mettl` / `skin-versant`; visually verified against the
decks in a browser harness (deleted after verification).

**Verification status:** template invariants, company-round suite, evaluation
suite and the all-formats E2E smoke (`test_legacy_smoke`: all six + 
professional_english start→complete→score) green; frontend tsc + production
build green. Real-microphone UAT of the new skins pending (same limitation as
SVAR: the sandbox has no mic).

**Acceptance review (post-delivery) — deviations rejected and fixed:**
- TCS/Infosys/Wipro E/F are now genuinely SPOKEN (`spoken_completion`,
  `spoken_correction`): hear the gapped/flawed sentence, say the whole correct
  one; scored as scripted speech (accuracy vs the corrected reference is the
  grammar signal). The typed substitution was rejected — the channel is part
  of the assessment.
- Cognizant word-list reading exists (reserved difficulty band 1.2; its own
  Section A part). Company read-aloud pools capped at difficulty 1.0, which
  also fixed a pre-existing paragraph leak.
- conversation_question bank 4 → 10 (three formats draw 3 each).
- Skinned write tasks: the single-line fill-the-blank tile applies only to
  sentence_completion; other write tasks keep the full editor in every skin.
- Company-round banner word is "Section" (every researched deck), not "Round".
- `reseed_formats` refuses to run without `ALLOW_DEV_RESEED=1`.
- The E2E smoke asserts the spoken grammar sections actually produce scores —
  a decorative section fails the suite.

**Known source limitations:** proprietary scoring algorithms are not public —
sub-score mappings are our documented approximations; the SpeechX section
picker (choose your section order) is not implemented — sections run in
sequence; Versant Part A shows one sentence at a time rather than a numbered
list read on cue, and Part F questions play once, not twice.

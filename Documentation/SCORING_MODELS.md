# How each format is scored

**One engine, several bookkeepings.** Every dimension — pronunciation,
accuracy, fluency, latency, disfluency, grammar, content — is measured once,
per response, by the frozen pipeline. What differs between formats is which
responses count towards which sub-score, and how the sub-scores combine.

That mapping lives in one place: [`backend/app/evaluation.py`](../backend/app/evaluation.py).
It is deliberately a table. **If you have the official technical manuals,
correct it there** — nothing else needs to change.

---

## What is documented, and what is ours

This distinction matters more than any number below, and it is the thing to
push back on first if you know better.

| | Source |
|---|---|
| Sub-score **names** | Published test descriptions |
| Which **task types** feed each sub-score | Published test descriptions |
| Versant sub-score **weighting** (30/30/20/20) | Published |
| SVAR and SpeechX weighting | **Not published anywhere.** Equal here — an invented hierarchy would be worse than an admitted absence |
| Which of **our measures** stand in for each sub-score | **Ours.** No vendor publishes this, and could not: they are our measures |
| The actual **scoring algorithms** | **Not reproduced.** Proprietary, and not derivable from public information |

**No number produced here has been checked against a real result from the test
being imitated.** That needs a concordance study — the same speakers sitting
both tests — which has not been run. Every format score in the product is
labelled estimated, and for SVAR and SpeechX no number is shown at all, only a
band. See [VALIDATION_PROTOCOL.md](VALIDATION_PROTOCOL.md).

---

## Versant-style

Four sub-scores, weighted. The most fully documented of the three.

| Sub-score | Weight | Built from these tasks | Using these measures |
|---|---|---|---|
| Sentence Mastery | 30% | Repeat Sentence, Short Answer, Sentence Build | accuracy, grammar |
| Vocabulary | 30% | Short Answer, Story Retell | content, accuracy |
| Fluency | 20% | Read Aloud, Repeat Sentence, Sentence Build | fluency, latency, disfluency |
| Pronunciation | 20% | Read Aloud, Repeat Sentence, Sentence Build | pronunciation |

**Read Aloud does not count towards Sentence Mastery.** Reading a sentence off
a screen demonstrates nothing about holding one in memory and producing it, so
including it would let a fluent reader who cannot repeat a sentence score well
on the wrong thing. This is the single most important line in the table and
there is a test pinning it.

**Open Response contributes to nothing.** The published Versant scoring does
not include the open-ended task in the automatic score. Our engine measures it
anyway — it appears in the internal composite and the per-item diagnosis — but
it is excluded from the Versant-style view, because including it would make
the view something other than Versant-style.

**Known divergence:** the real test counts Short Answer towards Sentence
Mastery. Our engine produces no accuracy or grammar measure for a one-or-two
word answer, so it cannot contribute here. The report names the tasks each
sub-score actually used, so this is visible rather than hidden.

## SVAR-style

| Sub-score | Weight | Built from these tasks | Using these measures |
|---|---|---|---|
| Pronunciation | 25% | Read Aloud, Repeat Sentence | pronunciation |
| Fluency | 25% | Read Aloud, Repeat Sentence, Story Retell, Open Response | fluency, disfluency |
| Active Listening | 25% | Repeat Sentence, Short Answer, Story Retell | accuracy, content, latency |
| Grammar | 25% | Story Retell, Open Response, Sentence Build | grammar |

Active Listening excludes Read Aloud for the same reason Sentence Mastery
does: you cannot demonstrate listening by reading.

## SpeechX-style

| Sub-score | Weight | Built from these tasks | Using these measures |
|---|---|---|---|
| Pronunciation | 25% | Read Aloud, Repeat Sentence | pronunciation |
| Fluency | 25% | Read Aloud, Repeat Sentence, Open Response | fluency, latency, disfluency |
| Vocabulary | 25% | Short Answer, Open Response | content, accuracy |
| Grammar | 25% | Open Response, Short Answer | grammar |

## Company rounds

No sub-scores and no scale. A company round reports an outcome —
*Likely to clear / Borderline / Not yet / Well short* — because "would I have
got through" is the only thing the student is about to find out. Thresholds
are in [`backend/app/formats.py`](../backend/app/formats.py) and are authoring
estimates on the internal composite.

---

## Reporting rules

**A sub-score needs at least two scored responses.** One response wearing a
category name is not a measurement of it. Below that the sub-score is listed
under *Not reported for this attempt*, with what it needed — not silently
dropped, because dropping it changes what the overall means.

**An overall needs at least two surviving sub-scores**, otherwise it is one
sub-score relabelled. The weighting is renormalised over what survived.

**The internal composite stays the headline.** The format score sits below it.
Ours is the one comparable across formats and the one the validation study
will measure; the format view is orientation.

---

## Scales

| Format | Reported as | Why |
|---|---|---|
| Versant-style | Number on 20–80, plus band | The internal scale was built on this range, so restating a score on it is arithmetic, not a claim |
| SVAR-style | **Band only** | No data relates our range to theirs. Stretching 20–80 onto 0–100 inflates: an internal 70 would read as 83, and 77.5 as 96 |
| SpeechX-style | **Band only** | As above |
| Company rounds | Outcome | Not a scale at all |

Bands: Beginning / Developing / Competent / Strong, at 0%, 30%, 55% and 75% of
the internal range.

---

## The freeze

None of this is inside the frozen scoring path. `evaluation.py` consumes
values the pipeline already produced and decides which to average; it cannot
move a dimension score. `validation-baseline-v2` (`7cb4b39ddff4056b`) is
unaffected, which is the only reason this could be built during a
data-collection freeze.

Run `python -m app.validate freeze --study <name>` to confirm after any change
here — the drift check will say `none` if the scoring path is untouched.

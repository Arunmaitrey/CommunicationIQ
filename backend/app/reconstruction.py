"""Scoring a passage reconstruction.

Deliberately not ``score_essay``. Three of its five measures would be
measuring the wrong person:

* **lexical range** would score the *author's* vocabulary. A candidate who
  faithfully reproduces a passage full of varied words scores well for range
  they did not choose.
* **coherence** would score the author's paragraphing and connectives, for
  the same reason.
* **task_response's length gate** treats anything under forty words as
  unjudgeable. Forty words is right for an email and wrong here -- a
  fifty-word passage reconstructed in thirty-five words is a *partial*
  reconstruction, which is exactly the observation this task exists to make.
  Refusing to score it would throw away the measurement.

What is left is what reconstruction is actually about:

* **content** -- how many of the passage's ideas came back, matched through
  cues so a paraphrase counts. This is the measure.
* **grammar** -- whether they came back as English. Reused unchanged from the
  writing module, including its own stated limits.

``verbatim_share`` is recorded and not scored. The passage is in the runner
payload because the browser has to render it, so a candidate who reads it back
out of the network tab is possible; a long word-for-word run is visible in the
evidence rather than silently rewarded. Turning it into a penalty would need a
threshold nobody has calibrated, and a student who genuinely remembered a
sentence well would pay it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.writing import Measure, _band, _words, grammatical_accuracy, mechanics

# Under this many words there is no reconstruction to judge -- an answer of
# three words has not attempted the task. Far below the essay floor on
# purpose: a short reconstruction is a low score, not an unscorable one.
MIN_WORDS = 8

# How long a passage may be looked at, per word. Roughly a hundred words a
# minute -- half normal reading speed, because the task is to hold it rather
# than to have read it. Bounded at both ends so a very short passage still
# gets a usable look and a long one does not become an exercise in
# note-taking.
SECONDS_PER_WORD = 0.6
MIN_READING_SECONDS = 15
MAX_READING_SECONDS = 45


def reading_seconds(word_count: int) -> int:
    """How long this passage stays on screen before it is taken away."""
    if word_count <= 0:
        return MIN_READING_SECONDS
    return int(min(MAX_READING_SECONDS,
                   max(MIN_READING_SECONDS, round(word_count * SECONDS_PER_WORD))))


@dataclass
class ReconstructionScore:
    measures: list[Measure] = field(default_factory=list)
    word_count: int = 0
    source_words: int = 0
    verbatim_share: float = 0.0
    too_short: bool = False
    notes: list[str] = field(default_factory=list)


def content_recall(text: str, idea_units: list) -> Measure:
    """How many of the passage's ideas came back, in any words.

    Cue matching rather than string comparison against the source, because
    the task asks for a reconstruction and not a copy. "They moved it to
    Monday" and "the review is now on Monday" retain the same unit, and a
    measure that scored only one of them would be measuring recall of
    phrasing.
    """
    lowered = text.lower()
    written = set(_words(text))

    hit: list[str] = []
    missed: list[str] = []
    for entry in idea_units:
        if isinstance(entry, dict):
            label = str(entry.get("point", ""))
            cues = [str(c).lower() for c in entry.get("cues", []) if c]
        elif isinstance(entry, (list, tuple)) and len(entry) == 2:
            label, cues = str(entry[0]), [str(c).lower() for c in entry[1] if c]
        else:
            label, cues = str(entry), []

        if cues:
            covered = any(cue in lowered for cue in cues)
        else:
            terms = [w for w in _words(label) if len(w) > 3]
            covered = bool(terms) and any(w in written for w in terms)

        (hit if covered else missed).append(label)

    total = len(hit) + len(missed)
    coverage = len(hit) / total if total else 0.0

    return Measure(
        name="content_recall",
        score=_band(coverage),
        confidence=0.65 if total else 0.0,
        basis=f"{len(hit)} of {total} ideas from the passage came back",
        detail={"covered": hit, "missing": missed},
    )


def verbatim_share(text: str, source: str, run: int = 6) -> float:
    """The share of the answer sitting inside a long word-for-word run.

    Evidence, not a score. ``run`` is six words because five-word overlaps
    happen honestly ("the report is due on Friday") and six rarely do.
    """
    answer = _words(text)
    if len(answer) < run:
        return 0.0

    src = " ".join(_words(source))
    inside: set[int] = set()
    for start in range(len(answer) - run + 1):
        window = " ".join(answer[start:start + run])
        if window and window in src:
            inside.update(range(start, start + run))
    return round(len(inside) / len(answer), 3)


async def score(text: str, *, idea_units: list, source: str) -> ReconstructionScore:
    """Content recall plus grammar. No overall -- the two do not average.

    A reconstruction that retained every idea in broken English and one that
    retained half of them in clean English are different results, and one
    number would hide which. The section rollup averages them the same way it
    averages any two dimensions; what this refuses to do is publish a
    reconstruction-specific composite that implies the two trade off.
    """
    count = len(_words(text))
    source_count = len(_words(source))
    share = verbatim_share(text, source)

    if count < MIN_WORDS:
        return ReconstructionScore(
            measures=[], word_count=count, source_words=source_count,
            verbatim_share=share, too_short=True,
            notes=[f"{count} words is not an attempt at the passage. Nothing "
                   f"has been scored rather than scoring it as wrong."],
        )

    measures = [content_recall(text, idea_units), await grammatical_accuracy(text)]
    # Mechanics only once there is enough text for capitalisation and full
    # stops to be a pattern rather than one slip.
    if count >= 25:
        measures.append(mechanics(text))

    notes = ["Scored on which ideas came back and whether they came back as "
             "English. Not on your choice of words -- they are the passage's "
             "words, not yours."]
    if share >= 0.5:
        notes.append("Much of this answer matches the passage word for word. "
                     "That is recorded but not marked down.")

    return ReconstructionScore(
        measures=measures, word_count=count, source_words=source_count,
        verbatim_share=share, notes=notes)


def strip_cues(idea_units: list) -> list[str]:
    """The idea labels with their cue words removed.

    The cues are what the scorer looks for. Sending them to the browser would
    let a candidate paste them in and score full recall of a passage they
    never read -- the same rule the writing prompt already follows.
    """
    out: list[str] = []
    for entry in idea_units:
        if isinstance(entry, dict):
            out.append(str(entry.get("point", "")))
        elif isinstance(entry, (list, tuple)) and entry:
            out.append(str(entry[0]))
        else:
            out.append(str(entry))
    return [o for o in out if o]


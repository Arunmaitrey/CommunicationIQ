"""Tier 1 — word accuracy against the item's reference text.

For Repeat Sentence this is the task: reproduce the sentence. For Read Aloud
it catches skipped, added and swapped words. It is computed by aligning the
recogniser's output against the reference and counting what moved.

Two honesty constraints shape it:

* It is **not** a pronunciation score. A word the recogniser recovered
  correctly might still be hard for a human panel to follow, and a word it
  missed might have been perfectly clear. Phoneme-level judgement needs a GOP
  model and is still not built.
* A word the model was *unsure* about is not counted as an error. Low ASR
  confidence is our uncertainty, not the student's mistake, and it lowers the
  reported confidence instead.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from app.engine.contracts.types import (AccuracyResult, ProviderMeta,
                                        TranscriptResult)

SCALE_MIN = 20.0
SCALE_MAX = 80.0

# Tasks with a right answer to align against.
#
# Short Answer is deliberately absent. Its reference is one or two words, and
# "a key" against "key" scores 50% word accuracy while being entirely correct —
# so it is judged on key-point coverage instead.
SCRIPTED_TASKS = {"read_aloud", "repeat_sentence", "sentence_build",
                  # The heard prompt is flawed/gapped; the reference is
                  # the correct sentence, and "did it come out" is the
                  # grammar signal the section exists to measure.
                  "spoken_completion", "spoken_correction"}

# Sentence Build is scored differently from the other two, and the difference
# is the point of the task.
#
# Read Aloud and Repeat Sentence ask "did the words come out". Sentence Build
# gives a candidate the words already -- jumbled -- and asks them to build a
# sentence, so what is being measured is the *arrangement*. Scored as ordinary
# word accuracy, saying all six words in the wrong order aligns to five of six
# and scores 83%: near-perfect marks for the one failure the task exists to
# detect. See ``_construction`` for what replaces that.
CONSTRUCTION_TASKS = {"sentence_build"}

# How the two halves of a construction score are balanced.
#
# Order dominates, because order is the task. Coverage is not zero-weighted
# because it is real evidence -- a candidate who used every given word has
# understood what they were asked to do and got the arrangement wrong, which
# is a different and more recoverable failure than one who dropped half the
# sentence.
#
# The exact split is a judgement, not a finding. No validation data stands
# behind 0.2/0.8, and it is written here as one number rather than buried in
# an expression so that a study can move it and this comment can be corrected
# rather than quietly contradicted.
COVERAGE_SHARE = 0.2
ORDER_SHARE = 0.8

_PUNCT = re.compile(r"[^\w']+")

# Below this, the recogniser is guessing. Treated as "unheard" rather than
# "wrong" — the difference matters to a student reading their own report.
LOW_CONFIDENCE = 0.45

# Whisper writes numbers as digits: a student who correctly says "nine" against
# a reference reading "nine" gets a transcript reading "9". Counting that as a
# substitution marks someone down for the recogniser's formatting habit, which
# is exactly the kind of false error that makes a report untrustworthy.
_UNITS = ["zero", "one", "two", "three", "four", "five", "six", "seven",
          "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen",
          "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
_TENS = {20: "twenty", 30: "thirty", 40: "forty", 50: "fifty",
         60: "sixty", 70: "seventy", 80: "eighty", 90: "ninety"}


def _spell(number: int) -> str | None:
    """Small whole numbers as words. Anything larger is left as digits.

    Deliberately narrow: the point is to stop "9" and "nine" reading as
    different words, not to build a number-to-text library.
    """
    if 0 <= number < 20:
        return _UNITS[number]
    if 20 <= number < 100:
        tens, unit = divmod(number, 10)
        word = _TENS[tens * 10]
        return word if unit == 0 else f"{word} {_UNITS[unit]}"
    if number in (100, 1000):
        return "hundred" if number == 100 else "thousand"
    return None


def normalise(text: str) -> list[str]:
    """Words, lowercased, stripped of punctuation, digits spelled out.

    Contractions are kept whole: "don't" and "do not" are a real difference in
    a repeat-back task, not a formatting artefact to normalise away.
    """
    tokens: list[str] = []
    for token in _PUNCT.sub(" ", text.lower()).split():
        if token.isdigit():
            spelled = _spell(int(token))
            if spelled:
                tokens.extend(spelled.split())
                continue
        tokens.append(token)
    return tokens


class ReferenceMatchAccuracy:
    """Capability: ``accuracy``."""

    contract_version = "1.0"
    provider_key = "reference_match"
    version = "0.1.0"

    async def score(self, *, transcript: TranscriptResult, reference_text: str,
                    task_type: str = "",
                    alternatives: tuple[str, ...] = ()) -> AccuracyResult:
        return self.analyse(transcript, reference_text, task_type,
                            alternatives=alternatives)

    def analyse(self, transcript: TranscriptResult, reference_text: str,
                task_type: str = "",
                alternatives: tuple[str, ...] = ()) -> AccuracyResult:
        meta = ProviderMeta(provider_id="", provider_key=self.provider_key,
                            version=self.version, tier=1)

        reference = normalise(reference_text)
        heard = normalise(transcript.text)

        if reference and task_type in CONSTRUCTION_TASKS:
            return _construction(reference, heard, transcript, meta,
                                 alternatives=alternatives or ())

        if not reference or task_type not in SCRIPTED_TASKS:
            # No right answer to compare against. Zero confidence, not zero score.
            return AccuracyResult(score=SCALE_MIN, confidence=0.0, meta=meta)

        if not heard:
            return AccuracyResult(
                score=SCALE_MIN, matched=0, reference_words=len(reference),
                accuracy=0.0, confidence=0.5,
                word_errors=[{"expected": w, "heard": "", "kind": "deletion"}
                             for w in reference],
                meta=meta,
            )

        matcher = SequenceMatcher(a=reference, b=heard, autojunk=False)
        matched = 0
        errors: list[dict] = []

        # Word timings let an error point at a moment in the recording, which
        # is what makes the annotated listen-back useful rather than decorative.
        timings = [w for w in transcript.words if w.word.strip()]

        def heard_at(index: int) -> dict:
            if 0 <= index < len(timings):
                w = timings[index]
                return {"start_ms": w.start_ms, "confidence": w.confidence}
            return {}

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                matched += i2 - i1
            elif tag == "replace":
                for offset in range(max(i2 - i1, j2 - j1)):
                    expected = reference[i1 + offset] if i1 + offset < i2 else ""
                    got = heard[j1 + offset] if j1 + offset < j2 else ""
                    errors.append({"expected": expected, "heard": got,
                                   "kind": "substitution", **heard_at(j1 + offset)})
            elif tag == "delete":
                for offset in range(i1, i2):
                    errors.append({"expected": reference[offset], "heard": "",
                                   "kind": "deletion"})
            elif tag == "insert":
                for offset in range(j1, j2):
                    errors.append({"expected": "", "heard": heard[offset],
                                   "kind": "insertion", **heard_at(offset)})

        accuracy = matched / len(reference)
        score = SCALE_MIN + accuracy * (SCALE_MAX - SCALE_MIN)

        # Confidence follows the recogniser. If it was unsure of the words it
        # did hear, we are correspondingly unsure of the score.
        mean_confidence = (sum(w.confidence for w in timings) / len(timings)
                           if timings else 0.0)
        confidence = round(min(0.8, 0.35 + 0.5 * mean_confidence), 2)
        if mean_confidence < LOW_CONFIDENCE:
            confidence = round(confidence * 0.6, 2)

        return AccuracyResult(
            score=round(score, 1),
            matched=matched,
            reference_words=len(reference),
            accuracy=round(accuracy, 3),
            word_errors=errors[:40],
            confidence=confidence,
            meta=meta,
        )


def _lcs(a: list[str], b: list[str]) -> int:
    """Longest common subsequence length. Order-respecting by construction."""
    if not a or not b:
        return 0
    previous = [0] * (len(b) + 1)
    for x in a:
        current = [0]
        for j, y in enumerate(b):
            current.append(previous[j] + 1 if x == y
                           else max(current[j], previous[j + 1]))
        previous = current
    return previous[-1]


def _coverage(reference: list[str], heard: list[str]) -> float:
    """What share of the given words were used at all, order ignored.

    Multiset, not set: a reference with "the" twice is not satisfied by one
    "the". Counting distinct words would let a candidate drop half a repeated
    determiner and still read as complete.
    """
    from collections import Counter

    if not reference:
        return 0.0
    have = Counter(heard)
    used = sum(min(count, have[word]) for word, count in Counter(reference).items())
    return used / len(reference)


def _score_against(reference: list[str], heard: list[str]) -> tuple[float, float, float]:
    """(combined, coverage, order) for one candidate reference."""
    coverage = _coverage(reference, heard)
    # Denominator is the longer of the two, so padding the answer out with
    # extra words cannot raise the order share. Against `len(reference)`
    # alone, saying the sentence twice would score the same as saying it once.
    span = max(len(reference), len(heard)) or 1
    order = _lcs(reference, heard) / span
    return COVERAGE_SHARE * coverage + ORDER_SHARE * order, coverage, order


def _construction(reference: list[str], heard: list[str],
                  transcript: TranscriptResult, meta: ProviderMeta,
                  alternatives: tuple[str, ...] = ()) -> AccuracyResult:
    """Score a Sentence Build as a construction rather than a recitation.

    Two measures, because two different things go wrong and a single number
    that conflates them tells a candidate nothing:

    * **coverage** -- were the given pieces used at all. A candidate who
      leaves half the words out has not built the sentence.
    * **order** -- how much of the reference appears in sequence, over the
      longer of the two word lists so that padding cannot help.

    Scored against every accepted arrangement and the best one wins.
    ``alternatives`` comes from the item's rubric, and the bank does not
    currently carry any -- most of these sentences have exactly one natural
    arrangement, but not all do, and where a second is legitimate it is a
    content fix rather than a code one. The hook is read here so that stays
    true.
    """
    if not heard:
        return AccuracyResult(
            score=SCALE_MIN, matched=0, reference_words=len(reference),
            accuracy=0.0, confidence=0.5,
            word_errors=[{"expected": w, "heard": "", "kind": "deletion"}
                         for w in reference],
            meta=meta,
        )

    candidates = [reference] + [normalise(alt) for alt in alternatives]
    best, coverage, order = max(
        (_score_against(c, heard) for c in candidates if c),
        key=lambda triple: triple[0],
        default=(0.0, 0.0, 0.0))

    errors: list[dict] = []
    # The characteristic failure gets named rather than being broken into
    # substitutions that read as though the candidate said the wrong words.
    # They did not: they said the right words in the wrong places, and a
    # report that says "substitution" there is actively misleading.
    if coverage >= 0.9 and order < 0.8:
        errors.append({
            "expected": " ".join(reference), "heard": " ".join(heard),
            "kind": "word_order",
        })

    timings = [w for w in transcript.words if w.word.strip()]
    mean_confidence = (sum(w.confidence for w in timings) / len(timings)
                       if timings else 0.0)
    confidence = round(min(0.8, 0.35 + 0.5 * mean_confidence), 2)
    if mean_confidence < LOW_CONFIDENCE:
        confidence = round(confidence * 0.6, 2)

    return AccuracyResult(
        score=round(SCALE_MIN + best * (SCALE_MAX - SCALE_MIN), 1),
        matched=_lcs(reference, heard),
        reference_words=len(reference),
        accuracy=round(best, 3),
        word_errors=errors,
        confidence=confidence,
        meta=meta,
    )

"""The one answer to "what should I work on first?"

Before this module the result page computed that answer three times, by
three different rules, and showed all three:

* ``engine.pipeline.biggest_lever`` -- the LOWEST-SCORING composite dimension,
  with the gain the overall would make if it matched the student's best.
* ``reporting.recommendations`` (which wrote the summary sentence) -- the
  dimension with the LARGEST WEIGHTED GAIN. Pronunciation carries 0.20 of the
  overall and Content 0.07, so on a student whose Content (20.0) and
  Pronunciation (20.6) were level, the lever said Content (+4.2) and the
  sentence said Pronunciation (+11.9).
* ``priorities.priorities_for`` -- the lowest score among dimensions with at
  least two answers, with the lever pinned on top -- and an evidence line
  asserting "your report names this as the change that would lift your score
  most", which the report did not.

Three rules, one set of numbers, three answers. This module is now the only
place that rule lives. Everything downstream -- the summary sentence, the
result card, the practice buttons, the practice result, the AI narration --
consumes the object built here and is forbidden (by test) from choosing
differently.

The rule, in the order the product owner set it:

1. Only a MEASURED dimension can be the primary. Unmeasured is a gap in
   evidence, not evidence of weakness.
2. Only with ENOUGH evidence: at least ``MIN_RESPONSES`` answers measured it.
   One answer is an anecdote.
3. Only if it is GENUINELY WEAK relative to this attempt's other measured
   dimensions: at least ``CLEAR_MARGIN`` below the student's own best.
4. Only if the product has a TARGETED PRACTICE for it that actually runs.
5. Among the dimensions that pass 1-4, the LOWEST SCORE is the primary --
   unless another passes within ``TIE_BAND`` of it, in which case there is
   no primary and the product says so rather than inventing one.

The weighted "biggest lever" is deliberately not the rule. The overall's
weights are an internal, uncalibrated composite; "work on pronunciation
because it carries more of our composite than content" is advice about our
arithmetic, not about the student. The weakest measured, practisable area is
something the student can see in their own numbers and act on.

Every threshold here is a PRODUCT RULE, stated as such. None claims
statistical backing, and the copy never does either.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.priorities import PRACTICE_CODE

# Evidence threshold: one answer is an anecdote, not a pattern.
MIN_RESPONSES = 2

# Two dimensions closer than this are "effectively tied": we will not call
# one of them the single weakest on a 60-point, uncalibrated scale.
TIE_BAND = 3.0

# The weakest must sit at least this far below the student's own best
# measured dimension before it is called a weak spot at all. Mirrors
# reporting.STRENGTH_MARGIN -- below this, a difference is rounding.
CLEAR_MARGIN = 3.0

# How many answers make the verdict "solid" rather than "moderate". A label
# for the student, not a statistic.
SOLID_RESPONSES = 5

# Student-facing names. Mirrors frontend/lib/dimensions.ts DIMENSION_LABEL;
# a test holds the two in step.
LABEL: dict[str, str] = {
    "fluency": "Fluency",
    "latency": "Response speed",
    "accuracy": "Word accuracy",
    "disfluency": "Hesitation",
    "pronunciation": "Pronunciation",
    "grammar": "Grammar",
    "content": "Content",
    "completeness": "Completeness",
    "comprehension": "Comprehension",
    "vocabulary": "Vocabulary",
    "appropriacy": "Choosing what to say",
}

IDENTIFIED = "identified"      # one clear primary
TIED = "tied"                  # two or more level at the bottom
LEVEL = "level"                # everything close together -- no weak spot
INSUFFICIENT = "insufficient"  # nothing measured on enough answers
NONE = "none"                  # nothing measured at all

NO_CLEAR_WINNER = "Nothing clearly stands out yet"
NOT_ENOUGH = "Not enough evidence to identify one clear weakness yet"


def label(dimension: str) -> str:
    return LABEL.get(dimension, dimension.replace("_", " ").capitalize())


@dataclass(frozen=True)
class Candidate:
    dimension: str
    score: float
    responses: int


@dataclass(frozen=True)
class PrimaryDiagnosis:
    """The authoritative answer, with everything a surface needs to show it.

    ``status`` is the verdict. ``dimension`` is set only when IDENTIFIED.
    ``candidates`` is the tied group when TIED, otherwise the dimensions that
    were eligible. ``headline`` / ``reason`` / ``evidence`` are the student
    copy: what to work on, why we say it, what it was measured from.
    """
    status: str
    headline: str
    reason: str
    evidence: str = ""
    dimension: str = ""
    label: str = ""
    score: float | None = None
    responses: int = 0
    scale_max: float = 100.0
    confidence: str = ""           # solid | moderate | ""
    practice_code: str = ""
    candidates: tuple[Candidate, ...] = field(default_factory=tuple)
    # Dimensions that scored lower than the primary but could not be it, and
    # why -- shown rather than hidden, so the student is never told "X is
    # your weakest" while a lower number sits on the same page unexplained.
    excluded: tuple[tuple[str, str], ...] = field(default_factory=tuple)


def _n(score: float) -> str:
    return f"{score:.0f}"


def diagnose(dimensions: dict[str, float], *, scale_max: float = 100.0,
             response_counts: dict[str, int] | None = None,
             available_practice: set[str] | None = None) -> PrimaryDiagnosis:
    """Apply the rule above to one attempt's measured dimensions.

    ``available_practice`` is the set of practice profile codes that exist
    and are published for this tenant; ``None`` means every mapped code is
    assumed present (pure unit tests). A dimension whose practice is not
    runnable cannot be the primary -- the button must never promise a
    session the tenant does not have.
    """
    counts = response_counts or {}
    measured = {d: float(s) for d, s in dimensions.items() if d != "overall"}
    if not measured:
        return PrimaryDiagnosis(
            status=NONE, headline=NOT_ENOUGH,
            reason=("Nothing was measured on this attempt, so there is no "
                    "area to point at yet."),
            scale_max=scale_max)

    excluded: list[tuple[str, str]] = []
    eligible: list[Candidate] = []
    for d, s in sorted(measured.items(), key=lambda p: p[1]):
        n = int(counts.get(d, 0))
        code = PRACTICE_CODE.get(d, "")
        if not code:
            excluded.append((d, "we do not have a targeted practice for it yet"))
            continue
        if available_practice is not None and code not in available_practice:
            excluded.append((d, "its practice session is not available here"))
            continue
        if n < MIN_RESPONSES:
            excluded.append((d, "it was measured on only one answer" if n == 1
                             else "no answer measured it"))
            continue
        eligible.append(Candidate(dimension=d, score=s, responses=n))

    best = max(measured.values())

    if not eligible:
        lows = [label(d) for d, _ in excluded][:3]
        return PrimaryDiagnosis(
            status=INSUFFICIENT, headline=NOT_ENOUGH,
            reason=("Too few answers measured each area to say which needs "
                    "work first. Another attempt will make the picture "
                    "clearer."),
            evidence=_excluded_line(excluded) if lows else "",
            scale_max=scale_max, excluded=tuple(excluded))

    weakest = eligible[0]
    # Only lower-scoring exclusions are worth explaining next to the answer.
    lower_excluded = tuple((d, why) for d, why in excluded
                           if measured[d] < weakest.score - TIE_BAND)

    if best - weakest.score < CLEAR_MARGIN:
        return PrimaryDiagnosis(
            status=LEVEL, headline=NO_CLEAR_WINNER,
            reason=("Your measured areas are all close together, so there is "
                    "no single weak spot to attack yet. Steady practice "
                    "across the board, then another attempt, is the right "
                    "next step."),
            evidence=_spread_line(eligible, scale_max),
            scale_max=scale_max, candidates=tuple(eligible),
            excluded=lower_excluded)

    tied = [c for c in eligible if c.score - weakest.score < TIE_BAND]
    if len(tied) > 1:
        names = [label(c.dimension) for c in tied]
        joined = ", ".join(names[:-1]) + " and " + names[-1]
        either = "either" if len(tied) == 2 else "any of them"
        return PrimaryDiagnosis(
            status=TIED, headline=NO_CLEAR_WINNER,
            reason=(f"{joined} were measured at about the same level, lower "
                    "than your other areas. We need a little more evidence "
                    "before we can tell you which one will help most -- "
                    f"practising {either} is a good use of the time."),
            evidence=_spread_line(tied, scale_max),
            scale_max=scale_max, candidates=tuple(tied),
            excluded=lower_excluded)

    name = label(weakest.dimension)
    confidence = "solid" if weakest.responses >= SOLID_RESPONSES else "moderate"
    evidence = (f"Your {name.lower()} score was lower than your other "
                f"measured areas across {weakest.responses} answers "
                f"({_n(weakest.score)} of {_n(scale_max)}).")
    if lower_excluded:
        evidence += " " + _excluded_line(lower_excluded)
    return PrimaryDiagnosis(
        status=IDENTIFIED, headline=name,
        reason=(f"Your {name.lower()} needs the most attention based on the "
                "answers we measured."),
        evidence=evidence,
        dimension=weakest.dimension, label=name, score=round(weakest.score, 1),
        responses=weakest.responses, scale_max=scale_max,
        confidence=confidence, practice_code=PRACTICE_CODE[weakest.dimension],
        candidates=tuple(eligible), excluded=lower_excluded)


def _spread_line(cands: list[Candidate], scale_max: float) -> str:
    return "; ".join(
        f"{label(c.dimension)} {_n(c.score)} of {_n(scale_max)} across "
        f"{c.responses} answer{'s' if c.responses != 1 else ''}"
        for c in cands) + "."


def _excluded_line(excluded) -> str:
    parts = [f"{label(d)} was lower, but {why}" for d, why in excluded[:2]]
    return "; ".join(parts) + ", so we do not rely on it yet."


def first_practice(diagnosis: PrimaryDiagnosis) -> str:
    """The practice code the first button must start, or "" when there is
    honestly nothing to prescribe. The one place that decision is made."""
    return diagnosis.practice_code if diagnosis.status == IDENTIFIED else ""

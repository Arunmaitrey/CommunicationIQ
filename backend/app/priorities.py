"""What a student should practise next, from one attempt's measurements.

Turns the scored dimensions of a single attempt into at most three plain
priorities, each pointing at a practice surface that actually runs. Pure
functions over data the result endpoint already has, so every ranking rule is
an ordinary unit test — and so the router stays free of product logic.

Honesty rules, inherited from the report this feeds:
* Only *measured* dimensions can become priorities. An unscored dimension is
  a gap in evidence, not evidence of weakness.
* The evidence line states what was measured — a score, on a scale, over a
  number of answers. It never claims a cause the data cannot support.
* The order is the primary diagnosis's order (app/diagnosis.py): the
  identified primary leads, a tied group leads together, and nothing here
  ever chooses a different first answer than the diagnosis did.
"""
from __future__ import annotations

from dataclasses import dataclass

# Where each weakness is actually practised. "speaking" starts a short
# practice-mode speaking session through the ordinary runner; the others are
# the existing practice modules. Every value must be a surface that runs —
# a destination that is really a checkbox is worse than no button.
PRACTICE_SURFACE: dict[str, str] = {
    "pronunciation": "speaking",
    "fluency": "speaking",
    "disfluency": "speaking",
    "latency": "speaking",
    "accuracy": "speaking",
    "completeness": "speaking",
    "content": "speaking",
    "grammar": "grammar",
    "vocabulary": "vocabulary",
    "comprehension": "listening",
    "appropriacy": "listening",
}

# The practice profile each weakness starts (app/formats.PRACTICE_BLUEPRINTS).
# Every code is a real, seeded, runnable session -- the button must never
# promise pronunciation and deliver a generic mock again.
PRACTICE_CODE: dict[str, str] = {
    "pronunciation": "practice_pronunciation",
    "fluency": "practice_fluency",
    "disfluency": "practice_fluency",
    "latency": "practice_latency",
    "accuracy": "practice_accuracy",
    "completeness": "practice_completeness",
    "content": "practice_content",
    "grammar": "practice_grammar",
    "vocabulary": "practice_vocabulary",
    "comprehension": "practice_comprehension",
    "appropriacy": "practice_appropriacy",
}

MAX_PRIORITIES = 3


@dataclass(frozen=True)
class Priority:
    dimension: str
    score: float
    responses: int
    practice: str      # speaking | grammar | vocabulary | listening
    practice_code: str  # the practice profile this starts
    # "needs_most" for the top priority, "needs_work" for the rest -- the
    # student-facing verdict leads; the number is supporting evidence.
    verdict: str
    evidence: str
    # What to actually do about it this week (reporting.ADVICE).
    advice: str = ""


def _evidence(score: float, scale_max: float, responses: int,
              where: str) -> str:
    over = (f" across {responses} answers" if responses > 1
            else " on the one answer that measured it" if responses == 1
            else "")
    return f"Measured at {score:.0f} of {scale_max:.0f}{over} — {where}."


def priorities_for(dimensions: dict[str, float], *, scale_max: float,
                   response_counts: dict[str, int] | None = None,
                   primary=None) -> list[Priority]:
    """At most three practice priorities, in the diagnosis's order.

    ``dimensions`` is the attempt-level measured map the result already
    carries. ``primary`` is the attempt's PrimaryDiagnosis: when it
    identified a dimension that one leads and is the only "needs_most";
    when it found a tie the tied group leads, none of them "needs_most";
    otherwise the list is simply weakest-first with no "needs_most" at all.
    This function never picks a first answer the diagnosis did not.
    """
    from app.reporting import _advice_for

    counts = response_counts or {}
    measured = [(d, s) for d, s in dimensions.items() if d in PRACTICE_SURFACE]
    if not measured:
        return []
    # Evidence threshold: one answer is an anecdote, not a pattern. Prefer
    # dimensions measured across at least two answers; fall back to the thin
    # evidence only when nothing better exists (the evidence line says so).
    solid = [p for p in measured if counts.get(p[0], 0) >= 2]
    if solid:
        measured = solid
    measured.sort(key=lambda pair: pair[1])
    by_dim = dict(measured)

    lead: list[str] = []
    status = getattr(primary, "status", "")
    if status == "identified" and getattr(primary, "dimension", "") in by_dim:
        lead = [primary.dimension]
    elif status == "tied":
        lead = [c.dimension for c in getattr(primary, "candidates", ())
                if c.dimension in by_dim]
    ordered = ([(d, by_dim[d]) for d in lead]
               + [p for p in measured if p[0] not in lead])

    out: list[Priority] = []
    for rank, (dimension, score) in enumerate(ordered[:MAX_PRIORITIES]):
        if status == "identified" and rank == 0:
            verdict, where = "needs_most", "your lowest measured area"
        elif status == "tied" and dimension in lead:
            verdict, where = "needs_work", "level with your other lowest area"
        else:
            verdict, where = "needs_work", "lower than your stronger areas"
        out.append(Priority(
            dimension=dimension,
            score=round(score, 1),
            responses=int(counts.get(dimension, 0)),
            practice=PRACTICE_SURFACE[dimension],
            practice_code=PRACTICE_CODE[dimension],
            verdict=verdict,
            evidence=_evidence(score, scale_max,
                               int(counts.get(dimension, 0)), where),
            advice=_advice_for(dimension),
        ))
    return out


# --------------------------------------------------------------------------
# Practice outcome verdicts
# --------------------------------------------------------------------------
#
# A 0.4-point movement between two DIFFERENT item sets is noise, and calling
# it "improvement" would teach students to distrust the product the first
# time it reverses. The band below is a PRODUCT RULE, deliberately
# conservative, and stated as such -- it is not a validated measurement
# threshold, and nothing in the UI claims statistical backing. Within the
# band the honest verdict is "level"; with fewer than two measured answers
# the honest verdict is that there is no verdict.

PRACTICE_LEVEL_BAND = 5.0
PRACTICE_MIN_RESPONSES = 2


def practice_verdict(change: float | None, practice_responses: int) -> str:
    """higher | level | lower | insufficient — what one session can claim."""
    if change is None or practice_responses < PRACTICE_MIN_RESPONSES:
        return "insufficient"
    if change >= PRACTICE_LEVEL_BAND:
        return "higher"
    if change <= -PRACTICE_LEVEL_BAND:
        return "lower"
    return "level"

"""Per-assessment weighting, thresholds and the pass decision.

**Why this is a separate module and not a change to the pipeline.**

``pipeline.compose_overall`` is inside ``SCORING_PATH``: it is hashed for the
validation study and must not move. It composes the engine's own view of a
candidate using a single global weight set, and that view stays exactly as it
is — comparable across every assessment, which is the whole reason it exists.

What an employer wants is a different question. A customer-support round cares
more about intelligibility than about grammatical range; a technical screen
may invert that. Answering it means re-weighting the *same* measured
dimensions, which is arithmetic on top of the engine rather than a change to
it. So it happens here, the same way ``evaluation.py`` already computes vendor
sub-scores above the frozen path.

Two numbers therefore exist, and both are shown:

* the **engine composite**, always on the same basis, comparable everywhere;
* the **role-weighted score**, which answers "against what this employer
  said they care about, how did this candidate do".

Reporting only the second would quietly make every assessment
incomparable with every other. Reporting only the first would make the
weights an admin configured a lie. Reporting one without the other is the
mistake this module exists to avoid.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# The engine's own weights. Duplicated here deliberately rather than imported:
# this module must keep working if the frozen set is ever re-cut, and the
# comparison between "engine default" and "what you configured" needs a
# stable reference. Kept in step by a test.
ENGINE_WEIGHTS: dict[str, float] = {
    "pronunciation": 0.20, "accuracy": 0.20, "fluency": 0.17,
    "latency": 0.11, "disfluency": 0.08, "grammar": 0.09, "content": 0.07,
    "completeness": 0.08,
}

# A weight set has to be close to 1. Not exactly, because an admin typing
# percentages will produce 0.999 or 1.001 and refusing that is pedantry.
WEIGHT_SUM_TOLERANCE = 0.02


@dataclass
class ThresholdCheck:
    dimension: str
    floor: float
    actual: float | None
    #  True when the candidate is at or above the floor. None when the
    #  dimension was never measured -- which is not a failure, and must not be
    #  reported as one.
    met: bool | None


@dataclass
class WeightedResult:
    # None when too few dimensions were measured to weight anything.
    score: float | None
    # The weights actually used, after validation and renormalisation.
    weights: dict[str, float]
    # True when `weights` is the engine default because none were configured.
    using_engine_default: bool
    # Dimensions the profile weighted that the attempt never measured. Named
    # rather than silently dropped: a round weighted 25% on content that
    # contains no content-bearing task is misconfigured, and the report is
    # where somebody notices.
    unmeasured: list[str] = field(default_factory=list)
    thresholds: list[ThresholdCheck] = field(default_factory=list)
    # None when the profile sets no pass mark -- correct for practice.
    passed: bool | None = None
    why: str = ""


def normalise(weights: dict) -> dict[str, float]:
    """Clean an admin-supplied weight set, or fall back to the engine's.

    Accepts percentages or fractions, because an admin typing "25" means 25%
    and refusing it teaches them nothing.
    """
    if not weights:
        return dict(ENGINE_WEIGHTS)

    cleaned = {str(k): float(v) for k, v in weights.items()
               if k in ENGINE_WEIGHTS and float(v) > 0}
    if not cleaned:
        return dict(ENGINE_WEIGHTS)

    total = sum(cleaned.values())
    if total <= 0:
        return dict(ENGINE_WEIGHTS)
    return {k: v / total for k, v in cleaned.items()}


def weights_are_valid(weights: dict) -> tuple[bool, str]:
    """Whether a weight set can be stored. Used by the builder, not at scoring."""
    if not weights:
        return True, ""

    unknown = [k for k in weights if k not in ENGINE_WEIGHTS]
    if unknown:
        return False, (f"Not a measured dimension: {', '.join(sorted(unknown))}. "
                       f"Available: {', '.join(sorted(ENGINE_WEIGHTS))}.")

    try:
        values = [float(v) for v in weights.values()]
    except (TypeError, ValueError):
        return False, "Every weight must be a number."

    if any(v < 0 for v in values):
        return False, "A weight cannot be negative."
    if not values or sum(values) <= 0:
        return False, "At least one weight must be above zero."

    total = sum(values)
    # Accept either fractions summing to 1 or percentages summing to 100.
    if abs(total - 1.0) > WEIGHT_SUM_TOLERANCE and abs(total - 100.0) > 1.0:
        return False, (f"Weights should add up to 1 (or 100 as percentages). "
                       f"These add up to {round(total, 3)}.")
    return True, ""


def apply(dimensions: dict[str, float], *, profile_weights: dict,
          pass_threshold: float | None, skill_thresholds: dict,
          min_dimensions: int) -> WeightedResult:
    """Weight what was measured, then decide pass or fail.

    Renormalises over the dimensions actually present, so an attempt that
    could not produce `content` is not penalised for its absence -- it is
    scored on what it did produce, and the gap is reported separately. The
    alternative, treating an unmeasured dimension as zero, would let a missing
    scorer look like a failing candidate.
    """
    weights = normalise(profile_weights)
    using_default = not profile_weights

    present = {d: v for d, v in dimensions.items() if d in weights}
    unmeasured = sorted(d for d in weights if d not in dimensions)

    score: float | None = None
    if len(present) >= min_dimensions:
        total_weight = sum(weights[d] for d in present)
        if total_weight > 0:
            score = round(
                sum(dimensions[d] * weights[d] for d in present) / total_weight, 1)

    checks: list[ThresholdCheck] = []
    for dimension, floor in sorted((skill_thresholds or {}).items()):
        actual = dimensions.get(dimension)
        checks.append(ThresholdCheck(
            dimension=dimension, floor=float(floor), actual=actual,
            met=None if actual is None else actual >= float(floor),
        ))

    passed: bool | None = None
    why = ""
    if pass_threshold is not None and score is not None:
        failed_floors = [c for c in checks if c.met is False]
        if failed_floors:
            passed = False
            names = ", ".join(c.dimension for c in failed_floors)
            why = (f"Overall {score} against a {pass_threshold} pass mark, but "
                   f"below the required minimum on {names}.")
        elif score >= pass_threshold:
            passed = True
            why = f"Overall {score}, at or above the {pass_threshold} pass mark."
        else:
            passed = False
            why = f"Overall {score}, below the {pass_threshold} pass mark."
    elif pass_threshold is not None:
        why = ("Not enough was measured to decide a pass. This is reported as "
               "undecided rather than as a failure.")

    return WeightedResult(
        score=score, weights=weights, using_engine_default=using_default,
        unmeasured=unmeasured, thresholds=checks, passed=passed, why=why,
    )

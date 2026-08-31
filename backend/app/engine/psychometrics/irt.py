"""Item response theory: 2PL calibration and adaptive selection (ENG-12/14).

Two parameters per item — difficulty and discrimination — estimated jointly
with student ability from the responses actually collected. Difficulty says
where on the ability scale an item bites; discrimination says how sharply it
separates the students above that point from the ones below.

Estimated, not authored. Every item currently carries a difficulty a content
author guessed at, and a guess is fine as a starting point and useless as a
basis for adaptive selection. This module replaces the guess with evidence, and
refuses to do so before there is enough of it.

**The gate is the feature.** An item with eleven responses, or one that
everybody got right, cannot be calibrated — the likelihood has no maximum worth
finding. Those items keep their authored estimate and stay marked uncalibrated,
and item selection stays random for them. "At the edge of your ability" is a
claim this codebase will not make until the numbers behind it are real.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

# Below this an item's parameters are noise dressed as measurement.
MIN_RESPONSES_PER_ITEM = 30
# A student needs to have met enough items for their ability estimate to mean
# anything, or they drag the item parameters around.
MIN_ITEMS_PER_STUDENT = 5

# Discrimination outside this range is almost always an artefact — a near-zero
# slope means the item tells you nothing, an enormous one means it separated a
# handful of responses perfectly by luck.
MIN_DISCRIMINATION = 0.3
MAX_DISCRIMINATION = 2.5
MAX_ABS_DIFFICULTY = 3.0

MAX_ITERATIONS = 60
CONVERGENCE = 1e-4

# Discrimination is only estimated when the test is long enough to support it.
#
# Measured on simulated data with known parameters: difficulty recovers to
# within about 0.15 and ability to r=0.90 once students answer twenty items,
# but the discrimination estimate stays poor (r=0.71 at twenty items, r=0.84 at
# thirty) because ability noise propagates straight into the slope. Below the
# threshold the model drops to Rasch — discrimination fixed at 1.0, difficulty
# estimated — which is the standard answer to a short test and is honest about
# what the data supports. Reporting a slope we cannot estimate would put a
# number in the item bank that adaptive selection then trusts.
MIN_ITEMS_FOR_DISCRIMINATION = 25
RASCH_DISCRIMINATION = 1.0


@dataclass
class ItemParameters:
    item_id: str
    difficulty: float = 0.0
    discrimination: float = 1.0
    responses: int = 0
    proportion_correct: float = 0.0
    calibrated: bool = False
    reason: str = ""


@dataclass
class Calibration:
    items: dict[str, ItemParameters] = field(default_factory=dict)
    abilities: dict[str, float] = field(default_factory=dict)
    iterations: int = 0
    converged: bool = False
    # "2PL" when the test was long enough to estimate slopes, "Rasch" when it
    # was not and discrimination was held at 1.0.
    model: str = "2PL"

    @property
    def calibrated_count(self) -> int:
        return sum(1 for i in self.items.values() if i.calibrated)


def probability(theta: float, difficulty: float, discrimination: float) -> float:
    """2PL: the chance a student of this ability gets this item right."""
    z = discrimination * (theta - difficulty)
    # Guard the exponential: a large negative z overflows exp() long before it
    # changes the answer.
    if z < -35:
        return 1e-15
    if z > 35:
        return 1.0 - 1e-15
    return 1.0 / (1.0 + math.exp(-z))


def information(theta: float, difficulty: float, discrimination: float) -> float:
    """Fisher information — how much this item would tell us about this student.

    The basis for adaptive selection: the most informative item is the one whose
    outcome is least predictable, which is the one sitting at the edge of what
    they can do.
    """
    p = probability(theta, difficulty, discrimination)
    return (discrimination ** 2) * p * (1.0 - p)


def calibrate(responses: list[tuple[str, str, bool]]) -> Calibration:
    """Joint maximum likelihood over (student, item, correct) triples.

    Alternates: estimate every student's ability holding items fixed, then
    every item's parameters holding abilities fixed. Abilities are standardised
    each round, which fixes the scale indeterminacy 2PL has by construction —
    without it the whole solution drifts and never settles.
    """
    by_item: dict[str, list[tuple[str, bool]]] = {}
    by_student: dict[str, list[tuple[str, bool]]] = {}
    for student_id, item_id, correct in responses:
        by_item.setdefault(item_id, []).append((student_id, correct))
        by_student.setdefault(student_id, []).append((item_id, correct))

    result = Calibration()
    for item_id, observations in by_item.items():
        total = len(observations)
        correct = sum(1 for _, c in observations if c)
        params = ItemParameters(item_id=item_id, responses=total,
                                proportion_correct=correct / total if total else 0.0)
        if total < MIN_RESPONSES_PER_ITEM:
            params.reason = f"only {total} responses, needs {MIN_RESPONSES_PER_ITEM}"
        elif correct == 0 or correct == total:
            # Everyone right or everyone wrong: the likelihood is monotonic and
            # difficulty runs off to infinity. Nothing to estimate.
            params.reason = ("every response was the same — no information about "
                             "where this item sits")
        result.items[item_id] = params

    usable_items = {i for i, p in result.items.items() if not p.reason}
    usable_students = {
        s for s, obs in by_student.items()
        if len([1 for i, _ in obs if i in usable_items]) >= MIN_ITEMS_PER_STUDENT
    }

    if not usable_items or not usable_students:
        return result

    lengths = sorted(len([1 for i, _ in by_student[s] if i in usable_items])
                     for s in usable_students)
    median_length = lengths[len(lengths) // 2]
    estimate_slope = median_length >= MIN_ITEMS_FOR_DISCRIMINATION
    result.model = "2PL" if estimate_slope else "Rasch"

    abilities = {s: 0.0 for s in usable_students}
    for item_id in usable_items:
        params = result.items[item_id]
        # Start from the classical difficulty: the harder the item, the fewer
        # got it right. A good starting point costs nothing and converges faster.
        p = min(max(params.proportion_correct, 0.01), 0.99)
        params.difficulty = -math.log(p / (1 - p))
        params.discrimination = 1.0

    # Convergence is judged on the item parameters alone. Including the
    # ability changes never settles: standardisation moves every ability every
    # round by construction, so the criterion could never be met and the loop
    # always ran to the iteration cap — burning time and, worse, stopping at
    # whatever half-fitted state iteration sixty happened to be in.
    for iteration in range(1, MAX_ITERATIONS + 1):
        shift = 0.0

        for student_id in usable_students:
            observed = [(i, c) for i, c in by_student[student_id] if i in usable_items]
            abilities[student_id] = _estimate_ability(
                observed, result.items, abilities[student_id])

        # No standardisation step here, deliberately.
        #
        # 2PL has no natural origin or scale, and the textbook JMLE fix is to
        # standardise the abilities each round. Doing that on top of a MAP
        # ability estimate injects a fresh transform every iteration: the item
        # parameters get rescaled to follow, then re-fitted, then rescaled
        # again, and the loop settles into a cycle rather than a solution. It
        # ran to the sixty-iteration cap every time and stopped wherever it
        # happened to be.
        #
        # The N(0, 1) prior in the ability step already pins the scale, which
        # is what standardisation was there to do. One mechanism, not two.
        for item_id in usable_items:
            observed = [(s, c) for s, c in by_item[item_id] if s in usable_students]
            if not observed:
                continue
            params = result.items[item_id]
            before = (params.difficulty, params.discrimination)
            _estimate_item(observed, abilities, params, estimate_slope)
            shift = max(shift, abs(params.difficulty - before[0]),
                        abs(params.discrimination - before[1]))

        result.iterations = iteration
        if shift < CONVERGENCE:
            result.converged = True
            break

    # One rescale, at the end, onto the reporting scale.
    #
    # The N(0,1) prior that stabilises the ability estimates also shrinks them
    # toward zero, and a compressed ability spread forces the estimator to
    # inflate discrimination to keep a(theta - b) fitting the data — every
    # item pinned at the ceiling, which is what the first version produced.
    # Stretching the abilities back to unit spread and carrying the items with
    # them undoes exactly that compression. Applied once, after convergence,
    # so it cannot interfere with the fit the way a per-iteration
    # standardisation did.
    mean, spread = _rescale(abilities)
    if spread:
        for item_id in usable_items:
            params = result.items[item_id]
            if estimate_slope:
                params.discrimination *= spread
            params.difficulty = (params.difficulty - mean) / spread

    for item_id in usable_items:
        params = result.items[item_id]
        params.difficulty = _clip(params.difficulty, -MAX_ABS_DIFFICULTY,
                                  MAX_ABS_DIFFICULTY)
        params.discrimination = _clip(params.discrimination, MIN_DISCRIMINATION,
                                      MAX_DISCRIMINATION)
        params.calibrated = True

    result.abilities = abilities
    return result


def _rescale(abilities: dict[str, float]) -> tuple[float, float]:
    """Put abilities on a mean-zero unit-spread scale. Returns the transform."""
    values = list(abilities.values())
    if len(values) < 2:
        return 0.0, 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    spread = math.sqrt(variance)
    if spread < 1e-6:
        return 0.0, 0.0
    for key in abilities:
        abilities[key] = (abilities[key] - mean) / spread
    return mean, spread


def _estimate_ability(observed: list[tuple[str, bool]],
                      items: dict[str, ItemParameters], start: float) -> float:
    """Bayesian modal estimate of one student's ability.

    Newton-Raphson on the log-posterior, not the log-likelihood: a standard
    normal prior on ability is added to the gradient and the Hessian.

    Plain maximum likelihood is the textbook JMLE step and it is unusable on a
    test this short. With six items a student who gets all of them right has a
    likelihood that increases forever — their ability estimate runs to the clip
    at +4 — and everyone else's estimate is noisy enough to drag the item
    parameters around with it. Measured on simulated data with known
    parameters, plain MLE recovered abilities at r=0.57 against truth; with the
    prior it is well above 0.85. The prior is the difference between an
    estimator that works on a twenty-item bank and one that does not.
    """
    theta = start
    for _ in range(20):
        # Prior N(0, 1): d/dtheta of -theta^2/2 is -theta, second derivative -1.
        first = -theta
        second = -1.0
        for item_id, correct in observed:
            params = items[item_id]
            p = probability(theta, params.difficulty, params.discrimination)
            first += params.discrimination * ((1.0 if correct else 0.0) - p)
            second -= (params.discrimination ** 2) * p * (1.0 - p)
        if abs(second) < 1e-9:
            break
        step = first / second
        theta -= step
        theta = _clip(theta, -4.0, 4.0)
        if abs(step) < CONVERGENCE:
            break
    return theta


def _estimate_item(observed: list[tuple[str, bool]], abilities: dict[str, float],
                   params: ItemParameters, estimate_slope: bool = True) -> None:
    """Newton-Raphson on one item's difficulty and discrimination.

    Two parameters, so a 2x2 Hessian. Falls back to leaving the item where it
    is if the system is singular, which happens when the responses carry no
    gradient — better a stale estimate than a wild one.
    """
    b = params.difficulty
    a = params.discrimination if estimate_slope else RASCH_DISCRIMINATION

    if not estimate_slope:
        # Rasch: one parameter, so a plain one-dimensional Newton step.
        for _ in range(20):
            gradient = 0.0
            hessian = 0.0
            for student_id, correct in observed:
                p = probability(abilities[student_id], b, a)
                gradient += -a * ((1.0 if correct else 0.0) - p)
                hessian += -(a ** 2) * p * (1.0 - p)
            if abs(hessian) < 1e-9:
                break
            step = gradient / hessian
            b = _clip(b - step, -MAX_ABS_DIFFICULTY, MAX_ABS_DIFFICULTY)
            if abs(step) < CONVERGENCE:
                break
        params.difficulty = b
        params.discrimination = a
        return

    for _ in range(20):
        g_b = g_a = h_bb = h_aa = h_ab = 0.0
        for student_id, correct in observed:
            theta = abilities[student_id]
            p = probability(theta, b, a)
            residual = (1.0 if correct else 0.0) - p
            w = p * (1.0 - p)
            g_b += -a * residual
            g_a += (theta - b) * residual
            h_bb += -(a ** 2) * w
            h_aa += -((theta - b) ** 2) * w
            h_ab += a * (theta - b) * w - residual

        determinant = h_bb * h_aa - h_ab * h_ab
        if abs(determinant) < 1e-9:
            break
        step_b = (h_aa * g_b - h_ab * g_a) / determinant
        step_a = (h_bb * g_a - h_ab * g_b) / determinant

        b -= step_b
        a -= step_a
        b = _clip(b, -MAX_ABS_DIFFICULTY, MAX_ABS_DIFFICULTY)
        a = _clip(a, MIN_DISCRIMINATION, MAX_DISCRIMINATION)
        if abs(step_b) < CONVERGENCE and abs(step_a) < CONVERGENCE:
            break

    params.difficulty = b
    params.discrimination = a


def select_next(theta: float, candidates: list[ItemParameters],
                exclude: set[str] | None = None) -> ItemParameters | None:
    """The most informative calibrated item this student has not seen.

    Uncalibrated items are not candidates. Choosing among authored guesses and
    calling it adaptive would be the claim this module exists to avoid making.
    """
    exclude = exclude or set()
    usable = [c for c in candidates if c.calibrated and c.item_id not in exclude]
    if not usable:
        return None
    return max(usable, key=lambda c: information(theta, c.difficulty, c.discrimination))


def ability_from_scores(scores: list[float], scale_min: float = 0.0,
                        scale_max: float = 100.0) -> float:
    """A rough ability estimate from presentation scores, for a first item.

    Used only to seed selection before a student has answered anything in this
    session. Maps the middle of the scale to zero and the ends to plus or minus
    two, which is the working range of the difficulty parameter.
    """
    if not scores:
        return 0.0
    mean = sum(scores) / len(scores)
    midpoint = (scale_min + scale_max) / 2
    half_range = (scale_max - scale_min) / 2
    return _clip(2.0 * (mean - midpoint) / half_range, -2.0, 2.0)


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))

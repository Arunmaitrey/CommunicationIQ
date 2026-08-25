"""Layer 4: mastery tracking, item calibration, adaptive selection.

The tests that matter most here are the ones about *refusing* to calibrate.
Anyone can fit two parameters to eleven responses; the question is whether the
system then presents the result as knowledge.
"""
from __future__ import annotations

import math
import random

import pytest

from app.engine.psychometrics import bkt, irt


# ==========================================================================
# Bayesian Knowledge Tracing
# ==========================================================================

def test_a_correct_answer_raises_the_belief_and_a_wrong_one_lowers_it():
    prior = 0.5
    assert bkt.update(prior, True) > prior
    assert bkt.update(prior, False) < prior


def test_one_slip_barely_moves_an_established_belief():
    """The reason BKT replaced a running mean. Four demonstrations then one
    miss is a slip, not a fifth of the skill disappearing."""
    mastery = 0.3
    for _ in range(4):
        mastery = bkt.update(mastery, True, "fluency")
    established = mastery

    after_slip = bkt.update(established, False, "fluency")
    assert after_slip > established - 0.35, "a single slip should not gut the estimate"
    assert after_slip < established

    # A running mean over the same five observations lands far lower.
    mean = sum([1, 1, 1, 1, 0]) / 5
    assert after_slip > mean


def test_a_lucky_guess_is_worth_less_than_a_demonstration():
    """On a skill with a high guess rate, a correct answer is weaker evidence."""
    lucky = bkt.update(0.3, True, "listening")      # guess 0.25
    earned = bkt.update(0.3, True, "response_latency")  # guess 0.05
    assert earned > lucky


def test_belief_never_reaches_certainty():
    """A probability of exactly 1 cannot be updated by any later evidence — a
    student would be frozen at their best day forever."""
    mastery = 0.5
    for _ in range(200):
        mastery = bkt.update(mastery, True)
    assert mastery < 1.0

    for _ in range(200):
        mastery = bkt.update(mastery, False)
    assert mastery > 0.0


def test_practice_itself_counts_a_little():
    """The learning step applies after the evidence: you learn from the ones
    you get wrong, and the model says so."""
    params = bkt.Parameters(p_transit=0.2, p_guess=0.1, p_slip=0.1)
    after_evidence = bkt.posterior(0.4, False, params)
    after_learning = bkt.update(0.4, False)
    assert after_learning > after_evidence - 1.0
    assert bkt.update(0.4, False) > bkt.posterior(0.4, False, bkt.DEFAULT)


def test_the_predicted_next_result_is_not_the_mastery_number():
    """Quoting mastery as the chance of success ignores slip and guess — a
    small lie in the direction of flattery."""
    assert bkt.probability_correct(0.9) < 0.9
    assert bkt.probability_correct(0.0) > 0.0


def test_scores_are_binarised_at_the_platforms_own_readiness_line():
    from app.readiness import READY_AT
    assert bkt.DEMONSTRATED_AT == READY_AT

    assert bkt.update_from_score(0.5, 75.0) > 0.5
    assert bkt.update_from_score(0.5, 40.0) < 0.5


def test_confidence_grows_slowly():
    assert bkt.confidence_after(1) < 0.25
    assert bkt.confidence_after(5) < 0.65
    assert bkt.confidence_after(50) <= 0.9


def test_degenerate_parameters_are_refused():
    with pytest.raises(ValueError):
        bkt.Parameters(p_guess=0.6, p_slip=0.5).validated()
    with pytest.raises(ValueError):
        bkt.Parameters(p_init=1.5).validated()


# ==========================================================================
# IRT calibration
# ==========================================================================

def simulate(n_students: int = 200, n_filler: int = 0,
             seed: int = 7) -> tuple[list, dict, dict]:
    """Responses generated from known item parameters.

    Recovering parameters you planted is the only way to test an estimator
    without a labelled dataset — if it cannot find them here it will not find
    anything real.

    ``n_filler`` pads the test out with extra items. Test *length* is what
    governs how well the estimator does: ability noise propagates into the
    item parameters, so a six-item bank and a thirty-item bank are different
    problems even with the same number of students.
    """
    rng = random.Random(seed)
    truth = {
        "easy": (-1.2, 1.0),
        "medium": (0.0, 1.4),
        "hard": (1.3, 1.1),
        "sharp": (0.2, 2.0),
        "flat": (-0.3, 0.5),
        "extra": (0.7, 1.2),
    }
    for k in range(n_filler):
        truth[f"filler{k}"] = (rng.gauss(0, 1.1), rng.uniform(0.7, 1.6))

    abilities = {f"s{i}": rng.gauss(0, 1) for i in range(n_students)}

    responses = []
    for student, theta in abilities.items():
        for item, (b, a) in truth.items():
            p = irt.probability(theta, b, a)
            responses.append((student, item, rng.random() < p))
    return responses, truth, abilities


def test_calibration_recovers_planted_difficulty_ordering():
    responses, truth, _ = simulate(n_filler=14)
    result = irt.calibrate(responses)

    assert result.calibrated_count == len(truth)
    recovered = {i: p.difficulty for i, p in result.items.items()}
    assert recovered["easy"] < recovered["medium"] < recovered["hard"]


def test_calibration_recovers_difficulty_closely():
    """Measured on planted parameters: mean absolute error around 0.2 logits
    on a twenty-item test. Asserted at 0.6 so the test catches a broken
    estimator rather than ordinary sampling noise."""
    responses, truth, _ = simulate(n_students=300, n_filler=14, seed=11)
    result = irt.calibrate(responses)
    errors = [abs(result.items[i].difficulty - b) for i, (b, _a) in truth.items()]
    assert max(errors) < 0.9
    assert sum(errors) / len(errors) < 0.35


def test_a_short_test_falls_back_to_rasch_rather_than_guessing_a_slope():
    """Discrimination needs test length the six-item bank does not have.
    Reporting a slope we cannot estimate would put a number in the item bank
    that adaptive selection then trusts."""
    responses, truth, _ = simulate(n_students=300, seed=13)
    result = irt.calibrate(responses)

    assert result.model == "Rasch"
    assert {result.items[i].discrimination for i in truth} == {irt.RASCH_DISCRIMINATION}
    # Difficulty is still estimated, and still useful.
    assert result.items["easy"].difficulty < result.items["hard"].difficulty


def test_a_long_enough_test_estimates_discrimination_and_ranks_it_correctly():
    responses, _truth, _ = simulate(n_students=300, n_filler=26, seed=13)
    result = irt.calibrate(responses)

    assert result.model == "2PL"
    assert (result.items["sharp"].discrimination
            > result.items["flat"].discrimination)


def test_recovered_abilities_correlate_with_the_real_ones():
    """r above 0.9 on a twenty-item test. Shorter tests are noisier by
    construction, which is why the estimator drops to Rasch there."""
    responses, _truth, abilities = simulate(n_students=300, n_filler=14, seed=17)
    result = irt.calibrate(responses)

    pairs = [(abilities[s], t) for s, t in result.abilities.items()]
    n = len(pairs)
    mean_x = sum(x for x, _ in pairs) / n
    mean_y = sum(y for _, y in pairs) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    sx = math.sqrt(sum((x - mean_x) ** 2 for x, _ in pairs))
    sy = math.sqrt(sum((y - mean_y) ** 2 for _, y in pairs))
    assert cov / (sx * sy) > 0.85


def test_calibration_converges_rather_than_running_to_the_cap():
    """It used to hit sixty iterations every time and stop wherever it was."""
    responses, _truth, _ = simulate(n_students=300, n_filler=14, seed=19)
    result = irt.calibrate(responses)
    assert result.converged
    assert result.iterations < irt.MAX_ITERATIONS


# -- the gate --------------------------------------------------------------

def test_too_few_responses_is_refused_with_a_reason():
    """Eleven responses can be fitted. They should not be."""
    rng = random.Random(3)
    responses = [(f"s{i}", "thin", rng.random() < 0.5) for i in range(11)]
    result = irt.calibrate(responses)

    params = result.items["thin"]
    assert params.calibrated is False
    assert "responses" in params.reason


def test_an_item_everyone_got_right_cannot_be_placed():
    responses = [(f"s{i}", "trivial", True) for i in range(80)]
    responses += [(f"s{i}", "other", i % 2 == 0) for i in range(80)]
    result = irt.calibrate(responses)

    assert result.items["trivial"].calibrated is False
    assert "same" in result.items["trivial"].reason


def test_parameters_stay_inside_sane_bounds():
    responses, _truth, _ = simulate(n_students=200, n_filler=26, seed=23)
    result = irt.calibrate(responses)
    for params in result.items.values():
        if not params.calibrated:
            continue
        assert irt.MIN_DISCRIMINATION <= params.discrimination <= irt.MAX_DISCRIMINATION
        assert abs(params.difficulty) <= irt.MAX_ABS_DIFFICULTY


def test_no_responses_at_all_is_not_a_crash():
    result = irt.calibrate([])
    assert result.items == {}
    assert result.calibrated_count == 0


# ==========================================================================
# Adaptive selection
# ==========================================================================

def calibrated(item_id: str, difficulty: float, discrimination: float = 1.0):
    return irt.ItemParameters(item_id=item_id, difficulty=difficulty,
                              discrimination=discrimination, calibrated=True)


def test_information_peaks_where_the_item_matches_the_student():
    at_level = irt.information(0.0, 0.0, 1.2)
    too_easy = irt.information(0.0, -2.5, 1.2)
    too_hard = irt.information(0.0, 2.5, 1.2)
    assert at_level > too_easy and at_level > too_hard


def test_selection_picks_the_item_at_the_edge_of_the_ability():
    pool = [calibrated("easy", -2.0), calibrated("right", 0.5),
            calibrated("hard", 2.5)]
    assert irt.select_next(0.5, pool).item_id == "right"
    assert irt.select_next(-2.0, pool).item_id == "easy"
    assert irt.select_next(2.5, pool).item_id == "hard"


def test_selection_does_not_repeat_an_item():
    pool = [calibrated("a", 0.0), calibrated("b", 0.1)]
    first = irt.select_next(0.0, pool)
    second = irt.select_next(0.0, pool, exclude={first.item_id})
    assert second.item_id != first.item_id


def test_an_uncalibrated_item_is_never_chosen_adaptively():
    """Choosing among authored guesses and calling it adaptive would be the
    claim this module exists to avoid making."""
    guesses = [irt.ItemParameters(item_id="guess", difficulty=0.0,
                                  discrimination=1.0, calibrated=False)]
    assert irt.select_next(0.0, guesses) is None


def test_ability_from_scores_maps_the_scale_sensibly():
    assert irt.ability_from_scores([]) == 0.0
    assert irt.ability_from_scores([50.0]) == 0.0
    assert irt.ability_from_scores([80.0]) > 1.5
    assert irt.ability_from_scores([20.0]) < -1.5

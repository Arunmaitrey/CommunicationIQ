"""Bayesian Knowledge Tracing (ENG-13).

Replaces the running mean the gap meter used to read. Both answer "how likely
is it that this student has this sub-skill", but BKT answers it with a model
that separates two things a mean cannot: getting it right by luck, and getting
it wrong despite knowing it.

That distinction is what stops the meter lurching. A student who has shown a
skill four times and slips once has slipped; a mean treats it as a fifth of
their ability disappearing. BKT's slip parameter absorbs it, and the posterior
barely moves — which is the honest reading, and also the one that does not
punish somebody for a bad morning.

Four parameters per skill, in the classic formulation:

* **P(L0)** — probability they already had it before we saw anything
* **P(T)**  — probability of acquiring it between opportunities
* **P(G)**  — probability of getting it right without having it (guess)
* **P(S)**  — probability of getting it wrong while having it (slip)

The defaults below are literature-typical starting values, not fitted ones.
Fitting them per skill needs far more response data than exists, and inventing
fitted-looking numbers would be worse than admitting they are priors.
"""
from __future__ import annotations

from dataclasses import dataclass

# Speech dimensions come back on the 20-80 presentation scale, not as right or
# wrong. BKT needs a binary observation, so a response counts as demonstrating
# the skill at or above the platform's own "placement ready" line — the same
# threshold the readiness bands use, so a student is never "ready" on one
# screen and "not demonstrating it" on another.
DEMONSTRATED_AT = 60.0


@dataclass(frozen=True)
class Parameters:
    """One skill's BKT parameters."""

    p_init: float = 0.25
    p_transit: float = 0.10
    p_guess: float = 0.20
    p_slip: float = 0.10

    def validated(self) -> "Parameters":
        # Guess + slip above 1 makes the model degenerate: an observation would
        # be evidence against the thing it is evidence for.
        if self.p_guess + self.p_slip >= 1.0:
            raise ValueError("p_guess + p_slip must be below 1.0")
        for name, value in (("p_init", self.p_init), ("p_transit", self.p_transit),
                            ("p_guess", self.p_guess), ("p_slip", self.p_slip)):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")
        return self


# Per-skill overrides where the task genuinely differs. Response speed has
# almost no guess component — you cannot accidentally start talking quickly —
# while listening accuracy on a four-option-shaped task has more room for luck.
BY_SKILL: dict[str, Parameters] = {
    "response_latency": Parameters(p_init=0.30, p_transit=0.15, p_guess=0.05,
                                   p_slip=0.15),
    "listening": Parameters(p_init=0.25, p_transit=0.10, p_guess=0.25, p_slip=0.10),
    "grammar": Parameters(p_init=0.20, p_transit=0.08, p_guess=0.20, p_slip=0.12),
}

DEFAULT = Parameters()


def parameters_for(skill: str) -> Parameters:
    return BY_SKILL.get(skill, DEFAULT).validated()


def posterior(prior: float, demonstrated: bool, params: Parameters) -> float:
    """P(knows the skill | this observation), before the learning step."""
    if demonstrated:
        numerator = prior * (1.0 - params.p_slip)
        denominator = numerator + (1.0 - prior) * params.p_guess
    else:
        numerator = prior * params.p_slip
        denominator = numerator + (1.0 - prior) * (1.0 - params.p_guess)

    if denominator <= 0.0:
        return prior
    return numerator / denominator


def update(prior: float, demonstrated: bool, skill: str = "") -> float:
    """One observation in, one new belief out.

    The learning step is applied after the evidence: practising is itself an
    opportunity to acquire the skill, so even a wrong answer nudges the
    posterior up a little. That is the model saying what teaching says — you
    learn from the ones you get wrong.
    """
    params = parameters_for(skill)
    after = posterior(_clamp(prior), demonstrated, params)
    return _clamp(after + (1.0 - after) * params.p_transit)


def update_from_score(prior: float, score: float, skill: str = "",
                      scale_min: float = 20.0, scale_max: float = 80.0) -> float:
    """Convenience for the pipeline, which works in presentation scores."""
    del scale_min, scale_max
    return update(prior, score >= DEMONSTRATED_AT, skill)


def probability_correct(mastery: float, skill: str = "") -> float:
    """What the model expects next time — used to explain a prediction.

    Not the mastery number itself: a student with 0.8 mastery still has a slip
    probability, and quoting 80% when the model expects 74% would be a small
    lie in the direction of flattery.
    """
    params = parameters_for(skill)
    known = _clamp(mastery)
    return known * (1.0 - params.p_slip) + (1.0 - known) * params.p_guess


def confidence_after(observations: int) -> float:
    """How much to trust the estimate, given how much was seen.

    Deliberately slow to reach certainty. Five observations is a hint, not a
    diagnosis, and the readiness report leans on this.
    """
    return round(min(0.9, 1.0 - 0.85 ** max(0, observations)), 2)


def _clamp(value: float) -> float:
    # Never exactly 0 or 1: a certain belief cannot be updated by any evidence,
    # and a student would be stuck at their first result forever.
    return max(0.01, min(0.99, value))

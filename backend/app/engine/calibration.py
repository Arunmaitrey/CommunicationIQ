"""Whether a score means anything yet.

Every number this engine produces is a rescaled heuristic until somebody has
checked it against human judgement. That is not a defect — it is the state of
any assessment engine before its validation study — but presenting an
uncalibrated number on a 20-80 scale that looks like a vendor band is how a
placement officer ends up quoting it to a recruiter.

So the state lives here, in one place, and travels with every score:

* **uncalibrated** — the default. Scores are internally consistent and
  externally meaningless. The product shows them as practice feedback and
  refuses to present a composite as an assessment result.
* **calibrated** — a linear map fitted against human ratings, with the study
  that produced it recorded. Only then does a composite get shown as a score.

Moving between the two is not a config flag somebody can flip because a demo
is coming. It requires a fitted mapping, which requires the ratings.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

# The gates from the validation plan. A study that misses any of them does not
# produce a calibration, however much data it collected.
MIN_RATER_AGREEMENT = 0.70      # ICC across human raters
MIN_CORRELATION = 0.60          # AI versus human, per dimension
MIN_OVERALL_CORRELATION = 0.65
MAX_MEAN_ABSOLUTE_ERROR = 8.0   # points on the 20-80 scale
MAX_L1_GROUP_BIAS = 3.0         # mean residual spread across L1 groups

# Below this many measured dimensions, a composite is an average of too little
# to carry the word "overall".
MIN_DIMENSIONS_FOR_OVERALL = 3


@dataclass(frozen=True)
class Calibration:
    """A fitted mapping from engine score to human-anchored score."""

    dimension: str
    slope: float = 1.0
    intercept: float = 0.0
    correlation: float = 0.0
    mean_absolute_error: float = 0.0
    n_recordings: int = 0
    n_raters: int = 0
    rater_agreement: float = 0.0
    l1_group_bias: float = 0.0
    fitted_at: datetime | None = None
    study: str = ""

    @property
    def usable(self) -> bool:
        return (self.rater_agreement >= MIN_RATER_AGREEMENT
                and self.correlation >= MIN_CORRELATION
                and self.mean_absolute_error <= MAX_MEAN_ABSOLUTE_ERROR
                and self.l1_group_bias <= MAX_L1_GROUP_BIAS)

    def apply(self, raw: float) -> float:
        return self.slope * raw + self.intercept


@dataclass
class State:
    """What is known about this engine's scores, right now."""

    dimensions: dict[str, Calibration] = field(default_factory=dict)

    def is_calibrated(self, dimension: str) -> bool:
        fit = self.dimensions.get(dimension)
        return bool(fit and fit.usable)

    @property
    def any_calibrated(self) -> bool:
        return any(self.is_calibrated(d) for d in self.dimensions)

    def note_for(self, dimension: str) -> str:
        if self.is_calibrated(dimension):
            fit = self.dimensions[dimension]
            return (f"Calibrated against {fit.n_raters} human raters on "
                    f"{fit.n_recordings} recordings (r={fit.correlation:.2f}).")
        return UNCALIBRATED_NOTE


UNCALIBRATED_NOTE = (
    "Not yet checked against human listeners. Useful for tracking your own "
    "progress; not a score to quote to anyone."
)

OVERALL_UNCALIBRATED_NOTE = (
    "This combines several measures using weights that have not been validated "
    "against human judgement. Treat the individual measures as the useful part."
)

# Nothing is calibrated. This is the honest starting state and it stays that
# way until app.validate produces a fit that clears the gates above.
STATE = State()


def current() -> State:
    return STATE


def install(fits: dict[str, Calibration]) -> None:
    """Called by the validation tooling once a study has produced a fit."""
    STATE.dimensions.update({d: f for d, f in fits.items() if f.usable})


def reset() -> None:
    STATE.dimensions.clear()

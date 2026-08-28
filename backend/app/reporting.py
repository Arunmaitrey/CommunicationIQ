"""What the report says, beyond the numbers.

Everything here is a rearrangement of measurements the pipeline already
produced. Nothing computes a score, and nothing may: ``biggest_lever`` lives
inside ``SCORING_PATH`` and stays exactly as it is, so this module sits above
the freeze the same way ``weighting`` and ``evaluation`` do.

Four things the audit asked for and the report did not have:

**Strengths, not only weaknesses.** The result gave one "biggest lever" and
nothing else — a screen that tells a nineteen-year-old the single worst thing
about how they speak, every time, with no counterweight. Somebody who reads
that after each attempt learns that practising produces criticism. What they
are good at is measured just as precisely and was simply never shown.

**Recommendations as a set.** One lever is one instruction. Two or three,
ordered by how much each would actually move the number, is a plan — and the
gains are computed the same honest way the single lever's was: what the
overall *would be* if this dimension matched the student's own best, not a
figure chosen because it reads well.

**Evidence per dimension.** The data has been stored since M2 —
transcripts, word timings, grammar errors, pauses. "Your grammar was 54" is
an assertion; "your grammar was 54, and here are the four sentences it was
counted from" is something a student can argue with, which is the point.

**A plain summary at the top.** The Phase 0 rule. A student opening their
result should meet a sentence in their own language before a chart.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Mirrored from the frozen pipeline rather than imported, the same arrangement
# `weighting.ENGINE_WEIGHTS` uses: this module must keep working if the frozen
# set is re-cut, and a test asserts the two agree.
WEIGHTS: dict[str, float] = {
    "pronunciation": 0.20, "accuracy": 0.20, "fluency": 0.17,
    "latency": 0.11, "disfluency": 0.08, "grammar": 0.09, "content": 0.07,
    "completeness": 0.08,
}

# How far above your own average a dimension has to sit before calling it a
# strength. Below this it is noise, and a "strength" that is really rounding
# teaches a student to distrust the whole report.
STRENGTH_MARGIN = 3.0

# How far below before it is worth a recommendation. Deliberately smaller --
# the cost of mentioning something not worth fixing is a wasted paragraph, and
# the cost of missing something is a student who never fixes it.
LEVER_MARGIN = 2.0

# At most this many recommendations. A list of seven is not a plan; it is the
# same information as the chart, retyped.
MAX_LEVERS = 3

# What a student is actually told to do about each dimension. Written for
# them, not for us -- and specific enough to act on this week.
ADVICE: dict[str, str] = {
    "pronunciation": (
        "Record yourself reading a short paragraph, then listen back for the "
        "words that came out unclear. Say those words alone, slowly, ten "
        "times each."),
    "accuracy": (
        "Practise Repeat Sentence with your eyes closed. Most of what is lost "
        "here is lost while holding the sentence, not while saying it."),
    "fluency": (
        "Talk for sixty seconds on an easy topic without stopping. Do not "
        "correct yourself mid-sentence -- finish the wrong sentence and start "
        "the next one."),
    "latency": (
        "Answer the moment the tone ends, even with 'Well,' or 'So,'. The "
        "gap before you start costs more than a slightly clumsy opening."),
    "disfluency": (
        "Notice your own filler word -- most people have exactly one -- and "
        "replace it with a closed mouth. A pause sounds far better than "
        "'um'."),
    "grammar": (
        "Pick one pattern you get wrong and drill only that for a week. "
        "Fixing one thing properly beats noticing five."),
    "content": (
        "Before answering, decide the two things you will say. Most content "
        "marks are lost by wandering, not by not knowing."),
    "comprehension": (
        "Listen to one short workplace clip a day and write one sentence "
        "about what was decided, not what was said."),
    "vocabulary": (
        "When you meet a word you half-know, write the whole sentence it was "
        "in. Words are not learned alone."),
    "completeness": (
        "Answer the whole question before you polish any of it. A short "
        "complete answer scores better here than half a good one."),
    "appropriacy": (
        "Read replies aloud before sending them. Most of what lands badly is "
        "grammatically perfect."),
}

def _advice_for(dimension: str) -> str:
    """The advice for a dimension, or an honest admission that there is none.

    ``ADVICE.get(dimension, "")`` is what this used to be, and it is the shape
    of bug this codebase keeps producing: a new dimension arrives, nobody
    writes advice for it, and the student is shown a recommendation card with
    a heading, a predicted gain and a blank space where the actionable part
    should be. A test below makes that unreachable; this makes it visible
    rather than blank if it ever becomes reachable anyway.
    """
    written = ADVICE.get(dimension, "").strip()
    if written:
        return written
    return ("We have not written practice advice for this one yet. Your "
            "admin can suggest something specific.")


# Said in the student's own words. Ordered from lowest to highest.
BANDS: tuple[tuple[float, str], ...] = (
    (0.0, "a long way from ready"),
    (35.0, "some way off"),
    (50.0, "close, with work to do"),
    (65.0, "about where a placement round expects you to be"),
    (75.0, "comfortably above what most rounds ask for"),
)


# Why a recording stopped, as the client that stopped it reported. The
# report may claim a candidate "ran out of time" ONLY for "window_expired":
# the acoustic ended-mid-speech signal cannot tell a timeout from somebody
# who pressed Stop while still talking, and telling a candidate they timed
# out on an answer they deliberately ended is a report contradicting their
# own behaviour. Unknown ("" — legacy rows, older clients) is never a
# timeout either: a claim about behaviour needs evidence, not a default.
END_REASONS = ("user_ended", "auto_advance", "window_expired", "cancelled")


def ran_out_of_time(ended_mid_speech: bool, ended_by: str) -> bool:
    """Whether one answer may honestly be described as cut off by the clock."""
    return bool(ended_mid_speech) and ended_by == "window_expired"


def band_phrase(overall: float) -> str:
    label = BANDS[0][1]
    for lower, phrase in BANDS:
        if overall >= lower:
            label = phrase
    return label


@dataclass
class Highlight:
    """One thing worth saying about a dimension, good or bad."""

    dimension: str
    score: float
    # How far from this student's own average. Signed.
    delta: float
    # What it means, for them.
    means: str


@dataclass
class Recommendation:
    dimension: str
    current: float
    target: float
    # What the overall would become if this matched their own best. Computed,
    # never chosen for effect.
    predicted_gain: float
    advice: str


@dataclass
class Report:
    summary: str
    strengths: list[Highlight] = field(default_factory=list)
    weaknesses: list[Highlight] = field(default_factory=list)
    recommendations: list[Recommendation] = field(default_factory=list)


def _weighted_mean(dimensions: dict[str, float]) -> float | None:
    usable = {d: v for d, v in dimensions.items() if d in WEIGHTS}
    if not usable:
        return None
    total = sum(WEIGHTS[d] for d in usable)
    return sum(v * WEIGHTS[d] for d, v in usable.items()) / total if total else None


def highlights(dimensions: dict[str, float],
               notes: dict[str, str] | None = None
               ) -> tuple[list[Highlight], list[Highlight]]:
    """What stood out, in both directions.

    Measured against the student's own average rather than a cohort or a fixed
    threshold. "Your pronunciation is ahead of your grammar" is a fact about
    one person and needs no calibration to state; "your pronunciation is good"
    is a claim about a population, and this product does not have one yet.
    """
    if len(dimensions) < 2:
        return [], []

    notes = notes or {}
    mean = sum(dimensions.values()) / len(dimensions)

    strengths: list[Highlight] = []
    weaknesses: list[Highlight] = []
    for dimension, score in dimensions.items():
        delta = round(score - mean, 1)
        entry = Highlight(dimension=dimension, score=round(score, 1),
                          delta=delta, means=notes.get(dimension, ""))
        if delta >= STRENGTH_MARGIN:
            strengths.append(entry)
        elif -delta >= LEVER_MARGIN:
            weaknesses.append(entry)

    strengths.sort(key=lambda h: h.delta, reverse=True)
    weaknesses.sort(key=lambda h: h.delta)
    return strengths, weaknesses


def recommendations(dimensions: dict[str, float]) -> list[Recommendation]:
    """The changes that would move the number most, in order.

    SUPPORTING DETAIL, NOT THE DIAGNOSIS. This ranks by weighted gain, which
    is a fact about the composite's weights as much as about the student;
    the answer to "what should I work on first" is app/diagnosis.py, and
    nothing on the result page presents this order as that answer.

    Same arithmetic as the frozen ``biggest_lever``, applied to more than one
    dimension: for each candidate, what the weighted overall would become if
    that dimension matched this student's own best. Nothing is recommended
    whose predicted gain rounds to nothing -- a suggestion that changes
    nothing is worse than silence, because it costs a week of somebody's
    practice.
    """
    usable = {d: v for d, v in dimensions.items() if d in WEIGHTS}
    if len(usable) < 2:
        return []

    before = _weighted_mean(usable)
    if before is None:
        return []
    best = max(usable.values())

    out: list[Recommendation] = []
    for dimension, score in usable.items():
        if best - score < LEVER_MARGIN:
            continue
        after = _weighted_mean({**usable, dimension: best})
        gain = round((after or before) - before, 1)
        if gain < 0.5:
            continue
        out.append(Recommendation(
            dimension=dimension, current=round(score, 1), target=round(best, 1),
            predicted_gain=gain, advice=_advice_for(dimension)))

    out.sort(key=lambda r: r.predicted_gain, reverse=True)
    return out[:MAX_LEVERS]


def summary(overall: float | None, dimensions: dict[str, float],
            skills: dict[str, float | None] | None = None,
            unscored: dict[str, str] | None = None,
            has_audio: bool = True, primary=None) -> str:
    """The first thing a student reads. Plain language, no jargon, no chart.

    Says what happened, where they are, and what to do -- in that order,
    because that is the order somebody wants it in. It never invents
    confidence: an attempt with no overall says so plainly rather than leading
    with a number that was withheld for good reason.

    "What to do" is the attempt's PrimaryDiagnosis (app/diagnosis.py), passed
    in as ``primary``. This sentence used to pick the dimension with the
    largest weighted gain -- a different rule from the result card's, which
    is how one page came to name Pronunciation here and Content below. It
    no longer chooses; it says what the diagnosis said.
    """
    unscored = unscored or {}

    # An assessment can now be entirely reading and writing, and telling
    # somebody their recordings are safe when they never made one reads as a
    # report about a different person's attempt. The reassurance is real and
    # worth keeping -- it just has to be true.
    kept = (" and your recordings are kept" if has_audio
            else " and your answers are kept")

    if overall is None:
        if unscored:
            return ("This attempt could not be given an overall score. "
                    + _why_not(unscored)
                    + " What was measured is below," + kept + ".")
        return ("There was not enough here to score. Nothing has been guessed "
                "at," + kept + ".")

    parts = [f"You scored {round(overall, 1)} out of 80, which is "
             f"{band_phrase(overall)}."]

    scored_skills = {s: v for s, v in (skills or {}).items() if v is not None}
    if len(scored_skills) >= 2:
        best = max(scored_skills, key=lambda s: scored_skills[s])
        worst = min(scored_skills, key=lambda s: scored_skills[s])
        if best != worst and scored_skills[best] - scored_skills[worst] >= 3:
            parts.append(f"Your {best} is ahead of your {worst}.")

    parts.extend(_what_to_do(primary, dimensions))

    if unscored:
        parts.append(_why_not(unscored))

    return " ".join(parts)


def _what_to_do(primary, dimensions: dict[str, float]) -> list[str]:
    """The summary's action sentence, from the diagnosis and nothing else."""
    status = getattr(primary, "status", "")
    if status == "identified":
        return [f"The one thing worth working on first is "
                f"{_say(primary.dimension)} -- your lowest measured area "
                f"across {primary.responses} answers."]
    if status == "tied":
        names = [_say(c.dimension) for c in primary.candidates]
        return [f"Nothing clearly stands out yet: {', '.join(names[:-1])} and "
                f"{names[-1]} were measured at about the same level, so we "
                "will not pick one for you until there is a little more "
                "evidence."]
    if status == "level":
        return ["Nothing clearly stands out yet: your measures are all at a "
                "similar level, so there is no single weak spot to attack -- "
                "steady practice across the board is the right next step."]
    if status in ("insufficient", "none") and dimensions:
        return ["There is not enough evidence yet to identify one clear "
                "weakness -- another attempt will make the picture clearer."]
    return []


def _why_not(unscored: dict[str, str]) -> str:
    names = ", ".join(_say(d) for d in sorted(unscored))
    return (f"{names[0].upper()}{names[1:]} could not be measured on this "
            f"server, so {'they are' if len(unscored) > 1 else 'it is'} left "
            f"out rather than guessed at.")


def _say(dimension: str) -> str:
    """A dimension name as a person would say it."""
    return {
        "pronunciation": "how clearly you pronounce words",
        "accuracy": "saying back what you heard",
        "fluency": "keeping going without stalling",
        "latency": "starting to speak quickly",
        "disfluency": "cutting out the ums",
        "grammar": "grammar",
        "content": "covering what the question asked",
        "comprehension": "understanding what you read or heard",
        "vocabulary": "vocabulary",
        "appropriacy": "choosing what to say",
    }.get(dimension, dimension.replace("_", " "))


def build(overall: float | None, dimensions: dict[str, float],
          skills: dict[str, float | None] | None = None,
          notes: dict[str, str] | None = None,
          unscored: dict[str, str] | None = None,
          has_audio: bool = True, primary=None) -> Report:
    """Everything above, assembled once."""
    strong, weak = highlights(dimensions, notes)
    return Report(
        summary=summary(overall, dimensions, skills, unscored, has_audio,
                        primary),
        strengths=strong, weaknesses=weak,
        recommendations=recommendations(dimensions),
    )


# --------------------------------------------------------------------------
# Evidence
# --------------------------------------------------------------------------
#
# Which stored measurements stand behind each dimension.
#
# All of this has been persisted since M2 and none of it was ever shown next
# to the number it produced. "Your grammar was 54" is an assertion; "your
# grammar was 54, counted from these four sentences" is something a student
# can disagree with -- and a student who can disagree with a score is being
# treated as a person rather than a subject.
#
# Declared as a map rather than inferred, for the reason every other map in
# this codebase is: a dimension added later must be classified deliberately,
# and an unclassified one showing no evidence is a silent gap.
EVIDENCE_FOR: dict[str, tuple[str, ...]] = {
    # What arrived against what was asked for, and whether the clock cut them
    # off -- which is the difference between "did not finish" and "chose to
    # stop", and only one of those is worth practising.
    "completeness": ("completeness", "ended_mid_speech", "speech_ms"),
    # Clarity for pronunciation, the reference comparison for accuracy. These
    # both used to say `word_errors`, which was serving clarity scores -- so
    # the accuracy panel showed evidence of a different measurement.
    "pronunciation": ("word_clarity",),
    "accuracy": ("word_errors", "transcript"),
    "fluency": ("words_per_minute", "articulation_rate", "pauses"),
    "latency": ("onset_ms",),
    "disfluency": ("disfluencies",),
    "grammar": ("grammar_errors", "transcript"),
    "content": ("transcript",),
    # Router-marked dimensions. Their evidence is the answer itself, which the
    # response detail already carries.
    "comprehension": ("transcript",),
    "vocabulary": ("transcript",),
    "appropriacy": ("transcript",),
}


def evidence_index(responses: list[dict]) -> dict[str, list[dict]]:
    """Dimension -> the responses that produced it, with what they produced.

    Built from the response detail the result already returns, so nothing new
    is stored and nothing is recomputed. A dimension nothing produced is
    absent rather than present-and-empty: an empty evidence panel reads as a
    system that lost the evidence, which is worse than one that says the
    measure was not taken.
    """
    out: dict[str, list[dict]] = {}
    for response in responses:
        scores = response.get("scores") or {}
        for dimension, score in scores.items():
            wanted = EVIDENCE_FOR.get(dimension, ())
            entry = {
                "response_id": response.get("response_id", ""),
                "position": response.get("position", 0),
                "task_type": response.get("task_type", ""),
                "score": round(float(score), 1),
            }
            for key in wanted:
                value = response.get(key)
                # Zero is a measurement; empty is an absence. `0 pauses` is
                # worth showing and `[]` is not.
                if value not in (None, "", [], {}):
                    entry[key] = value
            out.setdefault(dimension, []).append(entry)

    for rows in out.values():
        rows.sort(key=lambda r: r["position"])
    return out


# -- CEFR, as an indication rather than a result ---------------------------
#
# A CEFR level is a claim, and the honest position is that no concordance
# study has been run against the framework's own descriptors. What follows is
# the same treatment the vendor-format presentation already gets: shown, named
# for what it is, and never allowed to stand in for the number we can defend.
#
# The boundaries come from where the internal 20-80 scale was built to sit
# against placement expectations, not from a mapping study. B1 begins at the
# point the report already calls "close, with work to do", and B2 at the point
# it calls "about where a placement round expects you to be", because those
# are the two judgements this scale was designed to make. Aligning the CEFR
# cut points with the bands the product already publishes means the two can
# never contradict each other on screen, which a separately-invented set of
# thresholds eventually would.
CEFR_BANDS: tuple[tuple[float, str, str], ...] = (
    (0.0, "A1", "Can handle a few familiar phrases with heavy support."),
    (35.0, "A2", "Can manage short, routine exchanges on familiar topics."),
    (50.0, "B1", "Can hold a conversation on familiar matters and explain a "
                 "point of view, with effort."),
    (65.0, "B2", "Can interact with some fluency and argue a position in "
                 "detail on familiar subjects."),
    (75.0, "C1", "Can use the language flexibly for professional purposes "
                 "with little obvious searching."),
)

CEFR_CAVEAT = (
    "An indication, not a CEFR result. No study has been run comparing this "
    "assessment to the framework's own rating scale, so this places you on "
    "the ladder rather than certifying a level. Nobody should accept it in "
    "place of a CEFR certificate, and we do not offer it as one."
)


@dataclass
class CefrIndication:
    level: str
    descriptor: str
    caveat: str


def cefr(overall: float | None) -> CefrIndication | None:
    """The band an overall score indicates, or None where there is no score.

    None rather than A1. An attempt that could not be scored has not
    demonstrated the lowest level -- it has demonstrated nothing -- and a
    report that prints A1 for an engine failure is making an accusation.
    """
    if overall is None:
        return None
    level, descriptor = CEFR_BANDS[0][1], CEFR_BANDS[0][2]
    for lower, name, text in CEFR_BANDS:
        if overall >= lower:
            level, descriptor = name, text
    return CefrIndication(level=level, descriptor=descriptor,
                          caveat=CEFR_CAVEAT)

"""Story Retell reported as two axes, because it measures two things.

A retell asks a candidate to hold something they heard once and say it back
in their own words. Two quite different failures look identical in a single
number:

* they remembered the story and told it badly;
* they spoke beautifully and remembered almost none of it.

The first is a language problem. The second is a listening and working-memory
problem. They need different practice, and a trainer looking at one merged
score cannot tell which they are looking at — so the merged score is worse
than useless, it is misleading.

The engine already measures both. ``content`` is rubric key-point coverage;
``fluency``, ``grammar``, ``disfluency``, ``latency`` and ``pronunciation``
are the language side. Nothing new is computed here and no scoring decision
is made — this module only refuses to average across the boundary.

**What is honestly missing.** The brief asks Content to break down into key
facts, sequence, main idea and completeness. Only coverage of the author's
key points exists today; sequence in particular needs the rubric to carry
*ordered* points and the scorer to check order, which is real work and is not
pretended at here. ``content_parts`` says which of the four are measured.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# What each axis is made of. Kept explicit rather than "everything that is not
# content", so adding a dimension to the engine cannot silently land on the
# language side of a retell.
LANGUAGE_DIMENSIONS = ("fluency", "grammar", "disfluency", "latency",
                       "pronunciation")
CONTENT_DIMENSIONS = ("content",)

# The four the brief asks for, and whether each is really measured. Reported
# so the gap is visible in the product rather than only in a document.
CONTENT_PARTS: dict[str, bool] = {
    "key facts": True,        # rubric key-point coverage
    "main idea": True,        # the rubric's primary point
    "completeness": True,     # share of points covered
    "sequence": False,        # needs ordered rubric points; not built
}


@dataclass
class Axis:
    label: str
    score: float | None
    # Which measured dimensions went into it, so the number can be traced.
    from_dimensions: list[str] = field(default_factory=list)
    note: str = ""


@dataclass
class RetellBreakdown:
    content: Axis
    language: Axis
    # Never populated. Present as a field so that any future code averaging
    # the two axes has to do it deliberately rather than by accident.
    combined: None = None
    parts_measured: dict[str, bool] = field(default_factory=dict)
    note: str = ""


def _mean(dimensions: dict[str, float], keys) -> tuple[float | None, list[str]]:
    present = [k for k in keys if k in dimensions]
    if not present:
        return None, []
    return round(sum(dimensions[k] for k in present) / len(present), 1), present


def breakdown(dimensions: dict[str, float]) -> RetellBreakdown:
    """Split the measured dimensions into the two axes a retell has.

    ``dimensions`` is the per-response score map the pipeline already
    produced. An axis with nothing measured reports None rather than zero:
    "we could not tell" and "you scored badly" are different statements and
    the difference matters most on exactly this task.
    """
    content_score, content_from = _mean(dimensions, CONTENT_DIMENSIONS)
    language_score, language_from = _mean(dimensions, LANGUAGE_DIMENSIONS)

    note = ""
    if content_score is not None and language_score is not None:
        gap = language_score - content_score
        if gap >= 12:
            note = ("You spoke well but did not retain much of the story. That "
                    "is a listening and memory gap, not a language one — more "
                    "speaking practice will not fix it.")
        elif gap <= -12:
            note = ("You remembered the story but the delivery let it down. "
                    "The content is there; the language is what to work on.")
        else:
            note = "Content and delivery are at about the same level here."

    return RetellBreakdown(
        content=Axis(
            label="Content", score=content_score, from_dimensions=content_from,
            note=("What you retained: the points the story actually made."
                  if content_score is not None
                  else "Not enough was measured to judge what you retained."),
        ),
        language=Axis(
            label="Language", score=language_score,
            from_dimensions=language_from,
            note=("How you said it: fluency, grammar, delivery."
                  if language_score is not None
                  else "Not enough was measured to judge the delivery."),
        ),
        parts_measured=dict(CONTENT_PARTS),
        note=note,
    )

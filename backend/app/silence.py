"""What trailing-silence threshold the runner should actually advance on.

``TRAILING_SILENCE_MS = 1800`` in ``frontend/lib/speech.ts`` is a guess, and
its own comment says so: "the one number in the module that a real measurement
should eventually replace". This is how it gets replaced.

**Why it needs replacing rather than tuning by feel.** The threshold trades
two failures against each other and they are not symmetric:

* **Too low** and the runner advances while somebody is still thinking mid
  answer. That is a one-shot assessment: they do not get the rest of their
  sentence back, and the score they receive is of a truncated answer. It looks
  to every downstream measure like a short, hesitant response -- which is a
  statement about the candidate that we made up.
* **Too high** and the saving evaporates. The reason adaptive advancement
  exists is that an SVAR-style round takes eighteen minutes against a fifteen
  minute target, and a threshold nobody reaches leaves it at eighteen.

So the honest question is not "what feels right" but "at threshold T, how many
real answers would have been cut off, and how much dead air would have been
removed". Both are answerable from data already stored: the server's own VAD
writes ``FeatureRecord.speech_segments`` for every scored recording, which is
exactly the sequence of speech regions and the gaps between them.

**An internal gap is the evidence.** If a recording contains a pause of 2.1
seconds and then more speech, that candidate would have been cut off by any
threshold at or below 2.1 seconds. They demonstrably had not finished --
because they went on. No judgement, no rating panel, no study required: the
candidate's own recording says it.

**Above the frozen path, deliberately.** Nothing here scores anything or is
imported by anything that does. It reads stored features and prints a table.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Thresholds worth reporting on. Spread around the current guess rather than
# centred on it, so the table can say the guess is wrong in either direction.
CANDIDATE_THRESHOLDS_MS: tuple[int, ...] = (
    800, 1000, 1200, 1500, 1800, 2100, 2500, 3000,
)

# A recording with fewer speech regions than this has no internal gap to
# measure, so it tells us nothing about where the boundary should sit. Counted
# separately rather than silently averaged in as evidence of safety -- a
# corpus of one-word answers would otherwise "prove" any threshold is fine.
MIN_SEGMENTS_FOR_EVIDENCE = 2

# When one exact gap length dominates, the corpus is not speech.
#
# Found by running this against the estate and getting a confident answer:
# 2500 ms, on 618 recordings. It was rubbish. 551 of the 664 measured gaps
# were *exactly* 2272 ms, because they came from the synthetic audio the test
# fixtures generate, and the whole recommendation was one hardcoded pause
# length wearing a sample size.
#
# Real speech does not do that. Two people pausing for thought produce gaps
# that differ by tens of milliseconds at least; an exact repeat is a signature
# of generated audio. Ten percent is far above anything speech would produce
# and far below what a fixture produces, so the two are easy to separate.
#
# This is the failure this module was written to avoid, arriving in a shape I
# had not thought of: not too little evidence, which the informative-count
# already caught, but plenty of evidence that is not evidence of anything.
SYNTHETIC_MODAL_SHARE = 0.10


@dataclass
class Recording:
    """The part of a stored response this analysis needs."""

    response_id: str
    task_type: str
    duration_ms: int
    # [{start_ms, end_ms}], in order.
    segments: list[dict] = field(default_factory=list)


@dataclass
class Verdict:
    threshold_ms: int
    # Recordings that contain an internal pause at or over the threshold with
    # speech after it. The candidate had not finished and we would have moved
    # on anyway.
    interrupted: int
    # Recordings with at least one internal gap, so with something to say.
    informative: int
    # Total dead air the threshold would have trimmed, over every recording.
    saved_ms: int

    @property
    def interruption_rate(self) -> float:
        return self.interrupted / self.informative if self.informative else 0.0

    def __str__(self) -> str:
        return (f"{self.threshold_ms:>5} ms   "
                f"cut off {self.interrupted:>4} of {self.informative:>4} "
                f"({self.interruption_rate:6.1%})   "
                f"saved {self.saved_ms / 1000:>8.0f} s")


def internal_gaps(segments: list[dict]) -> list[int]:
    """Silences that had speech on both sides, in milliseconds.

    Trailing silence is excluded on purpose: a gap at the end is the thing the
    threshold is *for*, and counting it as evidence of a candidate being cut
    off would make every threshold look catastrophic.
    """
    ordered = sorted((s for s in segments
                      if s.get("start_ms") is not None
                      and s.get("end_ms") is not None),
                     key=lambda s: s["start_ms"])
    return [int(b["start_ms"]) - int(a["end_ms"])
            for a, b in zip(ordered, ordered[1:])
            if int(b["start_ms"]) > int(a["end_ms"])]


def trailing_silence_ms(recording: Recording) -> int:
    """Dead air after the last word. What a threshold trims."""
    ends = [int(s["end_ms"]) for s in recording.segments
            if s.get("end_ms") is not None]
    if not ends:
        return 0
    return max(0, recording.duration_ms - max(ends))


def would_interrupt(recording: Recording, threshold_ms: int) -> bool:
    """Whether advancing at this threshold would have cut this answer short."""
    return any(gap >= threshold_ms for gap in internal_gaps(recording.segments))


def sweep(recordings: list[Recording],
          thresholds: tuple[int, ...] = CANDIDATE_THRESHOLDS_MS) -> list[Verdict]:
    """The table. One row per candidate threshold."""
    informative = [r for r in recordings
                   if len(r.segments) >= MIN_SEGMENTS_FOR_EVIDENCE]

    out: list[Verdict] = []
    for threshold in thresholds:
        interrupted = sum(1 for r in informative
                          if would_interrupt(r, threshold))
        saved = sum(max(0, trailing_silence_ms(r) - threshold)
                    for r in recordings)
        out.append(Verdict(threshold_ms=threshold, interrupted=interrupted,
                           informative=len(informative), saved_ms=saved))
    return out


def recommend(verdicts: list[Verdict], tolerance: float = 0.02) -> Verdict | None:
    """The lowest threshold whose interruption rate is within tolerance.

    Lowest, not best-scoring: past the point where interruptions are rare, a
    higher threshold only spends the candidate's time. Two percent is a
    starting position and not a finding -- it is written here as an argument
    so that whoever runs this against real data can argue with it.

    Returns None when nothing measured clears the bar, which is a real answer:
    it means adaptive advancement should stay off until there is a threshold
    that does not cut people off.
    """
    eligible = [v for v in verdicts
                if v.informative and v.interruption_rate <= tolerance]
    return min(eligible, key=lambda v: v.threshold_ms) if eligible else None


async def gather(slug: str) -> list[Recording]:
    """Every scored recording in one institution, as this analysis needs it."""
    from sqlalchemy import select

    from app.db import tenant_sessionmaker
    from app.models.tenant import (FeatureRecord, ProfileSection, Response,
                                   ResponseAudio)

    async with tenant_sessionmaker(slug)() as session:
        rows = (await session.execute(
            select(FeatureRecord, ResponseAudio.duration_ms,
                   ProfileSection.task_type)
            .join(Response, Response.id == FeatureRecord.response_id)
            .join(ResponseAudio, ResponseAudio.response_id == Response.id)
            .outerjoin(ProfileSection,
                       ProfileSection.id == Response.section_id)
        )).all()

    return [Recording(response_id=feature.response_id,
                      task_type=task_type or "",
                      duration_ms=int(duration or 0),
                      segments=list(feature.speech_segments or []))
            for feature, duration, task_type in rows]


def looks_synthetic(recordings: list[Recording]) -> tuple[bool, str]:
    """Whether this corpus is generated audio rather than people talking.

    Returns the verdict and a sentence saying why, because "we will not answer
    that" is only useful next to the reason.
    """
    from collections import Counter

    gaps = [gap for r in recordings for gap in internal_gaps(r.segments)]
    if not gaps:
        return False, ""

    value, count = Counter(gaps).most_common(1)[0]
    share = count / len(gaps)
    if share >= SYNTHETIC_MODAL_SHARE:
        return True, (
            f"{count} of {len(gaps)} measured pauses are exactly {value} ms "
            f"({share:.0%}). Human speech does not repeat a gap length to the "
            f"millisecond; this is generated audio from the test fixtures.")
    return False, ""


async def report() -> str:
    """The whole thing, over every institution, as text."""
    from sqlalchemy import select

    from app.db import platform_sessionmaker
    from app.models.platform import Tenant

    async with platform_sessionmaker()() as session:
        slugs = list((await session.execute(select(Tenant.slug))).scalars().all())

    recordings: list[Recording] = []
    for slug in slugs:
        recordings.extend(await gather(slug))

    lines = [f"{len(recordings)} scored recordings across {len(slugs)} "
             f"institutions."]
    informative = [r for r in recordings
                   if len(r.segments) >= MIN_SEGMENTS_FOR_EVIDENCE]
    lines.append(f"{len(informative)} contain an internal pause, so only those "
                 f"can say anything about where the boundary belongs.")
    lines.append("")

    if not informative:
        lines.append("Nothing to measure yet. This needs real recordings of "
                     "people answering at length -- a corpus of one-word "
                     "answers cannot show where somebody was cut off, and "
                     "would report every threshold as perfectly safe.")
        return "\n".join(lines)

    verdicts = sweep(recordings)
    lines.extend(str(v) for v in verdicts)
    lines.append("")

    fake, why = looks_synthetic(recordings)
    if fake:
        lines.append("NOT A FINDING. " + why)
        lines.append("The table above is arithmetic on fixture audio. Leave "
                     "the threshold where it is until real recordings exist.")
        return "\n".join(lines)

    pick = recommend(verdicts)
    if pick is None:
        lines.append("No threshold here cuts fewer than 2% of answers short. "
                     "On this evidence adaptive advancement should stay off.")
    else:
        lines.append(f"Lowest threshold under 2% interruption: "
                     f"{pick.threshold_ms} ms "
                     f"(currently 1800 in frontend/lib/speech.ts).")
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover - a maintenance entry point
    import asyncio

    print(asyncio.run(report()))

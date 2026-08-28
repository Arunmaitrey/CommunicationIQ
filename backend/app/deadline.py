"""When an assessment runs out, and what happens then.

Four clocks exist in this product and they are not interchangeable. Three of
them already worked; this module is only about the fourth.

    prep            per item, counts down before the tone          unchanged
    item response   per item, the recording window                 unchanged
    section         advisory, sum of its items' budgets            advisory
    assessment      the whole sitting, one hard stop               new

**The invariant.** Expiry *submits the work that exists*. It does not discard
it, does not fail the attempt, and does not mark the unanswered items as
skipped in a way that reads as refusal. A candidate who ran out of time has
answered fewer questions, which is a fact about the sitting; a candidate whose
answers were thrown away has been robbed of them.

**Why the server computes it.** A browser clock can be wrong by minutes,
changed by hand, or stopped by a sleeping laptop. The deadline is derived here
from ``Attempt.started_at`` and the profile's own estimate, and the client is
told both the deadline and what time the server thinks it is -- so a countdown
can correct for skew instead of quietly running on the wrong clock. The client
displays it; the server decides.

**The section timer is advisory on purpose.** Cutting somebody off in the
middle of an item because a section budget expired would destroy an answer
mid-sentence, and the item timer already bounds every item. A section clock
that warns is useful; one that interrupts is a second authority over the same
recording, and two authorities over one recording is how answers get lost.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

# How much longer than the estimate a sitting gets.
#
# The estimate assumes every response window is used in full and nobody
# hesitates; a real candidate reads instructions and thinks. Cutting them off
# at exactly the estimate would expire a majority of honest attempts, so the
# ceiling is the estimate plus half again, floored so a short round is not
# unreasonably tight.
GRACE_FRACTION = 0.5
MIN_GRACE_MINUTES = 5

# After the deadline, an answer that arrives within this window is still
# taken. It covers the answer somebody submitted at the last second whose
# request was in flight when the clock turned over -- refusing that is
# punishing latency rather than lateness.
LATE_TOLERANCE_SECONDS = 20


def allowance_minutes(estimated_minutes: int) -> int:
    """The whole sitting's budget, including grace."""
    base = max(1, int(estimated_minutes or 0))
    return base + max(MIN_GRACE_MINUTES, round(base * GRACE_FRACTION))


def deadline_for(started_at: datetime | None,
                 estimated_minutes: int) -> datetime | None:
    """When this sitting must be over. None until it has started.

    An attempt that was created and never started has no deadline: the clock
    begins when the runner is opened, not at the moment somebody opened the
    page and went to find headphones.
    """
    if started_at is None:
        return None
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    return started_at + timedelta(minutes=allowance_minutes(estimated_minutes))


@dataclass(frozen=True)
class Clock:
    """What the client needs to run an honest countdown."""

    deadline_at: datetime | None
    server_now: datetime
    seconds_remaining: int | None
    expired: bool


def clock_for(started_at: datetime | None, estimated_minutes: int,
              now: datetime | None = None) -> Clock:
    moment = now or datetime.now(timezone.utc)
    deadline = deadline_for(started_at, estimated_minutes)
    if deadline is None:
        return Clock(None, moment, None, False)
    remaining = int((deadline - moment).total_seconds())
    return Clock(deadline, moment, max(0, remaining), remaining <= 0)


def accepts_answer(started_at: datetime | None, estimated_minutes: int,
                   now: datetime | None = None) -> bool:
    """Whether a new answer may still be taken.

    Separate from ``clock_for(...).expired`` by the late tolerance, and
    separate from whether the attempt may be *submitted* -- which is always
    allowed, because submitting is how the work that exists gets kept.
    """
    moment = now or datetime.now(timezone.utc)
    deadline = deadline_for(started_at, estimated_minutes)
    if deadline is None:
        return True
    return moment <= deadline + timedelta(seconds=LATE_TOLERANCE_SECONDS)


# How long after the bell a recording made *before* it may still arrive.
#
# The answer path and the upload path need different rules, and getting this
# wrong reintroduces the fault Phase 7 exists to fix.
#
# A recording existed before the bell, and the POST carrying it may be a retry
# after a dropped connection or a reload. Refusing *that* discards an answer
# the candidate gave inside their own time -- silent loss, arriving through
# the door built to prevent it.
#
# This once read that a chosen or written answer is composed at the moment it
# is submitted, and therefore needs no such window. That was true only while
# the runner sent typed answers exactly once and gave up on failure -- which
# is to say it was true of a bug. Now that a typed answer is queued like a
# recording, its delivery can be late for the same reason, and the same window
# applies to it, gated on the composition stamp the runner sends. See
# ``_within_deadline``.
#
# So a delivery gets a recovery window: long enough for the retry budget, a
# reload, and a walk back into signal; short enough that it is not an
# open-ended extension of the sitting. Bounded in any case by submission --
# once an attempt is submitted no upload is accepted at all.
UPLOAD_RECOVERY_MINUTES = 10


def accepts_recording(started_at: datetime | None, estimated_minutes: int,
                      now: datetime | None = None) -> bool:
    """Whether audio for an item may still be delivered.

    Deliberately more permissive than ``accepts_answer``. See the note above.
    """
    moment = now or datetime.now(timezone.utc)
    deadline = deadline_for(started_at, estimated_minutes)
    if deadline is None:
        return True
    return moment <= deadline + timedelta(minutes=UPLOAD_RECOVERY_MINUTES)


EXPIRED_MESSAGE = (
    "The time for this assessment has run out. Everything you answered has "
    "been kept and scored -- what is missing is the questions you did not "
    "reach, not the answers you gave."
)


RECORDING_TOO_LATE_MESSAGE = (
    "This recording arrived too long after the assessment ended to be part "
    "of it. It has not been deleted -- ask your admin if you believe it "
    "should count."
)

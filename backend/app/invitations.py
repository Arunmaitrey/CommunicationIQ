"""Letting somebody sit an assessment who has no account here.

A campus student is enrolled: an admin imported them, they have a cohort, and
their results belong to a record that follows them. An external candidate is
not. They are a person an employer asked to take one test, once, and the
product has never had a way to let them in — the audit's phrasing was that
everything "assumes an enrolled user".

The obvious answer is a link with a token in it. The obvious answer is also
where this goes wrong, so the rules are written down here rather than spread
through a router.

**A token is a key to one assessment, not an account.** Redeeming it mints a
session whose role is ``candidate``, and a candidate can reach exactly one
attempt of exactly one profile. Not the practice screens, not the item bank,
not another candidate's result, not their own result twice. The narrowest
thing that still lets somebody take a test.

**Single use, and used means claimed.** A link forwarded to a friend must not
let the friend sit it too. Redemption is what burns the token, not completion
-- a candidate who closes the tab mid-test gets back in with the session they
already hold, and a second person with the same link does not get a session at
all.

**Expiry is real and short by default.** An invitation that works forever is a
credential nobody remembers issuing. Seven days is long enough to arrange a
sitting and short enough that a leaked link is usually already dead.

**The candidate's details are theirs.** Name and email are captured at
redemption because a result has to belong to somebody, and nothing else is
asked for. There is no field here for date of birth, gender, or anything else
an employer might be tempted to collect through a testing tool.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

# Long enough that guessing is hopeless, short enough to paste into an email
# without wrapping. 32 url-safe characters is ~190 bits.
TOKEN_BYTES = 24

DEFAULT_VALID_DAYS = 7
MAX_VALID_DAYS = 90

# What a redeemed session may do. Deliberately not "student": a student can
# reach practice, drills, progress and every past result, and none of that
# belongs to somebody sitting one test for an employer.
CANDIDATE_ROLE = "candidate"


def new_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def expiry_for(days: int | None = None) -> datetime:
    wanted = DEFAULT_VALID_DAYS if days is None else int(days)
    wanted = max(1, min(MAX_VALID_DAYS, wanted))
    return datetime.now(timezone.utc) + timedelta(days=wanted)


@dataclass(frozen=True)
class Refusal:
    """Why a token cannot be redeemed, in words the candidate can act on."""

    reason: str
    message: str


UNKNOWN = Refusal(
    "unknown",
    "This link is not valid. Check you copied all of it, or ask whoever "
    "invited you for a new one.")
EXPIRED = Refusal(
    "expired",
    "This invitation has expired. Ask whoever invited you to send a new "
    "link -- they can do that in a moment.")
USED = Refusal(
    "used",
    "This invitation has already been used. If that was not you, tell "
    "whoever invited you, because somebody else has your link.")
WITHDRAWN = Refusal(
    "withdrawn",
    "This invitation was withdrawn. Ask whoever invited you if that was "
    "not expected.")


def check(invitation, now: datetime | None = None) -> Refusal | None:
    """Whether this invitation may be redeemed. None means yes.

    Deliberately returns *why* rather than a bare False. "Invalid link" tells
    a candidate nothing they can act on, and the three real cases -- expired,
    already used, withdrawn -- each have a different next step.

    The reasons are not a disclosure risk: somebody holding the token already
    knows it exists, and somebody who is not gets ``UNKNOWN`` from the lookup
    before reaching here.
    """
    if invitation is None:
        return UNKNOWN
    if invitation.status == "withdrawn":
        return WITHDRAWN
    if invitation.redeemed_at is not None:
        return USED

    moment = now or datetime.now(timezone.utc)
    expires = invitation.expires_at
    if expires is not None:
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if moment > expires:
            return EXPIRED
    return None


def candidate_email(token: str, given: str) -> str:
    """The email a candidate's record is filed under.

    An external candidate gives their real address and it is used. Where one
    is not given -- an employer testing in a room, on a shared machine -- the
    record still needs a unique key, so it gets one derived from the token
    rather than a blank that would collide with the next candidate.

    Never used to contact anybody. It is a primary key that happens to look
    like an email because the column is one.
    """
    cleaned = (given or "").strip().lower()
    if cleaned:
        return cleaned
    return f"candidate+{token[:12].lower()}@invite.local"

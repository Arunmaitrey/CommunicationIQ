"""A small limit on how often one caller may hit an unauthenticated endpoint.

Every other route in this application costs a session to reach, so the caller
is already a known person inside a known institution and the audit log is the
right tool. The invitation endpoints are the exception: they are open by
necessity, because the whole point is that the candidate has no account yet.

**What this defends against.** Not token guessing -- an invitation token is 24
random bytes, and no rate limit is what makes that infeasible. It defends
against the cheap thing: an open endpoint that runs two database lookups per
call, hit in a loop, costing an institution its service.

**What it does not do.** The counters live in this process. Behind two workers
a caller gets two buckets, and behind two instances, four. That is a real
limitation and it is stated rather than papered over: this is a brake, not a
gate, and an application genuinely under attack needs the limit at the edge
where every request passes through one place. Sized accordingly -- loose
enough that no honest candidate reloading a page will ever see it, tight
enough that a script notices.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

# Two limits, because one would have to be wrong in one direction or the
# other.
#
# Counting only by address punishes the normal case: a company sends thirty
# candidates a link and they sit the assessment from one office, behind one
# public address. Counting only by token misses a script walking a list.
#
# So a token may be looked at ten times a minute -- a candidate opens the
# link, reloads because the train went through a tunnel, and claims, which is
# three -- and an address may make sixty calls a minute, which no person
# reaches and a loop passes in a second.
PER_TOKEN_LIMIT = 10
PER_CALLER_LIMIT = 60
DEFAULT_LIMIT = PER_TOKEN_LIMIT
DEFAULT_WINDOW_SECONDS = 60

# Above this many distinct callers the oldest are forgotten, so a flood of
# addresses cannot turn the limiter itself into the memory leak.
MAX_TRACKED = 10_000


@dataclass
class Limiter:
    """Fixed-window counting, which is the right amount of machinery here.

    A fixed window lets a caller send twice the limit across a window
    boundary. A sliding window would not, and would cost a timestamp list per
    caller. At these sizes the difference is between 10 and 20 requests a
    minute, and neither is a threat -- so the simpler one wins, and this note
    exists so nobody mistakes the choice for an oversight.
    """

    limit: int = DEFAULT_LIMIT
    window: int = DEFAULT_WINDOW_SECONDS
    _seen: dict[str, tuple[float, int]] = field(default_factory=dict)

    def allows(self, caller: str, now: float | None = None) -> bool:
        moment = now if now is not None else time.monotonic()
        started, count = self._seen.get(caller, (moment, 0))
        if moment - started >= self.window:
            started, count = moment, 0
        if count >= self.limit:
            self._seen[caller] = (started, count)
            return False
        if len(self._seen) >= MAX_TRACKED and caller not in self._seen:
            self._forget_oldest()
        self._seen[caller] = (started, count + 1)
        return True

    def _forget_oldest(self) -> None:
        oldest = min(self._seen, key=lambda k: self._seen[k][0])
        self._seen.pop(oldest, None)

    def reset(self) -> None:
        """For tests, and for nothing else."""
        self._seen.clear()


def caller_of(request) -> str:
    """Who to count against.

    ``X-Forwarded-For`` is trusted here because this runs behind a proxy that
    sets it, and its first entry is the client. That trust is misplaced if the
    application is ever exposed directly -- a caller can send whatever they
    like -- which is the other reason this is described above as a brake.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


TOO_MANY_MESSAGE = (
    "Too many requests from this connection. Wait a minute and try the link "
    "again -- your invitation has not been used up."
)

"""Which items a section may draw on, and how it draws them.

Selection was ``task_type`` and ``status``. That is the right pool for a
diagnostic and the wrong one for a company round: an employer hiring for a
banking back-office wants the workplace material to be banking's, and a
trainer running a hard retake wants the hard half of the bank rather than a
fresh random third of all of it.

Everything here is **optional**. A section that configures nothing selects
exactly what it selected before -- which is what keeps every existing
template, every seeded profile and every speaking-only assessment behaving
identically. A filter that silently narrowed an unconfigured pool would be a
change to results nobody asked for.

**The rule that keeps being got wrong.** A property that is true of one item
source is not true of the others. ``TaskItem`` carries the classification
columns; ``QuizItem`` and ``WritingPrompt`` do not, and never will -- a
listening passage is not "for" the banking industry in any sense a filter
could act on. So ``FILTERS_FOR`` states, per source, which filters mean
anything, and a section that asks for one its source cannot honour is
**refused at publish time** rather than quietly returning nothing. That is the
ninth instance of the same mistake this codebase has made, and this time it is
declared rather than discovered.

**Difficulty is different.** All three banks carry a difficulty, so difficulty
filtering and the difficulty mix apply everywhere -- but only where the bank
is actually spread. The quiz bank sits in a narrow band, so asking it for
thirty per cent hard items gets an honest shortfall rather than an invented
one, and ``draw`` reports what it could not honour.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

# --------------------------------------------------------------------------
# The taxonomy
# --------------------------------------------------------------------------
#
# Short on purpose. The audit named BPO, IT and Banking and left an ellipsis;
# a forty-entry taxonomy nobody will ever tag against is worse than five that
# get used, and a value that is never written is indistinguishable from a
# column that does not exist. Add to this when an item actually needs it.
INDUSTRIES: tuple[str, ...] = (
    "bpo", "it", "banking", "healthcare", "retail",
    # Material that would sit in any workplace. The default, and the reason a
    # filter for one industry must not throw the general items away -- see
    # `matches` below.
    "general",
)

# Belongs to every vertical, so an industry filter keeps it.
GENERAL_INDUSTRY = "general"

# ISO 639-1. One entry today, and the column exists so a second is a data
# change rather than a schema change.
LANGUAGES: tuple[str, ...] = ("en",)
DEFAULT_LANGUAGE = "en"


def known_industry(value: str) -> bool:
    return value in INDUSTRIES


# --------------------------------------------------------------------------
# Difficulty bands
# --------------------------------------------------------------------------
#
# Edges from the live bank's own terciles rather than round numbers: the
# published task items sit between -0.93 and +1.09 with terciles at -0.08 and
# +0.40, so these three bands split the bank roughly evenly. Round numbers
# would have put four fifths of it in "medium" and made the mix control a
# decoration.
EASY_BELOW = -0.08
HARD_FROM = 0.40

BANDS: tuple[str, ...] = ("easy", "medium", "hard")


def band_of(difficulty: float | None) -> str:
    """Which band an item's difficulty falls in."""
    value = 0.0 if difficulty is None else float(difficulty)
    if value < EASY_BELOW:
        return "easy"
    if value >= HARD_FROM:
        return "hard"
    return "medium"


# --------------------------------------------------------------------------
# What each source can be filtered by
# --------------------------------------------------------------------------
#
# Keyed by the source kind from ``sections.ITEM_SOURCE``. Difficulty is
# everywhere because every bank stores one. The classification filters are
# TaskItem-only because that is the only table that carries them.
FILTERS_FOR: dict[str, frozenset[str]] = {
    "task": frozenset({"difficulty", "topics", "roles", "industries",
                       "languages"}),
    # `topics` on a quiz item is its sub-category (grammar: verb_forms,
    # tenses, articles, prepositions). Roles/industries stay TaskItem-only.
    "quiz": frozenset({"difficulty", "topics"}),
    "writing_prompt": frozenset({"difficulty"}),
}

# Every filter this module knows about, so an unknown key in a stored
# configuration is an error rather than a no-op.
ALL_FILTERS: frozenset[str] = frozenset().union(*FILTERS_FOR.values()) | {
    "min_pool", "mix"}


@dataclass(frozen=True)
class PoolFilter:
    """How one section narrows and draws from its bank.

    Every field is optional and the empty filter is the historical behaviour.
    """

    # Inclusive bounds on the item's own difficulty. None means unbounded.
    difficulty_min: float | None = None
    difficulty_max: float | None = None
    # Any-of. An empty tuple means "do not filter on this".
    topics: tuple[str, ...] = ()
    roles: tuple[str, ...] = ()
    industries: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
    # How many eligible items the section needs before it is worth running.
    #
    # A floor, not a cap. A bank exactly the size of a section serves the same
    # test on every retake, and the retake then measures memory -- so this is
    # about variety, and capping the pool would work against the thing it is
    # named for.
    min_pool: int = 0
    # {band: share}. Shares are normalised, so {"hard": 2, "easy": 1} means
    # two thirds hard. Empty means no constraint.
    mix: dict[str, float] = field(default_factory=dict)

    @property
    def configured(self) -> bool:
        return bool(self.topics or self.roles or self.industries
                    or self.languages or self.mix or self.min_pool
                    or self.difficulty_min is not None
                    or self.difficulty_max is not None)

    def unsupported_for(self, source_kind: str) -> list[str]:
        """Filters this section asks for that its bank cannot honour."""
        allowed = FILTERS_FOR.get(source_kind, frozenset())
        asked: list[str] = []
        if self.difficulty_min is not None or self.difficulty_max is not None:
            asked.append("difficulty")
        for name in ("topics", "roles", "industries", "languages"):
            if getattr(self, name):
                asked.append(name)
        return [name for name in asked if name not in allowed]


EMPTY = PoolFilter()


def from_dict(raw: dict | None) -> PoolFilter:
    """Read a stored configuration, ignoring nothing silently.

    An unknown key raises. A section configured with a misspelled filter would
    otherwise select on everything except the thing the admin typed, and the
    result looks like a working assessment.
    """
    data = dict(raw or {})
    unknown = set(data) - ALL_FILTERS - {"difficulty_min", "difficulty_max"}
    if unknown:
        raise ValueError(f"unknown selection filter(s): {sorted(unknown)}")

    def strings(key: str) -> tuple[str, ...]:
        value = data.get(key) or []
        if isinstance(value, str):
            value = [value]
        return tuple(str(v).strip().lower() for v in value if str(v).strip())

    mix = {str(k): float(v) for k, v in (data.get("mix") or {}).items()
           if float(v) > 0}
    unknown_bands = set(mix) - set(BANDS)
    if unknown_bands:
        raise ValueError(f"unknown difficulty band(s): {sorted(unknown_bands)}")

    return PoolFilter(
        difficulty_min=(None if data.get("difficulty_min") is None
                        else float(data["difficulty_min"])),
        difficulty_max=(None if data.get("difficulty_max") is None
                        else float(data["difficulty_max"])),
        topics=strings("topics"), roles=strings("roles"),
        industries=strings("industries"), languages=strings("languages"),
        min_pool=int(data.get("min_pool") or 0),
        mix=mix,
    )


def to_dict(pool: PoolFilter) -> dict:
    """Only what was configured, so an unconfigured section stores ``{}``."""
    out: dict = {}
    if pool.difficulty_min is not None:
        out["difficulty_min"] = pool.difficulty_min
    if pool.difficulty_max is not None:
        out["difficulty_max"] = pool.difficulty_max
    for name in ("topics", "roles", "industries", "languages"):
        value = getattr(pool, name)
        if value:
            out[name] = list(value)
    if pool.min_pool:
        out["min_pool"] = pool.min_pool
    if pool.mix:
        out["mix"] = dict(pool.mix)
    return out


# --------------------------------------------------------------------------
# Matching
# --------------------------------------------------------------------------

def matches(item, pool: PoolFilter, source_kind: str = "task") -> bool:
    """Whether one item is eligible under this filter.

    Applied in Python rather than SQL on purpose: the classification columns
    are free text with an "unclassified" default, and the rule about what an
    empty value means is the part worth having in one readable place.

    **An unclassified item is eligible.** The bank was authored before these
    columns existed, so nearly every item has an empty topic and an empty
    role. Excluding them would mean a single industry filter emptied the bank
    -- turning an optional narrowing into a mandatory tagging exercise, and
    breaking every existing assessment the first time anybody used it.
    """
    allowed = FILTERS_FOR.get(source_kind, frozenset())

    if "difficulty" in allowed:
        value = float(getattr(item, "difficulty", 0.0) or 0.0)
        if pool.difficulty_min is not None and value < pool.difficulty_min:
            return False
        if pool.difficulty_max is not None and value > pool.difficulty_max:
            return False

    for name, attribute in (("topics", "topic"), ("roles", "role"),
                            ("industries", "industry"),
                            ("languages", "language")):
        wanted = getattr(pool, name)
        if not wanted or name not in allowed:
            continue
        have = str(getattr(item, attribute, "") or "").strip().lower()
        if not have:
            # Unclassified: eligible for everything. See the docstring.
            continue
        # Material that belongs to no vertical belongs to all of them. "The
        # training session begins at nine" is as true in a bank as in a call
        # centre, and a banking round built only from banking-specific
        # sentences would be a bank of five items -- which is a worse test
        # than a broad one, whatever the brochure says.
        if name == "industries" and have == GENERAL_INDUSTRY:
            continue
        if have not in wanted:
            return False
    return True


def eligible(items: list, pool: PoolFilter, source_kind: str = "task") -> list:
    return [i for i in items if matches(i, pool, source_kind)]


# --------------------------------------------------------------------------
# Drawing
# --------------------------------------------------------------------------

@dataclass
class Draw:
    items: list
    # What the mix asked for and what the bank could supply. Reported rather
    # than silently absorbed: a section that asked for three hard items and
    # got one is a different test from the one that was configured, and the
    # admin is the person who can fix it.
    shortfalls: dict[str, int] = field(default_factory=dict)
    note: str = ""


def draw(items: list, count: int, pool: PoolFilter,
         rng: random.Random | None = None) -> Draw:
    """Take ``count`` items, honouring the difficulty mix where it can.

    Deterministic given ``rng``, which is what makes the distribution testable
    rather than something we hope holds on average. The greedy-selection bug
    in whole-passage selection failed only on certain shuffles and survived a
    passing end-to-end test; this function is pure so its tests cannot repeat
    that.

    Never returns a duplicate, and never returns more than ``count``.
    """
    picker = rng or random
    available = list(items)
    if count <= 0 or not available:
        return Draw(items=[])

    if not pool.mix:
        take = min(count, len(available))
        return Draw(items=picker.sample(available, take))

    # Normalise the shares, then hand out whole items largest-remainder style
    # so the counts sum to exactly `count` rather than to count-1 after
    # rounding each share down.
    total = sum(pool.mix.values())
    by_band: dict[str, list] = {b: [] for b in BANDS}
    for item in available:
        by_band[band_of(getattr(item, "difficulty", 0.0))].append(item)

    exact = {b: count * (share / total) for b, share in pool.mix.items()}
    wanted = {b: int(v) for b, v in exact.items()}
    remainder = count - sum(wanted.values())
    for band in sorted(exact, key=lambda b: exact[b] - wanted[b], reverse=True):
        if remainder <= 0:
            break
        wanted[band] += 1
        remainder -= 1

    chosen: list = []
    shortfalls: dict[str, int] = {}
    for band, asked in sorted(wanted.items()):
        pool_for_band = by_band.get(band, [])
        got = min(asked, len(pool_for_band))
        if got:
            chosen.extend(picker.sample(pool_for_band, got))
        if got < asked:
            shortfalls[band] = asked - got

    # Top up from whatever is left, so a section asking for five gets five
    # even when the bank cannot honour the shape. A short section is a worse
    # measurement than a differently-shaped one, and the shortfall is
    # reported either way.
    if len(chosen) < count:
        picked = {id(i) for i in chosen}
        rest = [i for i in available if id(i) not in picked]
        if rest:
            chosen.extend(picker.sample(rest, min(count - len(chosen), len(rest))))

    note = ""
    if shortfalls:
        parts = ", ".join(f"{n} fewer {band}" for band, n in sorted(shortfalls.items()))
        note = (f"The bank could not supply the requested mix: {parts}. "
                f"The section was filled from the rest.")
    return Draw(items=chosen, shortfalls=shortfalls, note=note)

"""Sentence completion: one missing word, typed in.

All original (CONTENT-04). A Versant-style four-skills test uses this as a
written item, and it is a genuinely different measure from the multiple-choice
grammar questions already in the quiz bank: choosing between four options
tests recognition, producing the word tests recall. A candidate who can pick
"despite" from a list and cannot produce it is exactly the candidate a
recognition-only test misses.

Each item accepts a set of answers rather than one string. English usually
allows more than one word in a slot, and marking "although" wrong because the
author happened to write "though" would teach a student something false about
their own English. Where only one word genuinely fits, the set has one member
and that is a deliberate statement rather than an oversight.

The context is workplace throughout, matching the reading and writing banks:
these are the sentences a first job actually contains.
"""
from __future__ import annotations

# (sentence with ___ for the gap, {accepted answers}, what it tests)
ITEMS: list[tuple[str, set[str], str]] = [
    ("We cannot ship on Friday ___ the test data is still missing.",
     {"because", "since", "as"}, "cause"),
    ("___ the delay, the client renewed for another year.",
     {"despite", "notwithstanding"}, "concession"),
    ("Please confirm ___ you will attend the review on Thursday.",
     {"whether", "if"}, "reported clause"),
    ("The report was returned ___ two of the figures did not match.",
     {"because", "since", "as"}, "cause"),
    ("She has been with the team ___ March.",
     {"since"}, "duration with a start point"),
    ("We have worked on this module ___ three weeks.",
     {"for"}, "duration with a length"),
    ("The migration is behind schedule, ___ the deadline still holds.",
     {"but", "although", "though", "yet"}, "contrast"),
    ("Send the invoice ___ the end of the month.",
     {"by", "before"}, "deadline preposition"),
    ("Neither the manager ___ the client was told.",
     {"nor"}, "correlative pair"),
    ("If we ___ more time, we could test every edge case.",
     {"had"}, "unreal conditional"),
    ("The team is responsible ___ the release notes.",
     {"for"}, "dependent preposition"),
    ("He apologised ___ missing the meeting.",
     {"for"}, "dependent preposition"),
    ("We agreed ___ postpone the demo by a week.",
     {"to"}, "verb complement"),
    ("Each of the three services ___ its own database.",
     {"has"}, "agreement with 'each'"),
    ("The figures ___ checked twice before the report went out.",
     {"were"}, "past passive"),
    ("I look forward ___ hearing from you.",
     {"to"}, "fixed phrase"),
    ("There is little point ___ rewriting it now.",
     {"in"}, "fixed phrase"),
    ("The client asked us ___ explain the delay in plain language.",
     {"to"}, "verb complement"),
    ("The invoice must be paid ___ the end of the month.",
     {"by", "before"}, "time preposition"),
    ("She has worked in this team ___ 2019.",
     {"since"}, "since"),
    ("We will start the review ___ everyone has arrived.",
     {"when", "once", "after"}, "time clause"),
    ("He is responsible ___ onboarding the new hires.",
     {"for"}, "preposition"),
    ("The forecast depends ___ the sample we collected.",
     {"on", "upon"}, "preposition"),
    ("___ finishing the draft, she shared it with the client.",
     {"after", "upon"}, "time"),
    ("The updated policy applies ___ all contractors as well.",
     {"to"}, "preposition"),
]


def normalise(answer: str) -> str:
    """What a typed answer means, ignoring what it looks like.

    Case, surrounding whitespace and trailing punctuation are stripped: a
    candidate who types "Because" or "because," knew the word, and marking
    them wrong measures typing rather than English.
    """
    import re

    return re.sub(r"^[^a-z']+|[^a-z']+$", "", answer.strip().lower())


def is_correct(answer: str, accepted: set[str]) -> bool:
    """Whether a typed answer is one of the accepted words."""
    given = normalise(answer)
    return bool(given) and given in {normalise(a) for a in accepted}

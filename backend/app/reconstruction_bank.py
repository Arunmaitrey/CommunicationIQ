"""Passage reconstruction: read it, lose it, write it back.

Short passages -- forty to sixty words -- shown for a fixed number of seconds
and then taken away. The candidate writes what the passage said. It is the
one task in the suite that measures holding meaning in working memory and
re-expressing it, which is what taking notes in a meeting actually is.

**Idea units, not sentences.** Each passage carries the things it says, and
each of those carries the words that would show it came back. A candidate who
writes "they moved it to Thursday" has retained the same unit as one who
writes "the date changed to Thursday", and a scorer matching the author's
sentence would mark the first one wrong. The cue lists are what make the
measure survive paraphrase -- which is the whole point of the task, since a
verbatim answer is not what is being asked for.

**Deliberately short.** A sixty-word passage is at the edge of what fits in
working memory. Longer would measure note-taking speed, and the passage is
taken away precisely so that it cannot be copied.

**One honest limitation.** The passage text is in the runner payload, because
the browser has to render it. A candidate who opens the network tab can read
it back after it disappears. That is the same accepted trade-off as the spoken
prompt text, and it is why ``verbatim_share`` is recorded against every
answer: an answer that reproduces long runs of the source word for word is
visible in the evidence even though nothing scores on it.

All original (CONTENT-04).
"""
from __future__ import annotations

# (title, passage, [(idea unit, [cues])])
#
# No reading window is stored. How long a passage may be looked at is a
# function of how long it is -- `reconstruction.reading_seconds` computes it
# from the word count -- and a number typed next to each passage would be one
# more thing to keep in step with an edited passage, silently wrong when
# nobody did.
PASSAGES: list[tuple[str, str, list[tuple[str, list[str]]]]] = [
    (
        "Deadline moved",
        "The client has moved the review from Thursday to the following "
        "Monday. They want the draft two days before, so it now needs to be "
        "with them by the Saturday. Nothing else about the scope has changed.",
        [("the review moved to Monday", ["monday"]),
         ("it was Thursday before", ["thursday"]),
         ("the draft is due two days earlier", ["two days", "saturday",
                                                "2 days"]),
         ("the scope is unchanged", ["scope", "nothing else", "same scope"])],
    ),
    (
        "Support hours",
        "From next month the support desk will open at eight rather than "
        "nine, and will close at six as before. The team is not growing, so "
        "the extra hour in the morning comes out of the afternoon cover.",
        [("the desk opens an hour earlier", ["eight", "8", "earlier"]),
         ("closing time is unchanged", ["six", "6", "same", "as before"]),
         ("the team is not growing", ["not growing", "no new", "same team",
                                      "not getting larger"]),
         ("afternoon cover is reduced", ["afternoon"])],
    ),
    (
        "Laptop policy",
        "Anyone taking a laptop home must record it with the office manager "
        "on the way out. The machine does not need to be returned the next "
        "day, but it must be back in the building before any audit week.",
        [("laptops taken home must be recorded", ["record", "log", "sign",
                                                  "register", "tell"]),
         ("with the office manager", ["office manager", "manager"]),
         ("it need not come back the next day", ["next day", "not the next"]),
         ("it must be back before an audit week", ["audit"])],
    ),
    (
        "Test data",
        "The staging database was rebuilt on Friday, so any test accounts "
        "created before then are gone. New ones can be made from the admin "
        "screen. Live data was not touched at any point.",
        [("staging was rebuilt on Friday", ["rebuilt", "friday", "reset"]),
         ("old test accounts are gone", ["gone", "deleted", "lost", "removed",
                                         "wiped"]),
         ("new ones come from the admin screen", ["admin"]),
         ("live data was untouched", ["live", "production", "not touched",
                                      "unaffected"])],
    ),
    (
        "New joiner",
        "Priya joins the team on the first of next month and will sit with "
        "the reporting group for her first two weeks. She reports to Anil "
        "from the start, not after the two weeks are over.",
        [("Priya joins next month", ["priya", "joins", "starts"]),
         ("she sits with reporting for two weeks", ["reporting", "two weeks",
                                                    "2 weeks"]),
         ("she reports to Anil", ["anil"]),
         ("from the start, not later", ["from the start", "immediately",
                                        "straight away", "day one",
                                        "not after"])],
    ),
    (
        "Printer",
        "The printer on the second floor is out of service until the part "
        "arrives, which is expected on Wednesday. Until then, print jobs "
        "should go to the ground floor machine, which has no colour tray.",
        [("the second floor printer is out of service", ["second floor",
                                                         "2nd floor",
                                                         "out of service",
                                                         "broken", "not work"]),
         ("a part is expected Wednesday", ["wednesday", "part"]),
         ("use the ground floor machine", ["ground floor", "downstairs"]),
         ("it has no colour", ["colour", "color", "black and white"])],
    ),
    (
        "Expense claims",
        "Claims submitted after the twentieth of the month are paid in the "
        "following month's run rather than being held. Receipts must be "
        "attached at the time of submission; they cannot be sent afterwards.",
        [("claims after the twentieth wait a month", ["twentieth", "20th",
                                                      "next month",
                                                      "following month"]),
         ("they are not held", ["not held", "rather than", "instead of"]),
         ("receipts go in at submission", ["receipt", "at the time",
                                           "when you submit"]),
         ("they cannot follow later", ["cannot", "can't", "not afterwards",
                                       "not later"])],
    ),
    (
        "Interview panel",
        "The panel for Thursday is three people rather than the usual two, "
        "because the role covers both teams. Each interviewer scores the "
        "candidate independently, and the three scores are only compared "
        "afterwards, once any discussion takes place.",
        [("the panel is three, not two", ["three", "3"]),
         ("because the role covers both teams", ["both teams", "two teams",
                                                 "covers both"]),
         ("scoring is independent", ["independent", "separately", "on their own",
                                     "alone"]),
         ("discussion comes after scoring", ["before", "after", "discussion"])],
    ),
]

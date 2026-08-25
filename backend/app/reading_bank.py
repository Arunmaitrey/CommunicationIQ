"""Passages to read, with comprehension questions and a rate measure.

All original (CONTENT-04). The shapes are what a campus placement round or a
first job actually puts in front of someone -- a policy email, a status
report, a notice, a short article -- rather than the literary extracts that
comprehension exercises default to. A student who can follow a badly written
internal email is better prepared than one who can parse a paragraph of
prose.

The same two rules as the listening bank, for the same reasons:

* **The answer is never liftable from the question.** Matching a keyword in
  the stem to the same keyword in the passage is scanning, not comprehension.
* **At least one question per passage needs the whole thing** -- what the
  writer implied, what follows, what someone should now do.

And the same authoring convention: the correct option is written first for
reviewability and rotated on the way into the database, because a key that
always sits at index 0 lets a student score full marks without reading. See
``listening_bank.rotated``.

One extra property matters here. Several passages deliberately **bury the
qualification** -- a sentence early on that a later sentence narrows or
reverses. Skimmers reliably miss those, which is exactly what a reading-rate
measure paired with comprehension is meant to expose: reading quickly is only
a strength if the comprehension survives it.
"""
from __future__ import annotations

from app.listening_bank import rotated

# (title, kind, difficulty, body, [(stem, [options], correct_index, why), ...])
PASSAGES: list[tuple] = [
    (
        "Email: change to expense claims", "email", -0.3,
        "Team,\n\n"
        "From the first of next month, expense claims move to the new portal. "
        "Paper forms will not be accepted after that date. Claims for spending "
        "in the current month may still be submitted on paper up to the "
        "fifteenth, to give everyone time to move across.\n\n"
        "Two things worth knowing. Receipts must now be attached at the point "
        "of claiming rather than emailed separately, and any claim over five "
        "thousand rupees needs your manager's approval inside the portal "
        "before finance sees it. Smaller claims go straight through.\n\n"
        "If you are mid-way through a claim on paper, finish it on paper. Do "
        "not enter it twice.\n\n"
        "Ravi",
        [
            ("A claim for 3,200 rupees is entered in the portal. What happens next?",
             ["It goes straight to finance",
              "It waits for the manager's approval",
              "It is rejected as too small for the portal",
              "It must also be submitted on paper"],
             0,
             "The approval rule applies over five thousand; the last sentence "
             "of that paragraph is the qualification a skimmer misses."),
            ("It is the tenth of next month. Can a paper form still be used?",
             ["Yes, for spending in the previous month only",
              "Yes, for any spending",
              "No, paper stopped on the first",
              "Only with the manager's written approval"],
             0,
             "Two dates interact: paper stops on the first for new spending, "
             "but the previous month's claims run to the fifteenth."),
            ("What changed about receipts?",
             ["They are attached while claiming rather than emailed",
              "They are no longer required",
              "They must be posted to finance",
              "They are only needed above five thousand rupees"],
             0,
             "'Rather than emailed separately' -- the wrong options are all "
             "plausible processes that were not described."),
        ],
    ),
    (
        "Notice: library access over the vacation", "notice", -0.2,
        "The main library will remain open through the vacation, but on "
        "reduced hours: nine to five on weekdays and closed at weekends. The "
        "reading rooms on the second floor stay open until eight, including "
        "Saturdays, for students with a valid research card.\n\n"
        "Borrowing limits are unchanged. However, because the vacation period "
        "counts as a single loan period, books issued now are due back on the "
        "first day of term rather than after the usual three weeks.\n\n"
        "The digital catalogue is unaffected and remains available at all "
        "hours.",
        [
            ("A student without a research card wants to study on a Saturday. Can they?",
             ["No, the main library is closed at weekends",
              "Yes, until five",
              "Yes, until eight in the reading rooms",
              "Only if the digital catalogue is unavailable"],
             0,
             "The Saturday opening is reading-rooms-only and card-only. Both "
             "conditions have to be carried at once."),
            ("A book is borrowed during the vacation. When is it due?",
             ["On the first day of term",
              "Three weeks later",
              "At the end of the vacation",
              "It cannot be borrowed during the vacation"],
             0,
             "The passage says borrowing limits are unchanged and then "
             "narrows the due date -- the qualification follows the "
             "reassurance."),
            ("What is completely unaffected by the vacation arrangements?",
             ["The digital catalogue", "The reading room hours",
              "The borrowing period", "The weekend opening"],
             0,
             "Stated in the last line; every wrong option changed."),
        ],
    ),
    (
        "Status report: the migration is behind", "report", 0.2,
        "Progress this fortnight was slower than planned. Of the fourteen "
        "services scheduled for migration, nine have moved and are stable. "
        "Three more are ready but blocked on a firewall change requested a "
        "week ago and not yet approved. The remaining two turned out to share "
        "a database with a system nobody had documented, and cannot be moved "
        "until that dependency is understood.\n\n"
        "The firewall change is the smaller problem: it is a queue, not a "
        "technical obstacle, and once approved the three services move in an "
        "afternoon. The undocumented dependency is the real risk to the "
        "timeline, because we do not yet know how large it is.\n\n"
        "I am not recommending we move the deadline this fortnight. I am "
        "flagging that if the dependency is not understood within the next "
        "two weeks, the deadline will not hold and we should say so early "
        "rather than late.",
        [
            ("How many services are neither migrated nor blocked on the firewall?",
             ["Two", "Three", "Five", "Nine"],
             0,
             "Fourteen total, nine moved, three firewall-blocked, so two "
             "remain -- and those are the dependency ones. Every wrong option "
             "is a real number from the passage."),
            ("Which problem does the writer consider more serious?",
             ["The undocumented shared database",
              "The firewall approval queue",
              "The number of services still to move",
              "The two-week reporting cycle"],
             0,
             "Stated directly, and the reason is given: the size is unknown."),
            ("What is the writer actually asking for?",
             ["Nothing yet, but early warning if the risk materialises",
              "An immediate extension to the deadline",
              "Approval of the firewall change",
              "More people on the migration"],
             0,
             "The last paragraph opens by ruling out the obvious reading. A "
             "skimmer takes 'the deadline will not hold' and misses 'I am not "
             "recommending we move the deadline'."),
            ("What does the writer mean by calling the firewall issue 'a queue, not a technical obstacle'?",
             ["It needs waiting on, not solving",
              "It will resolve itself without anyone acting",
              "It is somebody else's responsibility",
              "It has already been approved"],
             0,
             "Inference. The distinction is between work and delay, and it is "
             "not spelled out."),
        ],
    ),
    (
        "Article: why interview practice often fails", "article", 0.4,
        "Most advice about interview preparation concentrates on answers. "
        "Candidates are told to prepare a story about a conflict, a story "
        "about a failure, a story about leadership. This is reasonable as far "
        "as it goes, and it produces a recognisable kind of candidate: fluent "
        "for ninety seconds and then lost, because the second question was "
        "not the one they rehearsed.\n\n"
        "The difficulty is that preparation of that sort trains recall rather "
        "than thinking. An interviewer is rarely testing whether you have a "
        "story ready. They are testing whether you can be specific under mild "
        "pressure, and whether the specifics hold together when someone asks "
        "why.\n\n"
        "A better exercise is to take one real thing you did and have someone "
        "ask you 'why' four times in a row. The first answer is usually the "
        "rehearsed one. The second is vaguer. By the fourth, either you find "
        "the actual reasoning or you discover that you did the thing because "
        "somebody told you to — which is worth knowing before an interviewer "
        "finds it out for you.",
        [
            ("What does the writer say is wrong with rehearsing stories?",
             ["It trains recall instead of thinking",
              "The stories chosen are usually the wrong ones",
              "Candidates do not rehearse enough of them",
              "Interviewers have heard them all before"],
             0,
             "The second paragraph names it. The fourth option is a plausible "
             "criticism the writer never makes."),
            ("According to the passage, what are interviewers actually testing?",
             ["Whether specifics hold up under questioning",
              "Whether a candidate has prepared thoroughly",
              "How fluently a candidate speaks for ninety seconds",
              "Whether a candidate has led a team before"],
             0,
             "Fluency for ninety seconds is described as the *symptom* of bad "
             "preparation, not the thing being tested."),
            ("What does the 'four whys' exercise reveal, on the writer's account?",
             ["Either your real reasoning, or that you had none",
              "Which of your stories is strongest",
              "How long you can speak without pausing",
              "Which questions an interviewer is likely to ask"],
             0,
             "The final sentence gives two outcomes, and the second is the "
             "uncomfortable one the passage is really about."),
            ("What is the writer's attitude to conventional advice?",
             ["Reasonable but insufficient",
              "Actively harmful and best ignored",
              "Correct for freshers, wrong for experienced candidates",
              "Impossible to follow without coaching"],
             0,
             "'Reasonable as far as it goes' -- the passage qualifies rather "
             "than rejects, and reading it as rejection is the common error."),
        ],
    ),
    (
        "Instructions: submitting the final project", "instructions", 0.0,
        "Submit one archive containing your source code and a one-page "
        "readme. Do not include the compiled output or the dependency folder; "
        "submissions over twenty megabytes will be rejected automatically and "
        "you will not be notified.\n\n"
        "Name the archive with your roll number only. Do not add your name, "
        "as marking is anonymous. If you worked in a pair, both members submit "
        "identically named archives from their own accounts, and the readme "
        "names both.\n\n"
        "The deadline is five o'clock on the twenty-eighth. Late submissions "
        "lose ten per cent per day, counted from the deadline rather than from "
        "the end of that day.",
        [
            ("A pair worked together. How many archives are submitted?",
             ["Two, one from each member",
              "One, from either member",
              "One, from the member whose roll number is lower",
              "Two, with different names"],
             0,
             "'Both members submit' and 'identically named' have to be held "
             "together -- the last option gets one of the two right."),
            ("A submission is 25 MB. What happens?",
             ["It is rejected and the student is not told",
              "It is accepted with a penalty",
              "It is rejected and the student is emailed",
              "It is accepted if the readme explains why"],
             0,
             "The 'you will not be notified' clause is the sting, and it sits "
             "at the end of a sentence about something else."),
            ("A submission arrives at nine in the morning on the twenty-ninth. What is the penalty?",
             ["Ten per cent", "Nothing, it is the same day",
              "Twenty per cent", "It is not accepted at all"],
             0,
             "Counted from the deadline, not the end of the day -- the "
             "qualification is the whole point of that sentence."),
        ],
    ),
]


def word_count(text: str) -> int:
    """Words in a passage, for the rate denominator.

    Whitespace-split rather than anything cleverer: it is what every
    words-per-minute figure a student has ever seen is based on, and a more
    sophisticated count would make this one incomparable with those.
    """
    return len(text.split())


def flat_questions() -> list[tuple]:
    """Every question with its rotation applied, numbered across the bank."""
    out: list[tuple] = []
    n = 0
    for passage in PASSAGES:
        for stem, options, correct, why in passage[4]:
            rolled, index = rotated(n, list(options), correct)
            out.append((passage[0], stem, rolled, index, why))
            n += 1
    return out

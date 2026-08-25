"""Response selection and vocabulary in context: two chosen-answer banks.

Both are answered by choosing, and there the resemblance ends — which is why
they are separate categories rather than one "multiple choice" bucket.

**Response Selection** plays a line and asks which reply fits. It measures
pragmatic appropriateness: whether a candidate can tell a reply that works
from one that is grammatical and lands badly. Every distractor here is a
correct English sentence; none of them can be eliminated on grammar. That is
the point, and it is why this cannot be marked by the comprehension scorer —
there is no passage to have understood, only a judgement about register and
intent.

**Vocabulary in Context** gives a word inside a sentence and asks what it
means *there*. Not a dictionary test: every option is a real sense of the
word, and only the context distinguishes them. A candidate who knows the most
common meaning and cannot read the sentence will pick the wrong one, which is
exactly the ability being measured.

Neither groups by passage. Response selection items are independent
exchanges; vocabulary items carry their own one-sentence context. Grouping
them the way comprehension groups would make a section of four unfillable
from a bank of twenty, which is what happened to sentence completion before
grouping was declared per category.

All original (CONTENT-04).
"""
from __future__ import annotations

# -- Response selection ----------------------------------------------------
#
# (spoken line, [replies], index of the reply that fits, why)
#
# The spoken line is played, never shown. The replies are read, because in
# life you have a moment to choose what to say and no moment to re-hear what
# was said to you.
RESPONSES: list[tuple[str, list[str], int, str]] = [
    ("I am afraid we cannot make the Friday deadline.",
     ["Thanks for telling me early. What date can you manage?",
      "That is not acceptable.",
      "Yes, Friday is fine.",
      "I will let the client know it is on track."],
     0,
     "Acknowledges and moves to the next decision. The second is grammatical "
     "and closes the conversation; the third and fourth ignore what was said."),

    ("Sorry, could you say that again? The line is not clear.",
     ["Of course — I said the meeting has moved to eleven.",
      "I already told you.",
      "Can you hear me now?",
      "Yes, the line is not clear."],
     0,
     "Repeats the content. The others respond to the interruption rather "
     "than to the request."),

    ("Your report was very useful, though the summary was a little long.",
     ["Thank you — I will tighten the summary next time.",
      "It had to be that long.",
      "Sorry, I will rewrite the whole thing.",
      "Which part did you not read?"],
     0,
     "Takes the praise and the correction. The second is defensive, the "
     "third over-corrects, the fourth is hostile."),

    ("Do you have five minutes to look at something?",
     ["I am in a call until three — would just after that work?",
      "No.",
      "Yes, five minutes exactly.",
      "What is it about?"],
     0,
     "Declines the moment while offering another. The fourth is not wrong, "
     "but it answers a different question than the one asked."),

    ("I think there may be an error in the figures you sent.",
     ["Let me check and come back to you within the hour.",
      "The figures came from the system.",
      "Which figures?",
      "I checked them twice."],
     0,
     "Owns the check. The second and fourth defend before looking, which is "
     "the most common register mistake in this population."),

    ("Welcome to the team — let me know if anything is unclear.",
     ["Thank you. I will note things down and ask in one go rather than "
      "interrupting.",
      "Everything is unclear.",
      "Nothing is unclear.",
      "I will ask you every time."],
     0,
     "Accepts the offer and proposes a workable pattern."),

    ("We will need the draft by Wednesday instead of Friday.",
     ["That is tight. I can do Wednesday if the review is dropped.",
      "Fine.",
      "That is impossible.",
      "Wednesday was always the date."],
     0,
     "Negotiates with a trade. 'Fine' hides a risk; the others refuse or "
     "rewrite history."),

    ("Could you explain that in simpler terms?",
     ["Of course. In short, the page loads more data than it needs to.",
      "It is quite technical.",
      "I already explained it.",
      "Which part did you not follow?"],
     0,
     "Simplifies immediately. The fourth sounds reasonable and puts the work "
     "back on the person who asked."),
]


# -- Vocabulary in context -------------------------------------------------
#
# (sentence containing the word, target word, [senses], index of the sense
#  used here, why)
#
# Every option is a genuine meaning of the word. Only the sentence decides.
VOCABULARY: list[tuple[str, str, list[str], int, str]] = [
    ("The team could not resolve the dispute, so it went to the manager.",
     "resolve",
     ["settle or bring to an end", "decide firmly to do something",
      "separate into parts", "become clear in detail"],
     0,
     "All four are real senses of 'resolve'. A dispute is settled."),

    ("She resolved to send the report before leaving that evening.",
     "resolve",
     ["decide firmly to do something", "settle or bring to an end",
      "separate into parts", "vote on a motion"],
     0,
     "The same word, the other common sense. Context is the only signal."),

    ("The new policy will affect everyone in the department.",
     "affect",
     ["have an effect on", "pretend to have", "a feeling or emotion",
      "put on a manner"],
     0,
     "'Affect' as a verb meaning influence, not the pretence sense."),

    ("Please address the second point in your reply.",
     "address",
     ["deal with", "speak formally to a group", "where somebody lives",
      "write a destination on an envelope"],
     0,
     "Deal with. The other three are all ordinary uses of the word."),

    ("The figures in the appendix qualify the claim made on page one.",
     "qualify",
     ["limit or make less absolute", "become eligible",
      "reach the next round", "describe a quality"],
     0,
     "The academic sense: narrowing a claim rather than earning a place."),

    ("He was let go after the merger.",
     "let go",
     ["dismissed from a job", "released from a grip",
      "stopped worrying about something", "allowed to leave a room"],
     0,
     "A workplace euphemism a candidate will meet and should recognise."),

    ("The proposal is sound, but the timing is wrong.",
     "sound",
     ["well reasoned and reliable", "a noise", "measure the depth of water",
      "in good health"],
     0,
     "Adjective sense. The noun is far more frequent, which is the trap."),

    ("We need to table the discussion until the client responds.",
     "table",
     ["postpone", "a piece of furniture", "arrange data in rows",
      "put forward for discussion"],
     0,
     "In Indian and British usage 'table' can mean to put forward; here the "
     "sentence's 'until' forces the postpone reading. Context decides."),

    ("Her account of the meeting differs from mine.",
     "account",
     ["a description of what happened", "a bank arrangement",
      "a customer relationship", "an explanation of a cost"],
     0,
     "Narrative sense, in a workplace where the financial senses dominate."),

    ("The issue was raised at the last review and has not moved since.",
     "raised",
     ["brought up for attention", "lifted upwards", "increased in amount",
      "brought up a child"],
     0,
     "Brought up for attention."),

    ("We should observe how the new process performs before changing it.",
     "observe",
     ["watch carefully", "obey a rule", "remark on something",
      "celebrate a day"],
     0,
     "Watch carefully. 'Observe a rule' is the near neighbour."),

    ("The manager will run the session on Thursday.",
     "run",
     ["be in charge of", "move quickly on foot", "operate a machine",
      "compete in an election"],
     0,
     "Be in charge of."),
]

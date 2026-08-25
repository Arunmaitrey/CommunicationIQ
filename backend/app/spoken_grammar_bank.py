"""Spoken grammar: hear a flawed or gapped sentence, say the whole correct one.

Two task types, one mechanic, straight from the researched company rounds
(TCS/Infosys/Wipro sections E and F):

    spoken_completion   a sentence with one word missing is heard; the
                        candidate says the complete sentence aloud
    spoken_correction   a sentence with one error is heard; the candidate says
                        the corrected sentence aloud

Both are *speaking* tasks, deliberately. The earlier build served these
sections as the typed/chosen grammar items, and the acceptance review rejected
that as a product deviation: in the researched assessments the candidate must
*produce the sentence out loud*, and spoken production and written recognition
are different abilities. The channel is part of the assessment.

Mechanically they are Repeat Sentence with a twist: the played prompt
(``prompt_text``) is the flawed/gapped sentence, and the scored target
(``reference_text``) is the correct one -- so the accuracy provider measures
whether the right sentence came out, which *is* the grammar signal here.

The gap in a completion is spoken as the word "blank", and the instructions
say so. The real assessments use a tone; a clearly-said "blank" carries the
same information through the synthesiser we have. Documented limitation.

All original (CONTENT-04). Workplace register throughout.
"""
from __future__ import annotations

# (heard_with_gap, full_correct_sentence)
COMPLETIONS: tuple[tuple[str, str], ...] = (
    ("She blank the meeting because her train was delayed.",
     "She missed the meeting because her train was delayed."),
    ("The report must be blank before the end of the day.",
     "The report must be submitted before the end of the day."),
    ("We have been working blank this client since January.",
     "We have been working with this client since January."),
    ("He is responsible blank training the new employees.",
     "He is responsible for training the new employees."),
    ("If the printer stops working, please blank the support team.",
     "If the printer stops working, please contact the support team."),
    ("The results were better blank we expected.",
     "The results were better than we expected."),
    ("All visitors must blank at the reception desk.",
     "All visitors must register at the reception desk."),
    ("The manager asked us to blank the figures once more.",
     "The manager asked us to check the figures once more."),
)

# (heard_with_error, corrected_sentence)
CORRECTIONS: tuple[tuple[str, str], ...] = (
    ("She don't have the access she needs for the new system.",
     "She doesn't have the access she needs for the new system."),
    ("The documents was sent to the client yesterday evening.",
     "The documents were sent to the client yesterday evening."),
    ("He have finished the report before the deadline.",
     "He has finished the report before the deadline."),
    ("We discussed about the new policy in the meeting.",
     "We discussed the new policy in the meeting."),
    ("Each of the team members have received the schedule.",
     "Each of the team members has received the schedule."),
    ("The train leave at nine, so we should start early.",
     "The train leaves at nine, so we should start early."),
    ("I am agree with the changes you have proposed.",
     "I agree with the changes you have proposed."),
    ("She is working here since two thousand and twenty.",
     "She has been working here since two thousand and twenty."),
)

# Read-aloud word lists (the researched Cognizant Q11-15: isolated words read
# clearly). Served by the ordinary read_aloud engine -- the reference is the
# words themselves -- and kept in their own difficulty band (1.2) so only a
# section that asks for that band draws them. The band is reserved: sentences
# sit at or below 1.0 and paragraphs at 2.0.
WORD_LIST_DIFFICULTY = 1.2
WORD_LISTS: tuple[str, ...] = (
    "colleague, schedule, receipt, courteous, immediately",
    "particular, opportunity, development, necessary, comfortable",
    "temperature, vegetable, literature, secretary, interesting",
    "responsibility, communication, organisation, approximately, environment",
    "purchase, warranty, technician, appointment, available",
)

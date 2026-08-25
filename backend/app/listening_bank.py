"""Passages to listen to, and questions written against them.

All original, like the rest of the content here (CONTENT-04). The shapes
imitate what campus rounds and vendor tests actually use -- an announcement,
a set of instructions, a short talk, a voicemail, a two-person exchange --
and none of the wording is taken from any of them.

Two rules held throughout, because they are what separate a listening test
from a memory test:

* **The answer is never a word you can lift from the question.** If the stem
  says "platform" and the passage says "platform", a student can pattern-match
  a half-heard fragment. The questions ask what changed, what follows, what
  someone should now do.
* **At least one question per passage needs the whole thing.** A passage where
  every answer sits in one sentence tests attention for four seconds. Gist and
  inference questions are what make it comprehension.

Distractors are drawn from the passage rather than invented. A wrong option
that appears nowhere in the audio is eliminated without listening; a wrong
option that *was* said, in a different role, is the one that separates
students who followed the passage from students who caught keywords.

**Authoring convention: the correct answer is written first, and rotated on
the way into the database.** Writing the key at index 0 keeps these tuples
readable and reviewable -- you can check an answer against its explanation
without counting positions. But storing them that way would mean a student
who taps the first option every time scores full marks without listening to
anything, which is exactly the failure this module exists to catch.
``rotated()`` moves each key to a different position deterministically, so
the bank stays easy to read, the stored data has no positional tell, and a
reseed produces the same layout rather than reshuffling under students who
have already answered.
"""
from __future__ import annotations

# (title, kind, approx_seconds, plays_allowed, difficulty, transcript,
#  [(stem, [options], correct_index, explanation), ...])
PASSAGES: list[tuple] = [
    (
        "Platform change at the station", "announcement", 30, 1, -0.4,
        "Attention passengers. The Intercity Express to Pune, scheduled to "
        "depart at ten fifteen from platform three, will now leave from "
        "platform six. Passengers who have already boarded at platform three "
        "are requested to move across using the footbridge at the north end. "
        "The departure time is unchanged.",
        [
            ("What should passengers already on platform three do?",
             ["Move to platform six using the north footbridge",
              "Wait where they are for a replacement train",
              "Leave the station and return at ten fifteen",
              "Go to platform three's south exit"],
             0,
             "The announcement names both the new platform and the route to "
             "it. The south exit is a distractor built from 'north end'."),
            ("What has NOT changed?",
             ["The departure time", "The platform", "The platform the train leaves from",
              "The footbridge that is open"],
             0,
             "The last sentence is the whole answer: the time is unchanged, "
             "the platform is what moved."),
        ],
    ),
    (
        "Instructions before a written test", "instructions", 40, 1, -0.2,
        "Before we begin, please switch your phones off completely rather "
        "than to silent. You will have ninety minutes for the paper. There "
        "are four sections and you may attempt them in any order, but do not "
        "detach the answer sheet from the question booklet. If you finish "
        "early, stay seated and raise your hand, and someone will collect "
        "your paper.",
        [
            ("What are candidates told to do with their phones?",
             ["Switch them off entirely", "Set them to silent",
              "Leave them at the front of the room",
              "Keep them face down on the desk"],
             0,
             "'Off completely rather than to silent' -- silent is the wrong "
             "option precisely because it was said."),
            ("A candidate finishes after sixty minutes. What should they do?",
             ["Stay seated and raise a hand",
              "Take their paper to the invigilator",
              "Leave quietly through the back",
              "Detach the answer sheet and hand it in"],
             0,
             "Two plausible-sounding actions were mentioned in other roles: "
             "collecting is done by staff, and detaching is forbidden."),
            ("Which statement about the four sections is correct?",
             ["They can be attempted in any order",
              "They must be attempted in order",
              "Each has its own time limit",
              "Only three of the four are compulsory"],
             0,
             "The ninety minutes covers the whole paper, not each section."),
        ],
    ),
    (
        "Voicemail about a rescheduled interview", "voicemail", 35, 2, 0.0,
        "Hello, this is Meera from the HR team at Sundar Systems. I am "
        "calling about your interview, which was set for Thursday morning. "
        "The panel has a conflict, so we would like to move it to Friday at "
        "the same time, eleven o'clock. The location is the same. Please "
        "confirm by replying to the email I sent this morning rather than "
        "calling this number, as I am travelling this week.",
        [
            ("How does Meera want the candidate to respond?",
             ["By replying to her email", "By calling the number she rang from",
              "By confirming with the panel directly",
              "By coming to the office on Thursday"],
             0,
             "She explicitly rules out calling, and gives the reason."),
            ("What is changing about the interview?",
             ["The day, but not the time or place",
              "The time, but not the day",
              "The location only",
              "The day and the location"],
             0,
             "Thursday to Friday, eleven o'clock unchanged, same location. "
             "This needs the whole message rather than one sentence."),
            ("Why does Meera not want a phone call?",
             ["She will be travelling", "She is in interviews all week",
              "The number does not accept incoming calls",
              "She prefers written records"],
             0,
             "Stated at the end. 'Written records' is a reasonable guess and "
             "is not what she said."),
        ],
    ),
    (
        "A short talk on why projects slip", "short_talk", 55, 1, 0.3,
        "When a project runs late, the reason people give is usually that "
        "the work was harder than expected. In my experience that is rarely "
        "the whole story. What actually happens is that the difficult part "
        "is identified early, everyone agrees it is difficult, and then it is "
        "scheduled last, because the easier work can be started immediately "
        "and shows progress. By the time anyone reaches the hard part, there "
        "is no room left in the plan. The fix is not to work faster. It is to "
        "attempt the risky piece first, while there is still time to be wrong "
        "about it.",
        [
            ("What does the speaker say is the real cause of delay?",
             ["Difficult work is scheduled last",
              "The work is harder than anyone expected",
              "Teams do not work quickly enough",
              "Progress is not measured often enough"],
             0,
             "The speaker names and then rejects the common explanation "
             "before giving their own. Catching only the first sentence gets "
             "this wrong."),
            ("What does the speaker recommend?",
             ["Doing the riskiest work first",
              "Adding more time to the plan",
              "Starting with work that shows visible progress",
              "Reviewing the schedule more frequently"],
             0,
             "The last sentence. The third option is what the speaker "
             "describes as the mistake."),
            ("What does the speaker mean by 'time to be wrong about it'?",
             ["Time to recover if the risky work goes badly",
              "Time to change the estimate before it is agreed",
              "Time to ask someone else to do it",
              "Time to prove the work was not needed"],
             0,
             "Inference. Nothing in the passage states this directly; it "
             "follows from the argument."),
        ],
    ),
    (
        "Two colleagues on a delivery date", "conversation", 45, 1, 0.2,
        "— Are we still saying the fifteenth for the client demo? "
        "— That is what is written down, but the data import is not finished. "
        "— How much is left? "
        "— Two days of work, maybe three if the file formats surprise us. "
        "— So the fifteenth is possible. "
        "— It is possible. It is not safe. If anything at all goes wrong we "
        "have nothing to show, and I would rather move it by a week than "
        "demo something that falls over in front of them.",
        [
            ("What is the second speaker's position?",
             ["The date is achievable but too risky",
              "The date cannot be met under any circumstances",
              "The date is comfortable if nothing goes wrong",
              "The demo should be cancelled entirely"],
             0,
             "'It is possible. It is not safe.' The distinction is the whole "
             "point of the exchange."),
            ("How much work remains on the data import?",
             ["Two to three days", "Two days exactly",
              "About a week", "Fifteen days"],
             0,
             "The range matters -- 'three if the file formats surprise us'."),
            ("What would the second speaker prefer to do?",
             ["Delay the demo by a week",
              "Demo whatever is ready on the fifteenth",
              "Ask the client to choose the date",
              "Split the demo across two sessions"],
             0,
             "Stated at the end, as a preference rather than a decision."),
        ],
    ),
    (
        "Campus placement briefing", "announcement", 50, 1, 0.1,
        "A quick note for final-year students. The pre-placement talk on "
        "Monday is not optional if you intend to sit the test on Tuesday. "
        "Attendance is taken at the talk and the test list is drawn from it. "
        "Bring your college ID to both. The test is ninety minutes, and there "
        "is no negative marking, so leave nothing blank. Results go out by "
        "email on Wednesday evening, and shortlisted students interview on "
        "Thursday.",
        [
            ("Why must students attend Monday's talk?",
             ["The test list is taken from the attendance record",
              "The syllabus is only explained there",
              "Their ID cards are issued at the talk",
              "It is the only way to register by email"],
             0,
             "The consequence is spelled out: attendance feeds the test list."),
            ("What advice is given about the test itself?",
             ["Answer every question, as there is no negative marking",
              "Attempt only the questions you are sure of",
              "Spend ninety minutes checking your answers",
              "Leave the difficult sections until Wednesday"],
             0,
             "The reasoning and the advice are in the same sentence."),
            ("A student is shortlisted. When do they interview?",
             ["Thursday", "Wednesday evening", "Tuesday", "Monday"],
             0,
             "Requires holding the whole sequence: talk Monday, test Tuesday, "
             "results Wednesday, interviews Thursday. Every wrong option is a "
             "real date from the passage."),
        ],
    ),
]


def rotated(question_index: int, options: list[str],
            correct: int) -> tuple[list[str], int]:
    """Move the correct answer off index 0, the same way every time.

    Deterministic in the question's position rather than random: a reseed must
    not renumber the options underneath a student who has already answered,
    and a test asserting the distribution must not be flaky.
    """
    shift = question_index % len(options)
    if shift == 0:
        return list(options), correct
    rolled = options[-shift:] + options[:-shift]
    return rolled, (correct + shift) % len(options)


def flat_questions() -> list[tuple]:
    """Every question in the bank, with its rotation already applied.

    One numbering across the whole bank, so consecutive questions inside a
    passage do not all land on the same rotation.
    """
    out: list[tuple] = []
    n = 0
    for passage in PASSAGES:
        for stem, options, correct, explanation in passage[6]:
            rolled, index = rotated(n, list(options), correct)
            out.append((passage[0], stem, rolled, index, explanation))
            n += 1
    return out

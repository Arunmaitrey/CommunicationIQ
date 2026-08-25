"""Spoken answers to something heard: conversations and passages.

Two task types, one shape. Both play something once and then ask a question
the candidate answers out loud, and both are scored on what was understood as
well as on how it was said.

    conversation_question   two people talking, then a question about it
    passage_question        a short talk or announcement, then a question

They are deliberately *not* the multiple-choice listening module wearing a
microphone. Choosing the right option from four shows recognition; saying what
happened in your own words shows comprehension you can act on, and it is what
a real telephonic round asks for. The two measure different things and both
belong in a four-skill test.

**Why these are TaskItems rather than a new table.** ``reference_text`` holds
everything that is spoken -- the exchange and the question -- and ``rubric``
holds the points a competent answer covers. That is exactly the shape Story
Retell and Short Answer already use, so the existing content-relevance scorer
marks these unchanged. A fourth table would have been a near-duplicate of
TaskItem with a different name.

**Why the key is ``key_points``.** That is the name the content-relevance
contract reads. A synonym -- "points" -- parses fine, matches nothing, and
produces a silent zero-coverage score rather than an error.

**Why the rubric points are cues, not phrases.** The same lesson the writing
bank learned: a point is a thing to say, and a candidate says it in their own
words. Matching the author's vocabulary would mark a correct answer wrong.

All original (CONTENT-04). Workplace throughout.
"""
from __future__ import annotations

# (task_type, spoken_text, {rubric}, difficulty)
#
# `spoken_text` is played once and never shown. It carries the stimulus and
# the question together, because that is the order a candidate hears them and
# splitting them would need two plays.
#
# **No framing sentence.** Every item used to open "Listen to two colleagues,
# then answer the question." -- and the duplicate detector was right to
# object: four items sharing a forty-character opening are indistinguishable
# to it, so a genuine duplicate among them would pass unnoticed. The framing
# is an instruction and belongs on the section, which already has an
# `instructions` field and shows it before the items. Removing it also makes
# every play shorter and starts each one on its actual content.
ITEMS: list[tuple[str, str, dict, float]] = [
    # -- conversations -----------------------------------------------------
    (
        "conversation_question",
        "— Did the client agree to the new date? "
        "— They agreed to it, but they want the first draft a week earlier "
        "in exchange. "
        "— That is tighter than before. "
        "— It is. I said we would confirm by Friday rather than agree on the "
        "call. "
        "Question: What did the second speaker actually commit to?",
        {"key_points": ["confirming by Friday, not agreeing",
                    "the client wants an earlier first draft",
                    "nothing was finally agreed on the call"],
         "prompt": "What did the second speaker commit to?"},
        -0.1,
    ),
    (
        "conversation_question",
        "— The build has been failing since this morning. "
        "— Is it the tests or the deploy step? "
        "— The tests pass locally. It only fails on the shared runner. "
        "— Then it is probably the environment, not the code. "
        "Question: Why does the second speaker think it is not the code?",
        {"key_points": ["the tests pass locally",
                    "it only fails on the shared runner",
                    "that points to the environment"],
         "prompt": "Why is it probably not the code?"},
        0.1,
    ),
    (
        "conversation_question",
        "— Can you take the client call at four? "
        "— I can, but I have not seen the latest numbers. "
        "— They were sent last night. "
        "— Then send them again, because I did not get them, and I would "
        "rather say that now than guess on the call. "
        "Question: What is the second speaker asking for, and why?",
        {"key_points": ["the numbers sent again",
                    "they did not receive them",
                    "so they do not have to guess on the call"],
         "prompt": "What are they asking for and why?"},
        0.2,
    ),
    (
        "conversation_question",
        "— Everyone is saying the release slipped because of testing. "
        "— That is not quite fair. Testing found the problem. The problem "
        "was there before testing looked at it. "
        "Question: What point is the second speaker making?",
        {"key_points": ["testing did not cause the delay",
                    "testing found an existing problem",
                    "the fault was there beforehand"],
         "prompt": "What point is being made?"},
        0.4,
    ),
    # -- passages ----------------------------------------------------------
    (
        "passage_question",
        "From Monday, the support desk moves to a single queue. Calls and "
        "emails will be answered in the order they arrive rather than by "
        "channel. The team is not getting larger, so the aim is a fairer "
        "wait rather than a shorter one. "
        "Question: What will change for customers, and what will not?",
        {"key_points": ["one queue instead of separate channels",
                    "answered in order of arrival",
                    "waits are fairer, not shorter",
                    "the team is not growing"],
         "prompt": "What changes and what does not?"},
        0.1,
    ),
    (
        "passage_question",
        "Most status reports say what was done. The useful ones say what "
        "changed. If nothing moved this week, the report should say so in one "
        "line rather than list activity that led nowhere, because a reader "
        "who cannot tell the difference stops reading them at all. "
        "Question: What does the speaker say a good status report should do?",
        {"key_points": ["say what changed rather than what was done",
                    "admit plainly when nothing moved",
                    "avoid listing activity that led nowhere"],
         "prompt": "What should a good status report do?"},
        0.3,
    ),
    (
        "passage_question",
        "This is Priya from accounts. Your expense claim from March has been "
        "held because the receipt for the hotel is missing, not because the "
        "amount is wrong. Send the receipt and it will go through in the next "
        "run. If you cannot find it, call me and we will do a declaration "
        "instead. "
        "Question: Why was the claim held, and what are the two ways forward?",
        {"key_points": ["the hotel receipt is missing",
                    "the amount itself is not in question",
                    "send the receipt",
                    "or call and make a declaration"],
         "prompt": "Why was it held and what can be done?"},
        0.2,
    ),
    (
        "passage_question",
        "The office will be closed on Friday for maintenance. Anyone who "
        "needs building access that day should request it by Wednesday. "
        "Remote work does not need approval, but the usual core hours still "
        "apply. "
        "Question: What does somebody need to do if they want to come in on "
        "Friday?",
        {"key_points": ["request building access",
                    "by Wednesday",
                    "remote work needs no approval",
                    "core hours still apply"],
         "prompt": "What is needed to come in on Friday?"},
        -0.2,
    ),
    # -- conversations, second release ------------------------------------
    #
    # Added when the company rounds began drawing three conversations each:
    # a four-item pool meant every candidate met nearly the same three, and
    # three formats shared them besides. Same shape, same rubric contract.
    (
        "conversation_question",
        "— The customer says the invoice total does not match the quote. "
        "— Is the difference the delivery charge? "
        "— Partly, but there is also a line for installation they say they "
        "never asked for. "
        "— Then remove the installation line and send a corrected invoice "
        "with a short apology. "
        "Question: What did the second speaker decide to do?",
        {"key_points": ["remove the installation charge",
                    "send a corrected invoice",
                    "include an apology"],
         "prompt": "What will be done about the invoice?"},
        0.0,
    ),
    (
        "conversation_question",
        "— We are short one person for the Saturday shift. "
        "— Did you ask Priya? She offered to swap last week. "
        "— She is travelling. I would rather not force anyone on a weekend. "
        "— Then post it as an open shift with the overtime rate and see who "
        "takes it. "
        "Question: What solution does the second speaker suggest, and why?",
        {"key_points": ["post it as an open shift",
                    "offer the overtime rate",
                    "so nobody is forced to work the weekend"],
         "prompt": "What is the suggested solution?"},
        0.2,
    ),
    (
        "conversation_question",
        "— The demo laptop will not connect to the projector in room two. "
        "— Did you try the adapter from the front desk? "
        "— Yes, and a different cable. The screen just flickers. "
        "— Then move the demo to room five and put a notice on room two's "
        "door so nobody walks into an empty room. "
        "Question: What two things did the second speaker ask for?",
        {"key_points": ["move the demo to room five",
                    "put a notice on room two's door",
                    "so nobody goes to the wrong room"],
         "prompt": "What two things should be done?"},
        0.0,
    ),
    (
        "conversation_question",
        "— Head office wants the monthly report a day early this time. "
        "— The sales figures only close on the last evening. "
        "— I know. Send everything else on time and follow up with the sales "
        "page the next morning, clearly marked as the late addition. "
        "Question: How will the early deadline be handled?",
        {"key_points": ["send the rest of the report early",
                    "sales figures follow the next morning",
                    "the late page is clearly marked"],
         "prompt": "How is the early deadline being handled?"},
        0.3,
    ),
    (
        "conversation_question",
        "— A candidate has asked to move tomorrow's interview to the "
        "afternoon. "
        "— The panel is only free in the morning. "
        "— Then offer them the first morning slot, and if that fails, "
        "reschedule to Thursday rather than change the panel. "
        "Question: What options were decided for the candidate?",
        {"key_points": ["offer the first morning slot",
                    "otherwise reschedule to Thursday",
                    "the panel is not being changed"],
         "prompt": "What options will the candidate get?"},
        0.1,
    ),
    (
        "conversation_question",
        "— The new starter has no login yet and it is day two. "
        "— IT says the request was never raised. "
        "— Raise it now marked urgent, and lend them the training-room "
        "machine so they are not sitting idle while it goes through. "
        "Question: What is the immediate plan for the new starter?",
        {"key_points": ["raise the request marked urgent",
                    "lend the training-room machine",
                    "so they can work while waiting"],
         "prompt": "What happens while the login is sorted out?"},
        -0.1,
    ),
]

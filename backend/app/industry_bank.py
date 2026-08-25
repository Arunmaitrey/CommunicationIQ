"""Industry-specific speaking items, for rounds that want the job's own words.

The rest of the bank is deliberately general — "the training session begins at
nine" is true in a bank, a hospital and a call centre, and general material is
what makes a broad test possible. But a candidate being screened for a
banking back-office will be asked about reconciliations, and one going into
BPO will be asked to hold a customer's temper. Sentences from the actual job
are harder in a way that generic ones are not, and that difference is what an
industry filter exists to reach.

Small on purpose. Five read-aloud sentences and four short answers per
vertical is enough for the filter to change what a section serves without
pretending to a depth nobody has authored. General material stays eligible
under every industry filter (see ``selection.matches``), so a filtered section
draws these *and* the general bank rather than these alone — which is what
keeps a banking round from being a five-item test.

All original (CONTENT-04). Indian workplace English throughout.
"""
from __future__ import annotations

# (industry, role, topic, sentence, difficulty)
READ_ALOUD: list[tuple[str, str, str, str, float]] = [
    # -- BPO ---------------------------------------------------------------
    ("bpo", "customer support", "escalation",
     "I understand the delay has cost you time, and I will stay on the line "
     "until it is sorted.", 0.5),
    ("bpo", "customer support", "escalation",
     "Let me check that against your account and come back to you in under a "
     "minute.", 0.2),
    ("bpo", "customer support", "verification",
     "Before we go further, could you confirm the registered mobile number "
     "on the account?", 0.0),
    ("bpo", "customer support", "handover",
     "I am transferring you to the billing team, and I will brief them so you "
     "do not have to repeat this.", 0.4),
    ("bpo", "customer support", "closing",
     "Is there anything else I can help with while I still have the file "
     "open?", -0.2),

    # -- IT ----------------------------------------------------------------
    ("it", "developer", "incident",
     "The service was returning errors for about forty minutes, and the cause "
     "was a change we deployed that morning.", 0.6),
    ("it", "developer", "standup",
     "I finished the migration script yesterday and I am blocked on access to "
     "the staging database.", 0.3),
    ("it", "developer", "review",
     "The logic is right, but the function reads the same configuration three "
     "times and that is worth tidying.", 0.7),
    ("it", "developer", "estimation",
     "Two days if the interface is already agreed, and closer to a week if it "
     "is not.", 0.1),
    ("it", "developer", "handover",
     "The tests cover the happy path and one failure case; the retry logic is "
     "not covered yet.", 0.5),

    # -- Banking -----------------------------------------------------------
    ("banking", "operations", "reconciliation",
     "The account did not reconcile because two entries were posted on the "
     "same reference number.", 0.7),
    ("banking", "operations", "compliance",
     "We cannot process the request until the address proof is countersigned "
     "and dated.", 0.4),
    ("banking", "relationship", "customer",
     "The interest is calculated on the daily closing balance, not on the "
     "month-end figure.", 0.5),
    ("banking", "operations", "escalation",
     "The transaction has been marked for review, which usually adds one "
     "working day.", 0.2),
    ("banking", "relationship", "customer",
     "You can close the account today, but the standing instruction has to be "
     "cancelled first.", 0.3),
]

# (industry, role, topic, question, [accepted answers], difficulty)
SHORT_ANSWERS: list[tuple[str, str, str, str, list[str], float]] = [
    ("bpo", "customer support", "escalation",
     "A caller is angry about a delay that was not your fault. What is the "
     "first thing you say?",
     ["apologise", "sorry", "acknowledge", "understand"], 0.2),
    ("bpo", "customer support", "verification",
     "What do you check before discussing an account with a caller?",
     ["identity", "verification", "details", "number"], -0.1),
    ("bpo", "customer support", "metrics",
     "What is the name for the time a caller waits before anyone answers?",
     ["wait time", "hold time", "queue time", "waiting"], 0.4),
    ("bpo", "customer support", "closing",
     "What should you confirm before ending a call?",
     ["resolved", "anything else", "satisfied", "helped"], 0.0),

    ("it", "developer", "incident",
     "What do you look at first when a service starts failing after a "
     "release?",
     ["logs", "the change", "deploy", "what changed", "rollback"], 0.3),
    ("it", "developer", "version control",
     "What do you call a request to merge your changes into the main branch?",
     ["pull request", "merge request", "pr"], -0.2),
    ("it", "developer", "testing",
     "What kind of test checks one function in isolation?",
     ["unit test", "unit"], -0.3),
    ("it", "developer", "standup",
     "What three things does a daily standup usually cover?",
     ["yesterday today blockers", "blockers", "progress"], 0.5),

    ("banking", "operations", "reconciliation",
     "What does it mean when an account does not reconcile?",
     ["mismatch", "does not match", "difference", "not balanced"], 0.5),
    ("banking", "operations", "compliance",
     "What is the usual name for the checks done before opening an account?",
     ["kyc", "know your customer", "verification"], 0.1),
    ("banking", "relationship", "customer",
     "What is the difference between a debit and a credit to an account?",
     ["out and in", "money out", "money in", "withdrawal deposit"], 0.4),
    ("banking", "operations", "escalation",
     "Who do you refer a suspicious transaction to?",
     ["compliance", "supervisor", "manager", "aml"], 0.3),
]

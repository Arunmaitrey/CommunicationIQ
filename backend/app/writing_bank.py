"""Things to write, and what a competent answer has to contain.

All original (CONTENT-04). These are the tasks a campus placement round or a
first job actually sets — reply to an awkward email, report a delay, escalate
without being rude, summarise for someone who was not there — rather than the
abstract "discuss both views" essay, an academic-exam shape and not what most
of these students are being hired to do.

Each prompt carries ``key_points``: the things an author decided a competent
answer must address. Task response is scored against that written-down rubric
rather than against a model's opinion, so a trainer can look at the score and
check it.

Each point also carries ``cues``, and that detail is load-bearing. A point is
an *instruction to the writer* — "give the new date" — and a competent answer
does not contain those words; it says "by Tuesday". Matching the rubric's own
vocabulary against the text marked a genuinely complete reply as covering one
point of four, which is worse than not scoring it at all, because it tells a
student their good answer was bad. The cues are what actually indicates the
point was addressed, and any one of them counts.

The hard part of every one of these is the same: a real constraint that makes
the polite answer and the honest answer pull in different directions. That is
what workplace writing is, and it is what a keyword-matching answer misses.
"""
from __future__ import annotations

# (title, kind, difficulty, min_words, minutes, scenario, prompt, key_points)
PROMPTS: list[tuple] = [
    (
        "Reply about a missed deadline", "email", -0.2, 120, 15,
        "You agreed to send a client their monthly report by Friday. It is "
        "now Friday afternoon and two of the figures are wrong — you found "
        "the error yourself. Fixing it properly needs until Tuesday. Nobody "
        "has noticed yet.",
        "Write the email you would send the client now.",
        [
            {"point": "say clearly that the report will be late",
             "cues": ["will be late", "is late", "delay", "delayed",
                      "not be ready", "will not be ready", "behind schedule",
                      "miss the deadline", "later than"]},
            {"point": "give the new date",
             "cues": ["tuesday", "monday", "next week", "by the", "on the",
                      "within", "no later than"]},
            {"point": "explain what went wrong",
             "cues": ["figures", "error", "mistake", "wrong", "incorrect",
                      "import", "data", "numbers", "fault", "issue"]},
            {"point": "say what you are doing to fix it",
             "cues": ["correct", "fixing", "fix", "checking", "recheck",
                      "verify", "review", "put right", "paused", "check"]},
        ],
    ),
    (
        "Escalate without blaming", "email", 0.2, 150, 20,
        "You have asked another team three times over two weeks for access to "
        "a test database. Each time they have said they will look at it. You "
        "are now blocked and your own deadline is in four days. You have to "
        "copy in your manager, and you will keep working with this team "
        "afterwards.",
        "Write the email, copying your manager for the first time.",
        [
            {"point": "state what you need and by when",
             "cues": ["access", "database", "need", "require", "request",
                      "four days", "this week", "deadline", "by "]},
            {"point": "set out what you have already tried",
             "cues": ["three times", "twice", "asked", "requested",
                      "followed up", "chased", "two weeks", "previously",
                      "earlier", "since"]},
            {"point": "explain the consequence of further delay",
             "cues": ["blocked", "cannot proceed", "at risk", "will slip",
                      "miss", "impact", "consequence", "hold up", "unable to",
                      "stalled"]},
            {"point": "keep the tone workable for the future",
             "cues": ["appreciate", "understand", "thanks", "thank you",
                      "happy to", "grateful", "realise", "aware", "busy",
                      "know you"]},
        ],
    ),
    (
        "Report a week that went badly", "report", 0.3, 180, 25,
        "Of eight tasks planned this week, three are finished, two are "
        "blocked waiting on someone else, and three were not started because "
        "you spent two days on an unplanned production problem. The "
        "production problem is fixed.",
        "Write your weekly status update for your team lead.",
        [
            {"point": "say what was completed",
             "cues": ["completed", "finished", "done", "delivered", "closed",
                      "three", "shipped"]},
            {"point": "explain what is blocked and on whom",
             "cues": ["blocked", "waiting", "depends", "dependency", "pending",
                      "held up", "another team", "someone else"]},
            {"point": "account for the unplanned work",
             "cues": ["production", "unplanned", "incident", "two days",
                      "urgent", "outage", "interrupt", "unexpected"]},
            {"point": "say what you will do next week",
             "cues": ["next week", "plan to", "will start", "intend",
                      "priority", "going forward", "monday", "then"]},
        ],
    ),
    (
        "Summarise a meeting for someone absent", "summary", 0.0, 140, 15,
        "In a forty-minute meeting the team agreed to postpone the mobile "
        "release by two weeks, chose to fix accessibility issues before "
        "adding the new dashboard, and could not agree who owns the migration "
        "script — that decision was deferred to next week. A colleague on "
        "leave needs to know what happened.",
        "Write the summary you would send them.",
        [
            {"point": "give the decisions that were made",
             "cues": ["postpone", "delayed", "two weeks", "accessibility",
                      "before", "agreed", "decided", "release"]},
            {"point": "identify what was not decided",
             "cues": ["not agree", "could not", "deferred", "unresolved",
                      "still open", "no decision", "undecided", "migration",
                      "next week"]},
            {"point": "say what happens next and when",
             "cues": ["next week", "will be", "follow up", "revisit",
                      "meeting", "then", "afterwards"]},
            {"point": "make clear what affects the reader",
             "cues": ["you", "your", "affects", "means", "worth knowing",
                      "relevant"]},
        ],
    ),
    (
        "Ask for something you were refused", "email", 0.4, 160, 20,
        "You asked to attend a three-day conference and your manager said no, "
        "citing cost. You still think it is worth it: two of your team's "
        "current problems are the conference's main topics, and a colleague "
        "at another company has offered to share a room, halving the cost.",
        "Write the email making the case again.",
        [
            {"point": "acknowledge the reason you were given",
             "cues": ["cost", "expense", "budget", "understand", "appreciate",
                      "you said", "you mentioned", "aware"]},
            {"point": "present the new information",
             "cues": ["share a room", "sharing", "half", "halve", "cheaper",
                      "reduce", "lower", "colleague", "offered"]},
            {"point": "connect it to work the team is doing",
             "cues": ["our", "team", "problem", "currently", "working on",
                      "relevant", "topics", "directly", "we are"]},
            {"point": "make it easy to say yes or no",
             "cues": ["let me know", "happy to", "if not", "either way",
                      "no problem", "decide", "your call", "understand if"]},
        ],
    ),
    (
        "Explain a technical problem to a non-technical reader", "email", 0.5,
        170, 25,
        "The company's payment page has been slow for a week. The cause is "
        "that every page load fetches the full product catalogue rather than "
        "the one item being bought. Fixing it takes about two days. The head "
        "of sales, who is not technical, has asked what is going on.",
        "Write the reply.",
        [
            {"point": "explain the cause in plain language",
             "cues": ["every time", "loads", "whole", "entire", "all the",
                      "catalogue", "catalog", "instead of", "rather than",
                      "one item"]},
            {"point": "say what the effect on customers is",
             "cues": ["slow", "waiting", "customers", "abandon", "leave",
                      "frustrat", "checkout", "experience", "seconds"]},
            {"point": "give a timescale for the fix",
             "cues": ["two days", "2 days", "this week", "wednesday",
                      "thursday", "friday", "shortly", "expect", "by "]},
            {"point": "avoid jargon without being condescending",
             "cues": ["think of it", "in other words", "put simply",
                      "effectively", "essentially", "imagine", "the reason",
                      "which means"]},
        ],
    ),
]

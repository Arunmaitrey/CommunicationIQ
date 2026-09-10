"""Populate the sentence_completion and voice_change quiz categories.

SVAR and SpeechX both have five sections -- Verb Forms, Tenses, Articles,
Prepositions, Change the Voice -- that select on
``QuizItem.category in {"sentence_completion", "voice_change"}`` with a
``topic`` tag (selection.py's ``topics`` filter matches item.topic). Neither
category had a single row in the database: `completion_bank.py` and
`voice_change_bank.py` hold real, hand-authored content for exactly this,
but nothing ever inserted it. The result was two tests silently running at
half their designed scope -- reading/listening/speaking worked, every
grammar-round section came back "no answers were given in this section" for
every student, forever.

`completion_bank.ITEMS` carries a free-text "what it tests" label, not one
of the four topics these sections filter on, so this file classifies each
existing item by its actual grammatical focus and adds the items neither
bank had at all -- there was no "articles" content anywhere, and verb_forms
and tenses were both short of a full section's worth.

    python -m app.seed_grammar_sections
"""
from __future__ import annotations

import asyncio

# (sentence with ___, accepted answers, topic)
# Existing completion_bank.py items, reclassified by grammatical focus
# rather than by their original free-text label.
_EXISTING_BY_INDEX_TOPIC = {
    4: "tenses",           # "since March" -- present perfect trigger
    5: "tenses",           # "for three weeks" -- present perfect trigger
    7: "prepositions",     # "by/before the end of the month"
    9: "verb_forms",       # unreal conditional ("had")
    10: "prepositions",    # "responsible for"
    11: "prepositions",    # "apologised for"
    12: "verb_forms",      # verb complement ("agreed to")
    13: "verb_forms",      # subject-verb agreement ("each ... has")
    14: "verb_forms",      # past passive form ("were checked")
    15: "prepositions",    # fixed phrase ("look forward to")
    16: "prepositions",    # fixed phrase ("point in")
    17: "verb_forms",      # verb complement ("asked us to")
    18: "prepositions",    # time preposition ("by/before")
    19: "tenses",          # "since 2019"
    20: "tenses",          # time clause sequencing
    21: "prepositions",    # "responsible for"
    22: "prepositions",    # "depends on/upon"
    24: "prepositions",    # "applies to"
}

NEW_VERB_FORMS = [
    ("The finance team ___ the invoice before it reaches the client.",
     {"reviews", "checks"}),
    ("By the time you arrive, the meeting ___ already started.",
     {"will have"}),
    ("She suggested ___ the release until Monday.",
     {"postponing", "delaying"}),
    ("If the server ___ down again, escalate to on-call immediately.",
     {"goes"}),
    ("The document needs ___ before it goes out.",
     {"reviewing", "checking"}),
]

NEW_TENSES = [
    ("We ___ this exact issue twice before, so the fix should be quick.",
     {"have seen", "have had"}),
    ("She ___ for the company for six years before she moved to management.",
     {"had worked"}),
    ("By next quarter, the team ___ the migration.",
     {"will have finished", "will have completed"}),
    ("At this time tomorrow, the client ___ the new dashboard.",
     {"will be reviewing"}),
    ("He ___ the report when the call came in.",
     {"was writing", "was drafting"}),
    ("We ___ the vendor twice this week already.",
     {"have contacted", "have called"}),
]

NEW_ARTICLES = [
    ("Please send ___ updated invoice to the client by Friday.",
     {"an"}),
    ("___ manager you spoke to yesterday has already left the company.",
     {"the"}),
    ("She is ___ engineer on the platform team.",
     {"an"}),
    ("We need ___ new laptop for the intern starting Monday.",
     {"a"}),
    ("___ feedback from the client was mostly positive.",
     {"the"}),
    ("He gave ___ honest answer about the delay.",
     {"an"}),
    ("___ project is behind schedule by two weeks.",
     {"the"}),
    ("This is ___ unusual request for a Friday afternoon.",
     {"an"}),
]

# Items whose real focus is a connector/conjunction rather than one of the
# four topics these sections need -- still real, still worth keeping, just
# not selected by SVAR/SpeechX today.
OTHER_TOPIC = "conjunctions"


async def main() -> None:
    from app import completion_bank, voice_change_bank
    from app.db import init_mongo
    from app.models.tenant import QuizItem

    await init_mongo()

    existing_sentence_completion = await QuizItem.find(
        QuizItem.category == "sentence_completion").count()
    existing_voice_change = await QuizItem.find(
        QuizItem.category == "voice_change").count()
    if existing_sentence_completion or existing_voice_change:
        print(f"already seeded: {existing_sentence_completion} sentence_completion, "
              f"{existing_voice_change} voice_change -- nothing to do")
        return

    created = 0
    for i, (stem, accepted, _label) in enumerate(completion_bank.ITEMS):
        topic = _EXISTING_BY_INDEX_TOPIC.get(i, OTHER_TOPIC)
        await QuizItem(
            category="sentence_completion", stem=stem,
            options=sorted(accepted), correct_index=0,
            topic=topic, status="published",
        ).insert()
        created += 1

    for group, topic in ((NEW_VERB_FORMS, "verb_forms"),
                         (NEW_TENSES, "tenses"),
                         (NEW_ARTICLES, "articles")):
        for stem, accepted in group:
            await QuizItem(
                category="sentence_completion", stem=stem,
                options=sorted(accepted), correct_index=0,
                topic=topic, status="published",
            ).insert()
            created += 1

    for stem, options, correct_index, explanation in voice_change_bank.ITEMS:
        await QuizItem(
            category="voice_change", stem=stem, options=options,
            correct_index=correct_index, explanation=explanation,
            status="published",
        ).insert()
        created += 1

    print(f"created {created} quiz items "
          f"({len(completion_bank.ITEMS) + len(NEW_VERB_FORMS) + len(NEW_TENSES) + len(NEW_ARTICLES)} "
          f"sentence_completion, {len(voice_change_bank.ITEMS)} voice_change)")


if __name__ == "__main__":
    asyncio.run(main())

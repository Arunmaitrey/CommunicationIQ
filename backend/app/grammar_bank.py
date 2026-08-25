"""Section C grammar bank for the SVAR-style four-section assessment.

Shape follows the observed reference (third-party walkthrough, Section C
instruction screen and items 1/34 and 29/34): five categories, a typed blank
with the candidate's choices shown in brackets, and a Voice Change part that
is answered by choosing a rewrite. Counts per category are the reference's:

    Verb Forms 8 · Tenses 8 · Articles 6 · Prepositions 6 · Voice Change 6

Only the *shape* is the reference's. Every sentence here is ours: the
walkthrough shows two items, and copying a proprietary bank would be wrong
even if it were visible. Each item has exactly one correct choice among the
bracketed options, so a score means "chose the right form", not "guessed one
of several".

Stored as sentence-completion QuizItems with ``topic`` set to the category,
so a section can draw "8 verb forms" rather than "8 of anything". The older
connector items (because/although/...) keep working for every other format
and are tagged ``connectors`` so they never leak into these categories.
"""
from __future__ import annotations

VERB_FORMS = "verb_forms"
TENSES = "tenses"
ARTICLES = "articles"
PREPOSITIONS = "prepositions"

# The reference order, 1-28. Voice Change (29-34) lives in voice_change_bank.
CATEGORY_ORDER: tuple[tuple[str, int], ...] = (
    (VERB_FORMS, 8), (TENSES, 8), (ARTICLES, 6), (PREPOSITIONS, 6),
)

# (stem with ___ and the choices in brackets, {accepted}, category)
ITEMS: list[tuple[str, set[str], str]] = [
    # -- Verb Forms: the right form of the verb in brackets ---------------
    ("The train ___ (leave/leaves) the station at 9:00 AM.", {"leaves"}, VERB_FORMS),
    ("Every employee ___ (need/needs) to submit the timesheet by Friday.", {"needs"}, VERB_FORMS),
    ("The manager asked us ___ (to finish/finishing) the report before lunch.", {"to finish"}, VERB_FORMS),
    ("She enjoys ___ (to work/working) with new clients.", {"working"}, VERB_FORMS),
    ("The files ___ (was/were) uploaded to the shared drive last night.", {"were"}, VERB_FORMS),
    ("Neither of the printers ___ (work/works) at the moment.", {"works"}, VERB_FORMS),
    ("Our team ___ (meet/meets) every Monday morning.", {"meets"}, VERB_FORMS),
    ("Please let me ___ (know/to know) if the invoice is wrong.", {"know"}, VERB_FORMS),
    # -- Tenses: the right tense for the time reference ---------------------
    ("She ___ (has worked/worked) here since 2021.", {"has worked"}, TENSES),
    ("By the time the client arrived, we ___ (had finished/finished) the setup.", {"had finished"}, TENSES),
    ("I ___ (will call/call) you as soon as the results are in.", {"will call"}, TENSES),
    ("They ___ (were testing/tested) the software when the power went off.", {"were testing"}, TENSES),
    ("He ___ (has sent/sent) the proposal yesterday.", {"sent"}, TENSES),
    ("I ___ (have been waiting/am waiting) for the approval for three weeks.", {"have been waiting"}, TENSES),
    ("When I joined the company, I ___ (did not know/have not known) anyone.", {"did not know"}, TENSES),
    ("The daily stand-up ___ (starts/is starting) at 10 a.m. every day.", {"starts"}, TENSES),
    # -- Articles -----------------------------------------------------------
    ("She is ___ (a/an) engineer at the Hyderabad office.", {"an"}, ARTICLES),
    ("Please send me ___ (a/the) report you presented yesterday.", {"the"}, ARTICLES),
    ("He bought ___ (a/an) new laptop for the project.", {"a"}, ARTICLES),
    ("___ (A/The) sun rises in the east.", {"the"}, ARTICLES),
    ("It took ___ (a/an) hour to fix the bug.", {"an"}, ARTICLES),
    ("We need ___ (a/the) volunteer for the demo; anyone will do.", {"a"}, ARTICLES),
    # -- Prepositions -------------------------------------------------------
    ("The review meeting is ___ (on/in) Monday.", {"on"}, PREPOSITIONS),
    ("The report is due ___ (on/by) 5 p.m. today.", {"by"}, PREPOSITIONS),
    ("He is good ___ (at/in) solving problems under pressure.", {"at"}, PREPOSITIONS),
    ("The file is saved ___ (in/on) the shared folder.", {"in"}, PREPOSITIONS),
    ("The office opens ___ (at/on) nine o'clock.", {"at"}, PREPOSITIONS),
    ("She is responsible ___ (for/of) the client accounts.", {"for"}, PREPOSITIONS),
]

# The older bank's category. Kept distinct so a "verb forms" draw can never
# be filled with a conjunction item.
LEGACY_TOPIC = "connectors"


def choices_in(stem: str) -> list[str]:
    """The bracketed choices of a stem: "(leave/leaves)" -> ["leave", "leaves"]."""
    start, end = stem.find("("), stem.find(")")
    if start < 0 or end < start:
        return []
    return [c.strip() for c in stem[start + 1:end].split("/") if c.strip()]

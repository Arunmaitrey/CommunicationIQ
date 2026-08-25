"""Writing: five measures, and the ways they could quietly be wrong.

The failure mode that matters here is not a crash. It is a scorer that looks
authoritative and rewards the wrong thing — length over substance, or the
rubric's own vocabulary over the student's. Both happened during development
and both are pinned below.
"""
from __future__ import annotations

import pytest

from app import writing as scorer
from app.writing_bank import PROMPTS

from tests.test_game_and_practice import auth, login

STRONG = """Dear Ms Rao,

I am writing about the monthly report that was due today. It will be late,
and I want to tell you now rather than send you something wrong.

While checking the figures this afternoon I found errors in two of them. The
cause was a data import that pulled last month's values into two columns.
I would rather correct it properly than patch the numbers, because a report
you cannot trust is worse than one that arrives late.

I will send the corrected version by Tuesday. In the meantime I have paused
the import so the same fault cannot affect next month.

I am sorry for the delay. Please tell me if Tuesday causes a problem."""

# Over the word minimum and empty. The measure of a scorer is whether it can
# tell this from the real thing.
PADDING = """i am writing this email to you today about the thing that we
discussed and which is important for us and for you also. it is a matter of
some importance and i wanted to bring it to your attention at the earliest
possible time so that you are aware of the situation as it stands at this
moment in time. i hope this email finds you well and that everything is going
well for you and your team also. please let me know if you have any questions
about anything at all and i will be happy to answer them for you as soon as i
possibly can. thank you very much for your time and your patience."""


# -- the bank --------------------------------------------------------------

def test_every_rubric_point_carries_cues():
    """Without cues, task response marks good answers down.

    A point is an instruction to the writer -- "give the new date" -- and a
    competent answer says "by Tuesday" instead. Matching the rubric's own
    words scored a complete reply as 1 of 4, which is worse than no score:
    it tells a student their good answer was bad.
    """
    for (title, _kind, _difficulty, _min_words, _minutes,
         _scenario, _prompt, points) in PROMPTS:
        assert points, title
        for point in points:
            assert isinstance(point, dict), f"{title}: {point!r} has no cues"
            assert point.get("point"), title
            assert point.get("cues"), f"{title}: '{point['point']}' has no cues"


def test_prompts_ask_for_enough_writing_to_judge():
    for (title, _k, _d, min_words, _m, _s, _p, _pts) in PROMPTS:
        assert min_words >= scorer.MIN_WORDS_TO_SCORE, title


# -- the scorer ------------------------------------------------------------

async def test_padding_does_not_beat_substance():
    """The headline property. Length must not stand in for content."""
    points = PROMPTS[0][7]
    strong = await scorer.score_essay(STRONG, key_points=points, min_words=120)
    padded = await scorer.score_essay(PADDING, key_points=points, min_words=120)

    # The padded piece is about as long as the real one -- that is the point
    # of it. The exact count is incidental and asserting it exactly made this
    # test about my sample rather than about the scorer.
    assert padded.word_count >= 110
    assert strong.overall is not None and padded.overall is not None
    assert strong.overall > padded.overall + 15, (
        f"strong {strong.overall} vs padded {padded.overall}: the scorer "
        f"cannot tell substance from volume")


async def test_a_good_answer_scores_task_response_in_its_own_words():
    """The regression the cues exist for."""
    result = await scorer.score_essay(STRONG, key_points=PROMPTS[0][7],
                                      min_words=120)
    task = next(m for m in result.measures if m.name == "task_response")
    assert task.score >= 60.0, task.basis
    assert not task.detail["missing"], task.detail["missing"]


async def test_too_short_returns_no_measures_rather_than_guesses():
    result = await scorer.score_essay("Sorry, it is late.", key_points=[],
                                      min_words=120)
    assert result.too_short
    assert result.overall is None
    assert result.measures == []
    assert result.notes


async def test_mechanics_catches_what_the_grammar_rules_cannot():
    """The grammar rules were built for speech, which has no capital letters.

    Run against typed text they scored an entirely lower-case paragraph as
    flawless, which is why mechanics is a separate measure.
    """
    clean = scorer.mechanics("The report is late. I have two reasons. Both are fixable.")
    messy = scorer.mechanics("i think this is fine. i am sure. yes it is.")
    assert clean.score > messy.score
    assert clean.score >= 70.0
    assert messy.score <= 40.0


def test_abbreviations_do_not_read_as_missing_capitals():
    """A naive sentence split turns "e.g." into a lower-case sentence start.

    Asserting on the bare word "capital" would pass either way: the clean
    message is "capitalisation, punctuation and spacing are clean".
    """
    note = scorer.mechanics("We tested e.g. the login flow. It passed. Ship it.")
    assert not note.detail["problems"], note.detail["problems"]
    assert note.score >= 70.0, note.basis


def test_lexical_range_declines_to_judge_a_short_sample():
    """Under twenty content words it reports no confidence rather than a number."""
    short = scorer.lexical_range("The project is late. The project is late.")
    assert short.confidence == 0.0
    assert "not enough" in short.basis


def test_lexical_range_notices_repetition():
    repeated = scorer.lexical_range(
        "The project is late. The project work is late because the project "
        "schedule is late. The project work should be faster and the project "
        "schedule should be faster. The project is important and the project "
        "work is important. The project schedule and the project work and the "
        "project deadline are all late, so the project team must work faster "
        "on the project schedule.")
    assert repeated.confidence > 0, repeated.basis
    assert repeated.detail["overused"], "repetition was not detected"
    assert repeated.score < 50.0


def test_coherence_prefers_structure_to_a_wall_of_text():
    wall = scorer.coherence(
        "We did the work. We did more work. We finished the work. "
        "The work is done. The work was hard. The work took time.")
    structured = scorer.coherence(
        "We finished the migration this week, although two services are "
        "still blocked.\\n\\nThe blockage is a firewall approval rather than a "
        "technical problem, which means it needs chasing rather than "
        "solving. For example, the three services behind it move in an "
        "afternoon once it clears.\\n\\nIn conclusion, the timeline holds.")
    assert structured.score > wall.score


# -- the endpoint ----------------------------------------------------------

async def test_the_cues_never_reach_the_client(client):
    """Handing over the cue words would let a student paste them in.

    Task response would then measure whether they read the API response.
    """
    token = await login(client, "student")
    prompts = (await client.get("/api/v1/student/writing/prompts",
                                headers=auth(token))).json()
    assert prompts
    for prompt in prompts:
        for point in prompt["key_points"]:
            assert isinstance(point, str), "a rubric point leaked its cues"
        assert "cues" not in str(prompt)


async def test_a_submission_is_kept_with_its_scores(client):
    """A score with no writing behind it cannot be checked or appealed."""
    token = await login(client, "student")
    prompts = (await client.get("/api/v1/student/writing/prompts",
                                headers=auth(token))).json()

    result = (await client.post(
        f"/api/v1/student/writing/prompts/{prompts[0]['id']}/submit",
        headers=auth(token),
        json={"text": STRONG, "minutes_spent": 11})).json()

    assert result["overall"] is not None
    assert result["text"] == STRONG.strip()
    assert {m["name"] for m in result["measures"]} == {
        "task_response", "coherence", "lexical_range",
        "grammatical_accuracy", "mechanics"}
    for measure in result["measures"]:
        assert measure["basis"], measure["name"]

    listed = (await client.get("/api/v1/student/writing/submissions",
                               headers=auth(token))).json()
    assert any(r["submission_id"] == result["submission_id"] for r in listed)


async def test_an_empty_submission_is_refused(client):
    token = await login(client, "student")
    prompts = (await client.get("/api/v1/student/writing/prompts",
                                headers=auth(token))).json()
    refused = await client.post(
        f"/api/v1/student/writing/prompts/{prompts[0]['id']}/submit",
        headers=auth(token), json={"text": "   ", "minutes_spent": 0})
    assert refused.status_code == 400

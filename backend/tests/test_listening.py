"""Listening comprehension: the audio comes first, and the key stays server-side.

Two properties carry this module. If either breaks it still looks like it
works, which is why they are tested rather than trusted:

* the questions must not reach the client before the passage has been played,
  and must never carry the answer key;
* the position of the correct option must not be guessable.
"""
from __future__ import annotations

import pytest

from app.db import tenant_sessionmaker
from app.listening_bank import PASSAGES, flat_questions, rotated
from app.models.tenant import SkillMastery
from sqlalchemy import select

from tests.test_game_and_practice import SLUG, _student_id, auth, login

# asyncio_mode = auto in pytest.ini, so async tests need no mark -- and the
# pure-content tests below are synchronous, which a module-level asyncio mark
# would warn about on every run.


async def _first_passage(client, token):
    rows = (await client.get("/api/v1/student/listening/passages",
                             headers=auth(token))).json()
    assert rows, "the listening bank is empty"
    return rows[0]


# -- content ---------------------------------------------------------------

def test_the_answer_is_not_always_the_first_option():
    """The flaw this caught: every key authored at index 0.

    Stored that way, a student who taps the first option every time scores
    full marks without listening -- the exact failure the module exists to
    detect. Authoring keeps the key first for readability; `rotated` moves it.
    """
    positions = [key for _t, _s, _o, key, _e in flat_questions()]
    assert len(set(positions)) == 4, (
        f"the key only ever lands in {sorted(set(positions))}")
    # Nothing above chance for a fixed-position guesser.
    for index in range(4):
        share = positions.count(index) / len(positions)
        assert share < 0.5, f"index {index} holds {share:.0%} of the answers"


def test_rotation_preserves_the_authored_answer():
    """Moving the option must not change which text is correct."""
    n = 0
    for passage in PASSAGES:
        for stem, options, correct, _explanation in passage[6]:
            rolled, key = rotated(n, list(options), correct)
            assert rolled[key] == options[correct], stem
            assert sorted(rolled) == sorted(options), stem
            n += 1


def test_rotation_is_stable_across_reseeds():
    """A reseed must not renumber options under a student who has answered."""
    assert flat_questions() == flat_questions()


def test_every_question_has_four_options_and_a_reason():
    for _title, stem, options, key, explanation in flat_questions():
        assert len(options) == 4, stem
        assert 0 <= key < 4, stem
        assert explanation, stem


# -- the flow --------------------------------------------------------------

async def test_questions_never_carry_the_answer_key(client):
    token = await login(client, "student")
    passage = await _first_passage(client, token)

    started = (await client.post(
        f"/api/v1/student/listening/passages/{passage['id']}/start",
        headers=auth(token), json={})).json()

    questions = (await client.get(
        f"/api/v1/student/listening/attempts/{started['attempt_id']}/questions",
        headers=auth(token))).json()

    assert questions
    for q in questions:
        assert set(q) == {"id", "stem", "options"}, (
            f"a question leaked {set(q) - {'id', 'stem', 'options'}}")


async def test_the_transcript_arrives_only_with_the_result(client):
    """It is sent at start for the browser to speak, and again after marking.

    The listing must not carry it: a student browsing passages could
    otherwise read every one without ever pressing play.
    """
    token = await login(client, "student")
    rows = (await client.get("/api/v1/student/listening/passages",
                             headers=auth(token))).json()
    for row in rows:
        assert "transcript" not in row


async def test_an_attempt_cannot_be_submitted_twice(client):
    token = await login(client, "student")
    passage = await _first_passage(client, token)
    started = (await client.post(
        f"/api/v1/student/listening/passages/{passage['id']}/start",
        headers=auth(token), json={})).json()
    attempt_id = started["attempt_id"]

    questions = (await client.get(
        f"/api/v1/student/listening/attempts/{attempt_id}/questions",
        headers=auth(token))).json()
    body = {"answers": [{"item_id": q["id"], "selected_index": 0}
                        for q in questions], "plays_used": 1}

    first = await client.post(
        f"/api/v1/student/listening/attempts/{attempt_id}/submit",
        headers=auth(token), json=body)
    assert first.status_code == 200

    again = await client.post(
        f"/api/v1/student/listening/attempts/{attempt_id}/submit",
        headers=auth(token), json=body)
    assert again.status_code == 409


async def test_questions_are_closed_once_the_attempt_is_marked(client):
    token = await login(client, "student")
    passage = await _first_passage(client, token)
    started = (await client.post(
        f"/api/v1/student/listening/passages/{passage['id']}/start",
        headers=auth(token), json={})).json()
    attempt_id = started["attempt_id"]

    questions = (await client.get(
        f"/api/v1/student/listening/attempts/{attempt_id}/questions",
        headers=auth(token))).json()
    await client.post(f"/api/v1/student/listening/attempts/{attempt_id}/submit",
                      headers=auth(token),
                      json={"answers": [{"item_id": q["id"], "selected_index": 0}
                                        for q in questions], "plays_used": 1})

    closed = await client.get(
        f"/api/v1/student/listening/attempts/{attempt_id}/questions",
        headers=auth(token))
    assert closed.status_code == 409


async def test_a_result_explains_every_question(client):
    token = await login(client, "student")
    passage = await _first_passage(client, token)
    started = (await client.post(
        f"/api/v1/student/listening/passages/{passage['id']}/start",
        headers=auth(token), json={})).json()
    questions = (await client.get(
        f"/api/v1/student/listening/attempts/{started['attempt_id']}/questions",
        headers=auth(token))).json()

    result = (await client.post(
        f"/api/v1/student/listening/attempts/{started['attempt_id']}/submit",
        headers=auth(token),
        json={"answers": [{"item_id": q["id"], "selected_index": 0}
                          for q in questions], "plays_used": 1})).json()

    assert result["total"] == len(questions)
    assert 20.0 <= result["score"] <= 80.0, "must use the internal 20-80 scale"
    assert result["transcript"], "the transcript is released after marking"
    for row in result["items"]:
        assert row["explanation"], row["stem"]


async def test_listening_mastery_moves_on_a_real_result(client):
    """The point of the module: the skill stops being a proxy."""
    token = await login(client, "student")
    user_id = await _student_id(client, token)

    async def mastery():
        """Value and observation count. The count is what always moves.

        Asserting the value changed is wrong: the update is
        0.7*prior + 0.3*observed, so a student whose prior already equals
        their score sits at a fixed point and the number legitimately does
        not move. That is the estimate working, not failing -- and it made
        this test fail on a real, correct result."""
        async with tenant_sessionmaker(SLUG)() as session:
            row = (await session.execute(
                select(SkillMastery).where(
                    SkillMastery.user_id == user_id,
                    SkillMastery.skill == "listening"))).scalars().first()
            return (row.mastery, row.observations) if row else (None, 0)

    before, before_n = await mastery()

    passage = await _first_passage(client, token)
    started = (await client.post(
        f"/api/v1/student/listening/passages/{passage['id']}/start",
        headers=auth(token), json={})).json()
    questions = (await client.get(
        f"/api/v1/student/listening/attempts/{started['attempt_id']}/questions",
        headers=auth(token))).json()
    await client.post(
        f"/api/v1/student/listening/attempts/{started['attempt_id']}/submit",
        headers=auth(token),
        json={"answers": [{"item_id": q["id"], "selected_index": 0}
                          for q in questions], "plays_used": 1})

    after, after_n = await mastery()
    assert after is not None, "a completed passage must produce an estimate"
    assert after_n > before_n, "the result must be counted as an observation"


async def test_one_student_cannot_open_another_students_attempt(client):
    """Attempt ids are guessable-shaped; ownership is checked, not assumed."""
    token = await login(client, "student")
    passage = await _first_passage(client, token)
    started = (await client.post(
        f"/api/v1/student/listening/passages/{passage['id']}/start",
        headers=auth(token), json={})).json()

    other = await login(client, "trainer")
    denied = await client.get(
        f"/api/v1/student/listening/attempts/{started['attempt_id']}/questions",
        headers=auth(other))
    # Either the role gate or the ownership check -- never the questions.
    assert denied.status_code in (403, 404)

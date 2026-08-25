"""Reading: comprehension and rate, measured separately and never blended.

The properties worth guarding are the ones that would still look fine if they
broke: the passage disappearing before the questions, the key staying on the
server, and speed never being reported as though it were understanding.
"""
from __future__ import annotations

from sqlalchemy import select

from app.db import tenant_sessionmaker
from app.models.tenant import ReadingAttempt
from app.reading_bank import PASSAGES, flat_questions, word_count
from app.routers.reading import _rate_note, _score

from tests.test_game_and_practice import SLUG, _student_id, auth, login


# -- content ---------------------------------------------------------------

def test_the_key_is_not_always_the_first_option():
    positions = [key for _t, _s, _o, key, _w in flat_questions()]
    assert len(set(positions)) == 4
    for index in range(4):
        assert positions.count(index) / len(positions) < 0.5


def test_every_passage_has_questions_and_reasons():
    for title, kind, _difficulty, body, questions in PASSAGES:
        assert questions, title
        assert word_count(body) >= 60, f"{title} is too short to time"
        for stem, options, correct, why in questions:
            assert len(options) == 4, stem
            assert 0 <= correct < 4, stem
            assert why, stem


# -- the rate comment ------------------------------------------------------

def test_speed_is_never_praised_on_its_own():
    """Fast with poor comprehension is skimming, and must be named as such."""
    skimming = _rate_note(600, 1, 5)
    assert "is skimming" in skimming.lower()
    assert "costing you" in skimming.lower()

    # Same speed, comprehension intact -- credited, and explicitly *not*
    # called skimming. Matching on the bare word would pass either way, since
    # this note contains the phrase "not skimming".
    genuine = _rate_note(600, 5, 5)
    assert "is skimming" not in genuine.lower()
    assert "not skimming" in genuine.lower()
    assert "genuinely fast" in genuine.lower()


def test_slow_but_accurate_reading_is_not_treated_as_failure():
    note = _rate_note(90, 5, 5)
    assert "slow" in note.lower()
    # The understanding is credited rather than buried under the speed.
    assert "took it in" in note.lower() or "understanding" in note.lower()


def test_an_impossible_rate_is_flagged_rather_than_scored():
    """A client-reported timer can be faked; the number is not trusted blindly."""
    note = _rate_note(2600, 3, 3)
    assert "not treated as a measurement" in note.lower()


def test_a_missing_rate_does_not_invent_one():
    assert "not measured" in _rate_note(None, 3, 3).lower()


def test_the_score_uses_the_internal_scale():
    assert _score(0, 4) == 20.0
    assert _score(4, 4) == 80.0
    assert 20.0 < _score(2, 4) < 80.0


# -- the flow --------------------------------------------------------------

async def _first(client, token):
    rows = (await client.get("/api/v1/student/reading/passages",
                             headers=auth(token))).json()
    assert rows, "the reading bank is empty"
    return rows[0]


async def test_the_listing_does_not_carry_the_passage(client):
    """Browsing must not let a student read everything without being timed."""
    token = await login(client, "student")
    rows = (await client.get("/api/v1/student/reading/passages",
                             headers=auth(token))).json()
    for row in rows:
        assert "body" not in row


async def test_questions_never_carry_the_answer_key(client):
    token = await login(client, "student")
    passage = await _first(client, token)
    started = (await client.post(
        f"/api/v1/student/reading/passages/{passage['id']}/start",
        headers=auth(token), json={})).json()
    questions = (await client.get(
        f"/api/v1/student/reading/attempts/{started['attempt_id']}/questions",
        headers=auth(token))).json()

    assert questions
    for q in questions:
        assert set(q) == {"id", "stem", "options"}


async def test_rate_is_computed_from_the_frozen_word_count(client):
    """words / minutes, against the count stored when the passage was seeded."""
    token = await login(client, "student")
    passage = await _first(client, token)
    started = (await client.post(
        f"/api/v1/student/reading/passages/{passage['id']}/start",
        headers=auth(token), json={})).json()
    questions = (await client.get(
        f"/api/v1/student/reading/attempts/{started['attempt_id']}/questions",
        headers=auth(token))).json()

    # Exactly one minute on the passage: wpm must equal the word count.
    result = (await client.post(
        f"/api/v1/student/reading/attempts/{started['attempt_id']}/submit",
        headers=auth(token),
        json={"answers": [{"item_id": q["id"], "selected_index": 0}
                          for q in questions], "read_ms": 60_000})).json()

    assert result["words_per_minute"] == started["word_count"]
    assert result["word_count"] == started["word_count"]


async def test_comprehension_and_rate_are_reported_separately(client):
    """Neither number may be folded into the other."""
    token = await login(client, "student")
    passage = await _first(client, token)
    started = (await client.post(
        f"/api/v1/student/reading/passages/{passage['id']}/start",
        headers=auth(token), json={})).json()
    questions = (await client.get(
        f"/api/v1/student/reading/attempts/{started['attempt_id']}/questions",
        headers=auth(token))).json()
    result = (await client.post(
        f"/api/v1/student/reading/attempts/{started['attempt_id']}/submit",
        headers=auth(token),
        json={"answers": [{"item_id": q["id"], "selected_index": 0}
                          for q in questions], "read_ms": 45_000})).json()

    assert 20.0 <= result["score"] <= 80.0
    assert result["words_per_minute"] is not None
    assert result["rate_note"]
    # The comprehension score must reflect the answers alone: a fast reader
    # who got half of them wrong cannot score full marks.
    assert result["score"] == _score(result["correct"], result["total"])


async def test_an_attempt_cannot_be_submitted_twice(client):
    token = await login(client, "student")
    passage = await _first(client, token)
    started = (await client.post(
        f"/api/v1/student/reading/passages/{passage['id']}/start",
        headers=auth(token), json={})).json()
    attempt_id = started["attempt_id"]
    questions = (await client.get(
        f"/api/v1/student/reading/attempts/{attempt_id}/questions",
        headers=auth(token))).json()
    body = {"answers": [{"item_id": q["id"], "selected_index": 0}
                        for q in questions], "read_ms": 30_000}

    assert (await client.post(
        f"/api/v1/student/reading/attempts/{attempt_id}/submit",
        headers=auth(token), json=body)).status_code == 200
    assert (await client.post(
        f"/api/v1/student/reading/attempts/{attempt_id}/submit",
        headers=auth(token), json=body)).status_code == 409


async def test_the_attempt_records_both_measures(client):
    token = await login(client, "student")
    user_id = await _student_id(client, token)
    passage = await _first(client, token)
    started = (await client.post(
        f"/api/v1/student/reading/passages/{passage['id']}/start",
        headers=auth(token), json={})).json()
    questions = (await client.get(
        f"/api/v1/student/reading/attempts/{started['attempt_id']}/questions",
        headers=auth(token))).json()
    await client.post(
        f"/api/v1/student/reading/attempts/{started['attempt_id']}/submit",
        headers=auth(token),
        json={"answers": [{"item_id": q["id"], "selected_index": 0}
                          for q in questions], "read_ms": 50_000})

    async with tenant_sessionmaker(SLUG)() as session:
        row = (await session.execute(
            select(ReadingAttempt).where(
                ReadingAttempt.id == started["attempt_id"]))).scalars().one()

    assert row.user_id == user_id
    assert row.read_ms == 50_000
    assert row.words_per_minute is not None
    assert row.score is not None
    assert row.completed_at is not None

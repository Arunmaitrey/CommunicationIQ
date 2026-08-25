"""The game, the quiz, and the guardrails.

Most of these test refusals and absences. The BRD's engagement requirements
are unusual in that several of them are satisfied by code that does not exist
— no price on a streak freeze, no leaderboard query, no endpoint that accepts
an XP amount. Those get tested by asserting the absence, because a promise
kept by omission is exactly the kind that gets broken by a well-meaning patch.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import delete, func, select

from app.db import platform_sessionmaker, tenant_sessionmaker
from app.gamification import engine
from app.models.platform import GamificationConfig
from app.models.tenant import (MistakeBankEntry, Quest, SkillMastery,
                               StreakState, XPLedger)
from tests.conftest import auth, login

pytestmark = pytest.mark.asyncio

SLUG = "stmarys"


async def _config():
    async with platform_sessionmaker()() as ps:
        return await engine.config_for(ps, None)


async def _student_id(client, token) -> str:
    return (await client.get("/api/v1/auth/me", headers=auth(token))).json()["id"]


# -- XP integrity ----------------------------------------------------------

async def test_no_endpoint_accepts_an_xp_amount(client):
    """NFR-15: XP is server-authoritative. A client that can name a number
    can name any number."""
    from app.main import app

    for route in app.routes:
        body_field = getattr(getattr(route, "dependant", None), "body_params", [])
        for param in body_field:
            model = getattr(param, "type_", None)
            fields = getattr(model, "model_fields", {}) or {}
            offenders = [f for f in fields
                         if f in {"xp", "awarded_xp", "total_xp", "level"}]
            assert not offenders, f"{route.path} accepts {offenders}"


async def test_the_ledger_is_append_only_in_practice():
    """Nothing outside the seed deletes or rewrites a ledger row.

    Greps for the operations rather than the name — reading the ledger is
    fine and constant; mutating it is the thing that must not appear.
    """
    import pathlib

    offenders = []
    for path in pathlib.Path("app").rglob("*.py"):
        if path.name == "seed.py":
            continue
        text = path.read_text(encoding="utf-8")
        for marker in ("delete(XPLedger", "update(XPLedger", ".awarded_xp ="):
            if marker in text:
                offenders.append(f"{path.name}: {marker}")
    assert not offenders, offenders


async def test_training_a_weakness_is_worth_more_than_repeating_a_strength():
    """GAM-02. The multiplier is resolved from the student's own mastery,
    not trusted from the caller."""
    config = await _config()
    async with tenant_sessionmaker(SLUG)() as session:
        # A student with mastery records, chosen deterministically.
        #
        # This was `select(XPLedger.user_id).limit(1)` -- no ordering, and
        # then an assertion that whoever came back had mastery. Eight users
        # have ledger entries and twenty-two have mastery, and the two sets
        # are not the same: the test passed only while Postgres happened to
        # return one of the overlap. Any row inserted anywhere could flip it,
        # and eventually one did.
        user_id = (await session.execute(
            select(SkillMastery.user_id)
            .join(XPLedger, XPLedger.user_id == SkillMastery.user_id)
            .order_by(SkillMastery.user_id)
            .limit(1))).scalars().first()
        assert user_id, "no seeded student has both XP and mastery records"

        weakest = await engine.weakest_skills(session, user_id)
        assert weakest, "the chosen student should have mastery records"

        weak = await engine.award(session, config, user_id, "drill_completed",
                                  target_skill=weakest[0])
        strong = await engine.award(session, config, user_id, "drill_completed",
                                    target_skill="__not_a_weakness__")
        await session.rollback()

    assert weak.weakness_multiplier > strong.weakness_multiplier
    assert weak.awarded_xp > strong.awarded_xp


# -- streaks ---------------------------------------------------------------

async def test_a_streak_advances_once_a_day_not_once_an_action():
    config = await _config()
    async with tenant_sessionmaker(SLUG)() as session:
        user_id = (await session.execute(select(XPLedger.user_id).limit(1))).scalars().first()
        await session.execute(delete(StreakState).where(StreakState.user_id == user_id))
        await session.commit()

        today = date(2026, 3, 10)
        state, _ = await engine.touch_streak(session, config, user_id, today)
        assert state.current_streak == 1
        state, _ = await engine.touch_streak(session, config, user_id, today)
        assert state.current_streak == 1, "twice in one day is still one day"

        state, _ = await engine.touch_streak(session, config, user_id,
                                             today + timedelta(days=1))
        assert state.current_streak == 2
        await session.rollback()


async def test_a_freeze_covers_a_missed_day_and_is_spent():
    """GAM-05: a student who was ill comes back to their streak, not a guilt
    screen. The freeze is consumed, and the fact recorded."""
    config = await _config()
    async with tenant_sessionmaker(SLUG)() as session:
        user_id = (await session.execute(select(XPLedger.user_id).limit(1))).scalars().first()
        await session.execute(delete(StreakState).where(StreakState.user_id == user_id))
        await session.commit()

        today = date(2026, 3, 10)
        await engine.touch_streak(session, config, user_id, today)
        state = await engine.streak_state(session, user_id)
        state.freezes_available = 2

        # Skips the 11th entirely.
        state, _ = await engine.touch_streak(session, config, user_id,
                                             today + timedelta(days=2))
        assert state.current_streak == 2
        assert state.freezes_available == 1
        assert state.freeze_history
        await session.rollback()


async def test_a_gap_bigger_than_the_freezes_resets_the_streak():
    config = await _config()
    async with tenant_sessionmaker(SLUG)() as session:
        user_id = (await session.execute(select(XPLedger.user_id).limit(1))).scalars().first()
        await session.execute(delete(StreakState).where(StreakState.user_id == user_id))
        await session.commit()

        today = date(2026, 3, 10)
        await engine.touch_streak(session, config, user_id, today)
        state = await engine.streak_state(session, user_id)
        state.freezes_available = 1

        state, _ = await engine.touch_streak(session, config, user_id,
                                             today + timedelta(days=6))
        assert state.current_streak == 1
        assert state.freezes_available == 1, "a freeze that cannot save it is not spent"
        await session.rollback()


async def test_there_is_no_way_to_buy_a_freeze(client):
    """GAM-21, kept by omission: no price, no currency, no payment hook."""
    from app.main import app

    paths = " ".join(getattr(r, "path", "") for r in app.routes)
    for forbidden in ("freeze/buy", "freeze/purchase", "streak/restore", "gems", "coins"):
        assert forbidden not in paths

    # And no code in the gamification package can charge for anything. The
    # check is on imports and calls, not prose — the docstrings in here
    # explain the prohibition and would trip a naive word search.
    import pathlib
    for path in pathlib.Path("app/gamification").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for marker in ("import razorpay", "import stripe", "PaymentProvider",
                       "create_intent", "Capability.PAYMENT"):
            assert marker not in text, f"{path.name} uses {marker}"


# -- quests ----------------------------------------------------------------

async def test_a_quest_generated_now_targets_the_current_weakest_skill():
    """A quest is generated once a day from the state at that moment, so this
    builds a fresh one rather than asserting about yesterday's."""
    async with tenant_sessionmaker(SLUG)() as session:
        user_id = (await session.execute(
            select(XPLedger.user_id).limit(1))).scalars().first()
        weakest = await engine.weakest_skills(session, user_id, 1)

        tomorrow = date.today() + timedelta(days=1)
        await session.execute(delete(Quest).where(Quest.user_id == user_id,
                                                  Quest.for_date == tomorrow))
        await session.commit()

        quest = await engine.daily_quest(session, user_id, tomorrow)
        assert quest.title
        if weakest:
            assert quest.target_skill == weakest[0]
        else:
            assert "baseline" in quest.title.lower()
        await session.rollback()


async def test_the_daily_quest_is_shown_and_explains_itself(client):
    token = await login(client, "student")
    quest = (await client.get("/api/v1/student/game",
                              headers=auth(token))).json()["quest"]
    assert quest["title"] and quest["description"]
    assert quest["target"] > 0


async def test_asking_twice_in_a_day_returns_the_same_quest(client):
    token = await login(client, "student")
    first = (await client.get("/api/v1/student/game", headers=auth(token))).json()
    second = (await client.get("/api/v1/student/game", headers=auth(token))).json()
    assert first["quest"]["id"] == second["quest"]["id"]


# -- the season ------------------------------------------------------------

async def test_the_countdown_is_the_real_drive_date(client):
    """GAM-25: the only countdown in the product is a true one."""
    token = await login(client, "student")
    season = (await client.get("/api/v1/student/game",
                               headers=auth(token))).json()["season"]

    assert season["is_real_drive_date"] is True
    assert season["drive_date"]

    admin = await login(client, "tenant_admin")
    rows = (await client.get("/api/v1/tenant/season", headers=auth(admin))).json()
    real = next(r for r in rows if r["days_to_drive"] is not None)
    assert abs(real["days_to_drive"] - season["days_remaining"]) <= 1


async def test_a_cohort_with_no_date_gets_a_rolling_season_that_says_so(client):
    from app.models.tenant import Cohort, CohortMember, SeasonPlan, User

    async with tenant_sessionmaker("vignan")() as session:
        student = (await session.execute(
            select(User).where(User.role == "student").limit(1))).scalars().first()
        cohort = (await session.execute(
            select(Cohort).join(CohortMember, CohortMember.cohort_id == Cohort.id)
            .where(CohortMember.user_id == student.id))).scalars().first()
        original = cohort.drive_start
        cohort.drive_start = None
        await session.execute(delete(SeasonPlan).where(SeasonPlan.user_id == student.id))
        await session.commit()

        plan = await engine.season_for(session, student.id)
        assert plan.drive_date is None
        assert (plan.ends_on - plan.starts_on).days == engine.ROLLING_SEASON_DAYS

        cohort.drive_start = original
        await session.commit()


# -- the quiz --------------------------------------------------------------

async def test_a_quiz_never_ships_the_answer_key(client):
    token = await login(client, "student")
    items = (await client.get("/api/v1/student/quiz/next?count=5",
                              headers=auth(token))).json()
    assert items
    for item in items:
        assert "correct_index" not in item
        assert "explanation" not in item
        assert item["options"]


async def test_answering_a_quiz_scores_it_and_explains_the_mistakes(client):
    token = await login(client, "student")
    items = (await client.get("/api/v1/student/quiz/next?count=5",
                              headers=auth(token))).json()

    # Answer everything wrong on purpose.
    answers = [{"item_id": i["id"], "selected_index": 3} for i in items]
    result = (await client.post("/api/v1/student/quiz/submit",
                                json={"answers": answers},
                                headers=auth(token))).json()

    assert result["total"] == len(items)
    assert result["items"]
    for row in result["items"]:
        assert "correct_index" in row
        assert row["explanation"], "a wrong answer without an explanation teaches nothing"


async def test_a_wrong_answer_enters_the_mistake_bank_and_a_right_one_retires_it(client):
    token = await login(client, "student")
    user_id = await _student_id(client, token)

    async with tenant_sessionmaker(SLUG)() as session:
        await session.execute(delete(MistakeBankEntry).where(
            MistakeBankEntry.user_id == user_id))
        await session.commit()

    items = (await client.get("/api/v1/student/quiz/next?count=3",
                              headers=auth(token))).json()
    first = items[0]

    # Deliberately wrong, not guessed. This used to answer index 0 and skip
    # the whole test whenever index 0 happened to be correct -- a coin flip on
    # whether the mistake bank was covered at all, which is worse than no test
    # because the suite still reported green.
    async with tenant_sessionmaker(SLUG)() as session:
        from app.models.tenant import QuizItem
        row = (await session.execute(
            select(QuizItem).where(QuizItem.id == first["id"]))).scalar_one()
        correct_index = row.correct_index
    wrong_index = 1 if correct_index == 0 else 0
    assert wrong_index != correct_index

    await client.post("/api/v1/student/quiz/submit", headers=auth(token),
                      json={"answers": [{"item_id": first["id"],
                                         "selected_index": wrong_index}]})

    mistakes = (await client.get("/api/v1/student/mistakes",
                                 headers=auth(token))).json()
    assert mistakes, "a wrong answer must land in the mistake bank"

    entry = mistakes[0]
    assert entry["times_wrong"] >= 1
    assert entry["interval_days"] >= 1
    assert entry["stem"]

    # Get it right three times and it retires.
    async with tenant_sessionmaker(SLUG)() as session:
        row = (await session.execute(
            select(MistakeBankEntry).where(MistakeBankEntry.id == entry["id"])
        )).scalar_one()
        item_id = row.quiz_item_id
        from app.models.tenant import QuizItem
        correct = (await session.get(QuizItem, item_id)).correct_index

    for _ in range(3):
        await client.post("/api/v1/student/quiz/submit", headers=auth(token),
                          json={"answers": [{"item_id": item_id,
                                             "selected_index": correct}]})

    async with tenant_sessionmaker(SLUG)() as session:
        row = (await session.execute(
            select(MistakeBankEntry).where(MistakeBankEntry.id == entry["id"])
        )).scalar_one()
    assert row.mastered is True


async def test_quizzing_without_speaking_stops_at_one_quiz_a_week(client):
    """QUIZ-06. The first quiz of the week always counts in full; after that,
    more quiz XP has to be earned by speaking."""
    token = await login(client, "student")
    user_id = await _student_id(client, token)
    config = await _config()
    floor = config.xp_table.get("quiz_completed", 25)

    async with tenant_sessionmaker(SLUG)() as session:
        await session.execute(delete(XPLedger).where(XPLedger.user_id == user_id))
        await session.commit()

    capped_seen = False
    for _ in range(5):
        items = (await client.get("/api/v1/student/quiz/next?count=5",
                                  headers=auth(token))).json()
        answers = [{"item_id": i["id"], "selected_index": 0} for i in items]
        result = (await client.post("/api/v1/student/quiz/submit",
                                    json={"answers": answers},
                                    headers=auth(token))).json()
        if result["xp_capped"]:
            capped_seen = True
            assert result["cap_note"], "a capped award must explain itself"

    assert capped_seen, "quizzing all week without speaking must hit the cap"

    async with tenant_sessionmaker(SLUG)() as session:
        rows = list((await session.execute(
            select(XPLedger).where(XPLedger.user_id == user_id))).scalars().all())
    quiz_xp = sum(r.awarded_xp for r in rows if r.activity == "quiz_completed")
    assert quiz_xp <= floor, f"{quiz_xp} XP from quizzes alone, floor is {floor}"


async def test_speaking_practice_unlocks_more_quiz_xp():
    """The share is of the week's total, so speaking raises the quiz ceiling —
    that is the incentive the cap is there to create."""
    config = await _config()
    async with tenant_sessionmaker(SLUG)() as session:
        user_id = (await session.execute(
            select(XPLedger.user_id).limit(1))).scalars().first()
        await session.execute(delete(XPLedger).where(XPLedger.user_id == user_id))
        await session.commit()

        # Quiz only: capped at the floor.
        first = await engine.award(session, config, user_id, "quiz_completed")
        second = await engine.award(session, config, user_id, "quiz_completed")
        await session.flush()
        assert second.cap_applied
        assert second.awarded_xp == 0

        # A speaking attempt raises the ceiling.
        await engine.award(session, config, user_id, "attempt_completed")
        await session.flush()
        third = await engine.award(session, config, user_id, "quiz_completed")
        assert third.awarded_xp > 0
        assert first.awarded_xp > 0
        await session.rollback()


# -- drills ----------------------------------------------------------------

async def test_a_drill_targets_a_diagnosed_weakness_and_says_why(client):
    token = await login(client, "student")
    res = await client.post("/api/v1/student/drills", headers=auth(token))
    assert res.status_code == 201, res.text
    drill = res.json()

    mastery = (await client.get("/api/v1/student/home",
                                headers=auth(token))).json()["mastery"]
    assert drill["target_skill"] == mastery[0]["skill"]
    assert drill["item_count"] > 0
    assert drill["mastery_before"] is not None


async def test_a_drill_is_refused_before_there_is_a_diagnosis(client):
    """Five random items dressed up as a personalised drill would be a lie."""
    from app.models.tenant import SkillMastery, User

    async with tenant_sessionmaker("vignan")() as session:
        student = (await session.execute(
            select(User).where(User.role == "student", User.email.like("%@vignan.edu"))
            .limit(1))).scalars().first()
        saved = list((await session.execute(
            select(SkillMastery).where(SkillMastery.user_id == student.id)
        )).scalars().all())
        rows = [{"skill": m.skill, "mastery": m.mastery, "baseline": m.baseline,
                 "observations": m.observations} for m in saved]
        await session.execute(delete(SkillMastery).where(
            SkillMastery.user_id == student.id))
        await session.commit()

    try:
        res = await client.post("/api/v1/auth/login",
                                json={"email": student.email, "password": "Password123!"})
        token = res.json()["token"]
        drill = await client.post("/api/v1/student/drills", headers=auth(token))
        assert drill.status_code == 409
        assert "baseline" in drill.json()["detail"].lower()
    finally:
        async with tenant_sessionmaker("vignan")() as session:
            for row in rows:
                session.add(SkillMastery(user_id=student.id, **row))
            await session.commit()


# -- the state endpoint ----------------------------------------------------

async def test_effort_and_mastery_are_reported_separately(client):
    """GAM-03/23: level always rises, the gap meter may stall, and the two
    are never merged into one number."""
    token = await login(client, "student")
    state = (await client.get("/api/v1/student/game", headers=auth(token))).json()

    assert "level" in state and "total_xp" in state
    assert "gap_percent" in state
    assert state["level"] == engine.level_for(state["total_xp"])
    # No combined score anywhere in the payload.
    assert not any(k in state for k in ("score", "rating", "rank", "leaderboard"))


async def test_the_ledger_shows_a_student_the_arithmetic(client):
    token = await login(client, "student")
    # Earn something first rather than skipping when the student happens to
    # have an empty ledger. A test that quietly opts out on a shared database
    # reports green while covering nothing.
    items = (await client.get("/api/v1/student/quiz/next?count=1",
                              headers=auth(token))).json()
    if items:
        await client.post("/api/v1/student/quiz/submit", headers=auth(token),
                          json={"answers": [{"item_id": items[0]["id"],
                                             "selected_index": 0}]})

    rows = (await client.get("/api/v1/student/game/ledger",
                             headers=auth(token))).json()
    assert rows, "a submitted quiz must leave a ledger row, even a capped one"
    for row in rows:
        assert {"base_xp", "difficulty_multiplier", "weakness_multiplier",
                "awarded_xp", "cap_applied"} <= set(row)


async def test_a_student_cannot_see_another_students_game_state(client):
    """GAM-22: private by default. There is no route that takes a user id."""
    from app.routers import game

    for route in game.router.routes:
        assert "{user_id}" not in getattr(route, "path", "")


# -- The streak is a function of state, not of one lucky call ---------------

async def test_a_completed_quest_always_counts_the_day(client):
    """A finished day must never sit above an uncounted streak.

    The regression this guards: touch_streak was reachable only from the one
    call that flipped the quest to completed, so the streak was a side effect
    of a single transition rather than a function of state. Whenever that call
    was lost -- a rolled-back request, a quest completed by a seeder or an
    import, two tabs racing -- the day could never qualify again, because
    advance_quest early-returns on an already-completed quest. Accounts got
    permanently stuck showing a 5/5 quest above a 0-day streak.
    """
    token = await login(client, "student")
    user_id = await _student_id(client, token)
    config = await _config()
    today = date.today()

    async with tenant_sessionmaker(SLUG)() as session:
        # Reproduce the stuck state exactly: quest done, day never counted.
        quest = await engine.daily_quest(session, user_id, today)
        quest.progress = quest.target
        quest.completed = True
        state = await engine.streak_state(session, user_id)
        state.current_streak = 0
        state.last_qualifying_day = None
        await session.commit()

    # Merely looking at the game state has to heal it -- a student cannot be
    # asked to trigger a fix they cannot see.
    body = (await client.get("/api/v1/student/game", headers=auth(token))).json()

    assert body["quest"]["completed"] is True
    assert body["streak"]["last_qualifying_day"] == today.isoformat()
    assert body["streak"]["current_streak"] >= 1


async def test_counting_a_day_twice_does_not_double_the_streak(client):
    """qualify_today is called from three places and must be idempotent."""
    token = await login(client, "student")
    user_id = await _student_id(client, token)
    config = await _config()
    today = date.today()

    async with tenant_sessionmaker(SLUG)() as session:
        quest = await engine.daily_quest(session, user_id, today)
        quest.progress = quest.target
        quest.completed = True
        await session.commit()

    async with tenant_sessionmaker(SLUG)() as session:
        await engine.qualify_today(session, config, user_id, today)
        await session.commit()
    async with tenant_sessionmaker(SLUG)() as session:
        first = (await engine.streak_state(session, user_id)).current_streak

    for _ in range(3):
        async with tenant_sessionmaker(SLUG)() as session:
            await engine.qualify_today(session, config, user_id, today)
            await session.commit()

    async with tenant_sessionmaker(SLUG)() as session:
        assert (await engine.streak_state(session, user_id)).current_streak == first


async def test_an_unfinished_quest_does_not_count_the_day(client):
    """The other half of the invariant: qualify_today must not be a free pass."""
    token = await login(client, "student")
    user_id = await _student_id(client, token)
    config = await _config()
    today = date.today()

    async with tenant_sessionmaker(SLUG)() as session:
        quest = await engine.daily_quest(session, user_id, today)
        quest.progress = 0.0
        quest.completed = False
        state = await engine.streak_state(session, user_id)
        state.last_qualifying_day = None
        await session.commit()

    async with tenant_sessionmaker(SLUG)() as session:
        assert await engine.qualify_today(session, config, user_id, today) == []
        await session.commit()

    async with tenant_sessionmaker(SLUG)() as session:
        assert (await engine.streak_state(session, user_id)).last_qualifying_day is None

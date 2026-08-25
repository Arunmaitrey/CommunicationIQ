"""Section results and the four-skill rollup.

The properties that matter are about what must *not* happen: a skill that was
never assessed must not appear as zero, an unscorable section must not read as
a bad performance, and a stored result must not change when it is read again.
"""
from __future__ import annotations

from sqlalchemy import select

from app import sections
from app.db import tenant_sessionmaker
from app.models.tenant import SectionResult

from tests.test_game_and_practice import SLUG, auth, login


def _responses(*means, skipped=0, unscorable=0):
    """Responses whose dimensions average to each given value."""
    out = [{"scores": {"fluency": m, "grammar": m}, "skipped": False}
           for m in means]
    out += [{"scores": {}, "skipped": False} for _ in range(unscorable)]
    out += [{"scores": {}, "skipped": True} for _ in range(skipped)]
    return out


# -- classification --------------------------------------------------------

def test_every_task_type_is_classified_deliberately():
    """An unclassified type would land in speaking and corrupt a rollup.

    Nothing would fail if it did, which is why this is a test rather than a
    convention.
    """
    for task_type, skill in sections.SKILL_OF_TASK.items():
        assert skill in sections.SKILLS, f"{task_type} -> {skill}"

    # The four skills each own at least one task type, or the rollup can never
    # produce them.
    owned = set(sections.SKILL_OF_TASK.values())
    assert owned == set(sections.SKILLS), f"no task types for {set(sections.SKILLS) - owned}"


def test_the_non_speaking_modules_are_not_filed_as_speaking():
    assert sections.skill_of("listening_comprehension") == "listening"
    assert sections.skill_of("reading_comprehension") == "reading"
    assert sections.skill_of("email_writing") == "writing"
    assert sections.skill_of("read_aloud") == "speaking"


# -- section scoring -------------------------------------------------------

def test_a_section_scores_the_mean_of_its_responses():
    result = sections.score_section(
        section_id="s", position=1, title="Read Aloud",
        task_type="read_aloud", responses=_responses(50.0, 60.0, 70.0))
    assert result.score == 60.0
    assert result.items_answered == 3
    assert result.confidence == 1.0


def test_skipped_answers_do_not_drag_a_section_down():
    """A skipped item is an absence, not a zero."""
    answered_only = sections.score_section(
        section_id="s", position=1, title="x", task_type="read_aloud",
        responses=_responses(60.0, 60.0))
    with_skips = sections.score_section(
        section_id="s", position=1, title="x", task_type="read_aloud",
        responses=_responses(60.0, 60.0, skipped=2))
    assert with_skips.score == answered_only.score
    assert with_skips.items_total == 4
    assert with_skips.items_answered == 2


def test_an_unscorable_section_says_why_rather_than_scoring_zero():
    result = sections.score_section(
        section_id="s", position=1, title="x", task_type="read_aloud",
        responses=_responses(unscorable=3))
    assert result.score is None
    assert "nothing could be scored" in result.unscored_reason.lower()
    assert result.confidence == 0.0


def test_a_section_nobody_answered_is_distinguished_from_one_that_failed():
    """Different causes, different messages."""
    unanswered = sections.score_section(
        section_id="s", position=1, title="x", task_type="read_aloud",
        responses=_responses(skipped=3))
    failed = sections.score_section(
        section_id="s", position=1, title="x", task_type="read_aloud",
        responses=_responses(unscorable=3))
    assert unanswered.unscored_reason != failed.unscored_reason
    assert "no answers" in unanswered.unscored_reason.lower()


def test_partial_scoring_lowers_confidence():
    result = sections.score_section(
        section_id="s", position=1, title="x", task_type="read_aloud",
        responses=_responses(60.0, unscorable=3))
    assert result.score == 60.0
    assert result.confidence == 0.25, "one of four scoring is not a firm reading"


# -- rollup ----------------------------------------------------------------

def _section(skill_task, score, title="x", weight=1.0):
    return sections.SectionScore(
        section_id=title, position=1, title=title, task_type=skill_task,
        skill=sections.skill_of(skill_task), score=score, weight=weight)


def test_skills_roll_up_separately_and_are_never_blended():
    """Averaging pronunciation with listening comprehension describes nothing."""
    rolled = sections.roll_up([
        _section("read_aloud", 60.0, "Read Aloud"),
        _section("listening_comprehension", 80.0, "Listening"),
    ])
    assert rolled["speaking"].score == 60.0
    assert rolled["listening"].score == 80.0
    assert "reading" not in rolled and "writing" not in rolled


def test_a_skill_with_no_section_is_absent_not_zero():
    """A report showing Writing as 0 for a test with no writing is a lie."""
    rolled = sections.roll_up([_section("read_aloud", 60.0)])
    assert set(rolled) == {"speaking"}
    assert "writing" not in rolled


def test_an_unscored_skill_reports_none_and_says_so():
    rolled = sections.roll_up([_section("email_writing", None, "Email")])
    assert "writing" in rolled
    assert rolled["writing"].score is None
    assert rolled["writing"].unscored_sections == ["Email"]
    assert rolled["writing"].note


def test_a_partly_scored_skill_uses_what_it_has_and_names_the_gap():
    rolled = sections.roll_up([
        _section("read_aloud", 60.0, "Read Aloud"),
        _section("repeat_sentence", None, "Repeat"),
    ])
    assert rolled["speaking"].score == 60.0
    assert rolled["speaking"].unscored_sections == ["Repeat"]
    assert "could not be scored" in rolled["speaking"].note


def test_weights_shift_a_skill_score():
    even = sections.roll_up([
        _section("read_aloud", 40.0, "A", weight=1.0),
        _section("repeat_sentence", 80.0, "B", weight=1.0),
    ])["speaking"].score
    weighted = sections.roll_up([
        _section("read_aloud", 40.0, "A", weight=3.0),
        _section("repeat_sentence", 80.0, "B", weight=1.0),
    ])["speaking"].score
    assert even == 60.0
    assert weighted == 50.0


# -- persistence -----------------------------------------------------------

async def test_a_result_stores_its_sections_once(client):
    """Reading a report twice must not stack a second set of rows."""
    token = await login(client, "student")
    attempts = (await client.get("/api/v1/student/attempts",
                                 headers=auth(token))).json()
    scored = [a for a in attempts if a["status"] == "scored"]
    if not scored:
        raise AssertionError("the demo estate has no scored attempt to read")
    attempt_id = scored[0]["id"]

    first = (await client.get(f"/api/v1/student/attempts/{attempt_id}/result",
                              headers=auth(token))).json()
    second = (await client.get(f"/api/v1/student/attempts/{attempt_id}/result",
                               headers=auth(token))).json()

    assert first["sections"], "no section results were stored"
    assert len(first["sections"]) == len(second["sections"])
    assert ([s["score"] for s in first["sections"]]
            == [s["score"] for s in second["sections"]])

    async with tenant_sessionmaker(SLUG)() as session:
        rows = list((await session.execute(
            select(SectionResult).where(SectionResult.attempt_id == attempt_id)
        )).scalars().all())
    assert len(rows) == len(first["sections"])
    for row in rows:
        assert row.scorer_version, "a stored result must record what scored it"


async def test_a_result_carries_a_skill_rollup(client):
    token = await login(client, "student")
    attempts = (await client.get("/api/v1/student/attempts",
                                 headers=auth(token))).json()
    scored = [a for a in attempts if a["status"] == "scored"]
    attempt_id = scored[0]["id"]

    body = (await client.get(f"/api/v1/student/attempts/{attempt_id}/result",
                             headers=auth(token))).json()

    assert body["skills"], "no skill rollup"
    for entry in body["skills"]:
        assert entry["skill"] in sections.SKILLS
        assert entry["section_count"] >= 1
    # Every skill present must be backed by a section of that skill.
    present = {e["skill"] for e in body["skills"]}
    from_sections = {s["skill"] for s in body["sections"]}
    assert present <= from_sections


# -- response modes (Phase 3 contract) --------------------------------------

def test_every_task_type_has_a_response_mode():
    """A type with no mode records audio, which is wrong for a written task."""
    for task_type in sections.SKILL_OF_TASK:
        mode = sections.mode_of(task_type)
        assert mode in ("speak", "select", "write"), f"{task_type} -> {mode}"


def test_modes_and_skills_agree():
    """A listening task cannot be answered by speaking, and so on.

    Not a style rule: a mismatch here would route a section to the wrong
    handler at runtime, and the failure would look like a scoring bug rather
    than a classification one.
    """
    for task_type, skill in sections.SKILL_OF_TASK.items():
        mode = sections.mode_of(task_type)
        if skill == "writing":
            assert mode == "write", f"{task_type} is writing but answers {mode}"
        if skill == "reading":
            assert mode in ("select", "write"), task_type
        if mode == "speak":
            assert skill == "speaking", f"{task_type} speaks but is {skill}"


def test_unknown_task_types_still_speak():
    """Everything authored before the other modes existed must be unaffected."""
    assert sections.mode_of("read_aloud") == "speak"
    assert sections.mode_of("something_new_and_unclassified") == "speak"


# -- whole-passage selection (Phase 3) --------------------------------------

def test_selection_fills_the_section_when_the_passages_allow_it():
    """The regression, tested deterministically rather than through a shuffle.

    Greedy-in-shuffled-order took the first passage that fit and then had no
    room: with a two and a three and a target of three, taking the two first
    delivers two. It only misfires when the small passage happens to come
    first, so routed through the API it failed about one run in six -- and an
    end-to-end test of that path passed with the bug still in place.
    """
    # The exact shape that broke it, with the small passage first.
    assert sum({"a": 2, "b": 3}[p]
               for p in sections.fill_from_passages({"a": 2, "b": 3}, 3)) == 3

    # And the real listening bank.
    bank = {"p1": 2, "p2": 3, "p3": 3, "p4": 3, "p5": 3, "p6": 3}
    for target, expected in ((2, 2), (3, 3), (5, 5), (6, 6), (17, 17)):
        got = sum(bank[p] for p in sections.fill_from_passages(bank, target))
        assert got == expected, f"asked {target}, filled {got}"


def test_selection_never_exceeds_the_target_or_splits_a_passage():
    bank = {"p1": 2, "p2": 3, "p3": 3}
    for target in range(0, 12):
        picked = sections.fill_from_passages(bank, target)
        total = sum(bank[p] for p in picked)
        assert total <= target, f"{target} -> {total}"
        assert len(picked) == len(set(picked)), "a passage was taken twice"


def test_an_unreachable_target_settles_for_the_best_below_it():
    """Four is not reachable from twos and threes. Three is the honest answer."""
    bank = {"p1": 2, "p2": 3, "p3": 3}
    assert sum(bank[p] for p in sections.fill_from_passages(bank, 4)) == 3


async def test_a_mixed_skill_assessment_delivers_every_section(client):
    """One attempt, three skills, every section filled. The end-to-end shape.

    Deliberately paired with the deterministic tests above: this one proves
    the wiring, those prove the algorithm. On its own it passed with the bug
    still present.
    """
    admin = await login(client, "tenant_admin")
    created = await client.post(
        "/api/v1/tenant/profiles", headers=auth(admin),
        json={
            "name": "Mixed-skill regression", "style": "company_round",
            "company": "Testco", "description": "Three skills, one attempt.",
            "estimated_minutes": 20,
            "sections": [
                {"title": "Speaking", "task_type": "read_aloud",
                 "item_count": 3, "prep_seconds": 5, "response_seconds": 20,
                 "prompt_plays_allowed": 0, "allow_replay": False},
                {"title": "Listening", "task_type": "listening_comprehension",
                 "item_count": 3, "prep_seconds": 0, "response_seconds": 0,
                 "prompt_plays_allowed": 1, "allow_replay": False},
                {"title": "Reading", "task_type": "reading_comprehension",
                 "item_count": 3, "prep_seconds": 0, "response_seconds": 0,
                 "prompt_plays_allowed": 0, "allow_replay": False},
            ],
        })
    assert created.status_code in (200, 201), created.text
    profile_id = created.json()["id"]

    published = await client.post(
        f"/api/v1/tenant/profiles/{profile_id}/status",
        headers=auth(admin), json={"status": "published"})
    assert published.status_code == 200, published.text

    student = await login(client, "student")
    payload = (await client.post(
        "/api/v1/student/attempts", headers=auth(student),
        json={"profile_id": profile_id, "mode": "practice"})).json()

    counts: dict[str, int] = {}
    for item in payload["items"]:
        counts[item["skill"]] = counts.get(item["skill"], 0) + 1

    assert counts == {"speaking": 3, "listening": 3, "reading": 3}, counts


async def test_a_listening_item_does_not_ship_its_transcript(client):
    """Sending the words with the question turns listening into reading.

    The same rule Repeat Sentence follows. A reading passage *is* sent,
    because reading it is the task.
    """
    admin = await login(client, "tenant_admin")
    created = (await client.post(
        "/api/v1/tenant/profiles", headers=auth(admin),
        json={"name": "Stimulus rules", "style": "company_round",
              "company": "T", "description": "x", "estimated_minutes": 10,
              "sections": [
                  {"title": "Listening", "task_type": "listening_comprehension",
                   "item_count": 3, "prep_seconds": 0, "response_seconds": 0,
                   "prompt_plays_allowed": 1, "allow_replay": False},
                  {"title": "Reading", "task_type": "reading_comprehension",
                   "item_count": 3, "prep_seconds": 0, "response_seconds": 0,
                   "prompt_plays_allowed": 0, "allow_replay": False},
              ]})).json()
    await client.post(f"/api/v1/tenant/profiles/{created['id']}/status",
                      headers=auth(admin), json={"status": "published"})

    student = await login(client, "student")
    payload = (await client.post(
        "/api/v1/student/attempts", headers=auth(student),
        json={"profile_id": created["id"], "mode": "practice"})).json()

    listening = [i for i in payload["items"] if i["skill"] == "listening"]
    reading = [i for i in payload["items"] if i["skill"] == "reading"]
    assert listening and reading

    for item in listening:
        assert not item["stimulus_text"], "a listening transcript was shipped"
        assert item["has_prompt_audio"]
        assert item["question"] and item["options"]
    for item in reading:
        assert item["stimulus_text"], "a reading passage was withheld"

    # And no answer key anywhere, in either.
    for item in payload["items"]:
        assert not any("correct" in key.lower() for key in item)


async def test_the_publish_guard_knows_where_each_bank_lives(client):
    """It counted spoken items only, and refused valid mixed templates."""
    admin = await login(client, "tenant_admin")
    created = (await client.post(
        "/api/v1/tenant/profiles", headers=auth(admin),
        json={"name": "Guard knows the banks", "style": "company_round",
              "company": "T", "description": "x", "estimated_minutes": 10,
              "sections": [
                  {"title": "Listening", "task_type": "listening_comprehension",
                   "item_count": 3, "prep_seconds": 0, "response_seconds": 0,
                   "prompt_plays_allowed": 1, "allow_replay": False}]})).json()
    published = await client.post(
        f"/api/v1/tenant/profiles/{created['id']}/status",
        headers=auth(admin), json={"status": "published"})
    assert published.status_code == 200, published.text


async def test_an_unreachable_item_count_is_refused_at_publish(client):
    """Passages come in twos and threes; four is not reachable from them.

    Better to refuse than to run a section quietly short of what it asked for.
    """
    admin = await login(client, "tenant_admin")
    created = (await client.post(
        "/api/v1/tenant/profiles", headers=auth(admin),
        json={"name": "Unreachable count", "style": "company_round",
              "company": "T", "description": "x", "estimated_minutes": 10,
              "sections": [
                  {"title": "Listening", "task_type": "listening_comprehension",
                   "item_count": 4, "prep_seconds": 0, "response_seconds": 0,
                   "prompt_plays_allowed": 1, "allow_replay": False}]})).json()
    refused = await client.post(
        f"/api/v1/tenant/profiles/{created['id']}/status",
        headers=auth(admin), json={"status": "published"})
    assert refused.status_code == 400
    # Asserting on behaviour rather than on a phrase. Pinning the exact
    # wording has already broken twice today when the message improved, which
    # teaches nothing except to stop improving messages.
    assert "4" in refused.text, "the refusal must name what was asked for"
    assert "3" in refused.text, "and what can actually be served"
    assert "passage" in refused.text.lower(), "and why"


def test_a_spoken_section_still_needs_a_response_clock():
    """Untimed is legitimate for reading, nonsense for speaking."""
    from pydantic import ValidationError
    from app.schemas import ProfileSectionRequest

    ProfileSectionRequest(title="Reading", task_type="reading_comprehension",
                          item_count=3, response_seconds=0)
    try:
        ProfileSectionRequest(title="Read Aloud", task_type="read_aloud",
                              item_count=3, response_seconds=0)
    except ValidationError as exc:
        assert "at least 5 seconds" in str(exc)
    else:
        raise AssertionError("a zero-second spoken section was accepted")


# -- sitting a non-speaking assessment (Phase 3, client half) ---------------

async def _mixed_profile(client, admin, name, sections_spec):
    created = (await client.post(
        "/api/v1/tenant/profiles", headers=auth(admin),
        json={"name": name, "style": "company_round", "company": "T",
              "description": "x", "estimated_minutes": 10,
              "sections": sections_spec})).json()
    published = await client.post(
        f"/api/v1/tenant/profiles/{created['id']}/status",
        headers=auth(admin), json={"status": "published"})
    assert published.status_code == 200, published.text
    return created["id"]


_LISTENING = {"title": "Listening", "task_type": "listening_comprehension",
              "item_count": 3, "prep_seconds": 0, "response_seconds": 0,
              "prompt_plays_allowed": 1, "allow_replay": False}
_READING = {"title": "Reading", "task_type": "reading_comprehension",
            "item_count": 3, "prep_seconds": 0, "response_seconds": 0,
            "prompt_plays_allowed": 0, "allow_replay": False}


async def test_a_candidate_can_sit_a_non_speaking_assessment(client):
    """The whole point of Phase 3: answered, scored, rolled up, no microphone."""
    admin = await login(client, "tenant_admin")
    profile_id = await _mixed_profile(client, admin, "Sit it",
                                      [_LISTENING, _READING])

    student = await login(client, "student")
    payload = (await client.post(
        "/api/v1/student/attempts", headers=auth(student),
        json={"profile_id": profile_id, "mode": "practice"})).json()
    attempt_id = payload["attempt_id"]

    assert payload["items"], "no items were served"
    assert not any(i["response_mode"] == "speak" for i in payload["items"]), (
        "a test with no speaking must not contain a spoken item")

    for item in payload["items"]:
        if item["has_prompt_audio"]:
            await client.post(
                f"/api/v1/student/attempts/{attempt_id}/responses/"
                f"{item['response_id']}/prompt", headers=auth(student), json={})
        answered = await client.post(
            f"/api/v1/student/attempts/{attempt_id}/responses/"
            f"{item['response_id']}/answer",
            headers=auth(student), json={"selected_index": 0})
        assert answered.status_code == 201, answered.text

    result = (await client.post(f"/api/v1/student/attempts/{attempt_id}/submit",
                                headers=auth(student), json={})).json()

    skills = {s["skill"]: s["score"] for s in result["skills"]}
    assert set(skills) == {"listening", "reading"}, skills
    for skill, score in skills.items():
        assert score is not None, f"{skill} produced no score"
        assert 20.0 <= score <= 80.0, f"{skill} off the internal scale: {score}"


async def test_an_item_cannot_be_answered_twice(client):
    """Otherwise a candidate tries options until one scores."""
    admin = await login(client, "tenant_admin")
    profile_id = await _mixed_profile(client, admin, "One shot", [_READING])

    student = await login(client, "student")
    payload = (await client.post(
        "/api/v1/student/attempts", headers=auth(student),
        json={"profile_id": profile_id, "mode": "practice"})).json()
    first_item = payload["items"][0]
    path = (f"/api/v1/student/attempts/{payload['attempt_id']}/responses/"
            f"{first_item['response_id']}/answer")

    assert (await client.post(path, headers=auth(student),
                              json={"selected_index": 0})).status_code == 201
    again = await client.post(path, headers=auth(student),
                              json={"selected_index": 1})
    assert again.status_code == 409


async def test_a_spoken_item_refuses_a_typed_answer(client):
    """The two submission paths are not interchangeable."""
    admin = await login(client, "tenant_admin")
    profile_id = await _mixed_profile(client, admin, "Speaking only", [{
        "title": "Read Aloud", "task_type": "read_aloud", "item_count": 2,
        "prep_seconds": 5, "response_seconds": 20,
        "prompt_plays_allowed": 0, "allow_replay": False}])

    student = await login(client, "student")
    payload = (await client.post(
        "/api/v1/student/attempts", headers=auth(student),
        json={"profile_id": profile_id, "mode": "practice"})).json()

    refused = await client.post(
        f"/api/v1/student/attempts/{payload['attempt_id']}/responses/"
        f"{payload['items'][0]['response_id']}/answer",
        headers=auth(student), json={"text": "typed instead of spoken"})
    assert refused.status_code == 409
    assert "speaking" in refused.text.lower()


# -- dictation (Phase 4) -----------------------------------------------------

_DICTATION = {"title": "Dictation", "task_type": "dictation",
              "item_count": 3, "prep_seconds": 0, "response_seconds": 0,
              "prompt_plays_allowed": 1, "allow_replay": False}


def test_task_type_knowledge_lives_in_one_place():
    """Adding a task type must mean filling in one module, not hunting.

    Three separate bugs in one day came from a set or map enumerated when
    only speaking existed and then not updated: the item source, the publish
    guard, and the spoken-reference set. They are all in `sections` now, so a
    missing entry is visible beside the others.
    """
    for task_type in sections.SKILL_OF_TASK:
        assert sections.skill_of(task_type) in sections.SKILLS
        assert sections.mode_of(task_type) in ("speak", "select", "write")
        kind, _key = sections.source_of(task_type)
        assert kind in ("task", "quiz", "writing_prompt"), task_type


def test_dictation_is_listening_measured_through_writing():
    assert sections.skill_of("dictation") == "listening"
    assert sections.mode_of("dictation") == "write"
    # It borrows the spoken sentence bank rather than duplicating it.
    assert sections.source_of("dictation") == ("task", "repeat_sentence")
    # And the played audio is the reference, not the (empty) prompt text.
    assert sections.speaks_reference("dictation")


async def test_dictation_scores_what_was_heard(client):
    """Exact, reordered and unrelated answers must score differently.

    Reordering is the one that matters: "the dog bit the man" and "the man
    bit the dog" are the same bag of words and not the same answer, so a
    comparison that ignores order would score them alike.
    """
    admin = await login(client, "tenant_admin")
    profile_id = await _mixed_profile(client, admin, "Dictation scoring",
                                      [_DICTATION])
    student = await login(client, "student")
    payload = (await client.post(
        "/api/v1/student/attempts", headers=auth(student),
        json={"profile_id": profile_id, "mode": "practice"})).json()
    attempt_id = payload["attempt_id"]

    async def answer(item, transform):
        heard = (await client.post(
            f"/api/v1/student/attempts/{attempt_id}/responses/"
            f"{item['response_id']}/prompt",
            headers=auth(student), json={})).json()
        assert "text" in heard, f"the prompt served nothing: {heard}"
        marked = await client.post(
            f"/api/v1/student/attempts/{attempt_id}/responses/"
            f"{item['response_id']}/answer",
            headers=auth(student), json={"text": transform(heard["text"])})
        assert marked.status_code == 201, marked.text
        return marked.json()["word_accuracy"]

    exact = await answer(payload["items"][0], lambda t: t)
    reversed_words = await answer(payload["items"][1],
                                  lambda t: " ".join(reversed(t.split())))
    unrelated = await answer(payload["items"][2],
                             lambda _t: "completely unrelated words")

    assert exact == 1.0, f"an exact transcription scored {exact}"
    assert unrelated < 0.2, f"unrelated text scored {unrelated}"
    assert reversed_words < 0.6, (
        f"reordered words scored {reversed_words} -- word order is not being "
        f"checked")


async def test_a_dictation_item_never_shows_its_sentence(client):
    """Hearing it is the task. Printing it would make this a typing test."""
    admin = await login(client, "tenant_admin")
    profile_id = await _mixed_profile(client, admin, "Dictation hidden",
                                      [_DICTATION])
    student = await login(client, "student")
    payload = (await client.post(
        "/api/v1/student/attempts", headers=auth(student),
        json={"profile_id": profile_id, "mode": "practice"})).json()

    for item in payload["items"]:
        assert item["prompt_text"] == "", "a dictation sentence was shipped"
        assert item["stimulus_text"] == ""
        assert item["question"], "the candidate needs an instruction"
        assert item["has_prompt_audio"]


# -- sentence completion (Phase 4) -------------------------------------------

def test_grouping_is_declared_per_category_not_assumed():
    """Whole-passage drawing is right for comprehension and wrong for gaps.

    Applying it to every quiz item made eighteen standalone completions look
    like one indivisible block, so a four-item section could be served none of
    them. Comprehension is measured over a passage; a gap-fill is meaningful
    on its own.
    """
    assert sections.groups_by_passage("audio_comprehension")
    assert sections.groups_by_passage("reading_comprehension")
    assert not sections.groups_by_passage("sentence_completion")


def test_completion_accepts_every_word_that_fits():
    """Marking "although" wrong because the author wrote "though" is a lie."""
    from app.completion_bank import ITEMS, is_correct

    multi = [(s, a) for s, a, _t in ITEMS if len(a) > 1]
    assert multi, "no item accepts an alternative -- English usually does"
    for _sentence, accepted in multi:
        for word in accepted:
            assert is_correct(word, accepted), word

    # Case and trailing punctuation are typing, not English.
    assert is_correct("Because,", {"because"})
    assert is_correct("  SINCE ", {"since"})
    assert not is_correct("however", {"because", "since"})
    assert not is_correct("   ", {"because"})


def test_every_completion_item_has_a_gap_and_an_answer():
    from app.completion_bank import ITEMS

    for sentence, accepted, tests in ITEMS:
        assert "___" in sentence, sentence
        assert accepted, sentence
        assert tests, sentence


async def test_completion_never_ships_its_accepted_answers(client):
    """The words live in the same column multiple choice uses for options.

    Reusing the row shape is right; shipping `options` for every quiz-sourced
    item was not, because for this category those *are* the answers.
    """
    admin = await login(client, "tenant_admin")
    profile_id = await _mixed_profile(client, admin, "Completion secrecy", [{
        "title": "Gaps", "task_type": "sentence_completion", "item_count": 4,
        "prep_seconds": 0, "response_seconds": 0,
        "prompt_plays_allowed": 0, "allow_replay": False}])

    student = await login(client, "student")
    payload = (await client.post(
        "/api/v1/student/attempts", headers=auth(student),
        json={"profile_id": profile_id, "mode": "practice"})).json()

    assert len(payload["items"]) == 4, "standalone items must be picked singly"
    for item in payload["items"]:
        assert item["options"] == [], "the accepted answers were shipped"
        assert "___" in item["question"], "the gap is missing from the stem"
        assert item["response_mode"] == "write"


async def test_completion_marks_only_the_words_that_fit(client):
    """One word answered everywhere must be right sometimes and wrong others.

    A marker returning all-correct or all-wrong is broken, and both look
    plausible from a single item.

    The whole bank, not a sample of six. Two of the eighteen gaps accept
    "because", so a six-item section misses both about one run in six -- and
    this test duly failed on a run where nothing had changed. A test that is
    right five times out of six is not evidence, and the fix is to stop
    sampling rather than to widen the sample.
    """
    from app.completion_bank import ITEMS

    admin = await login(client, "tenant_admin")
    # The connector bank only: the SVAR-style grammar categories (verb
    # forms, tenses, articles, prepositions) share the category and carry
    # their own topics, and "because" fits none of them.
    profile_id = await _mixed_profile(client, admin, "Completion marking", [{
        "title": "Gaps", "task_type": "sentence_completion",
        "item_count": len(ITEMS),
        "prep_seconds": 0, "response_seconds": 0,
        "prompt_plays_allowed": 0, "allow_replay": False,
        "selection": {"topics": ["connectors"]}}])

    student = await login(client, "student")
    payload = (await client.post(
        "/api/v1/student/attempts", headers=auth(student),
        json={"profile_id": profile_id, "mode": "practice"})).json()

    verdicts = []
    for item in payload["items"]:
        marked = (await client.post(
            f"/api/v1/student/attempts/{payload['attempt_id']}/responses/"
            f"{item['response_id']}/answer",
            headers=auth(student), json={"text": "because"})).json()
        verdicts.append(marked["correct"])

    assert len(verdicts) == len(ITEMS), (
        f"the section served {len(verdicts)} of {len(ITEMS)} gaps")
    fits = sum(1 for entry in ITEMS if "because" in entry[1])
    assert sum(verdicts) == fits, (
        f"{sum(verdicts)} gaps marked correct, but 'because' fits {fits}")
    assert 0 < fits < len(ITEMS), "the bank cannot demonstrate the property"


# -- the five remaining Phase 4 task types -----------------------------------
#
# Written after the same nine-times-repeated mistake: a rule that was correct
# when only speaking existed, silently applied to a task type that arrived
# later. Each of these asserts a *property of the task type* rather than
# checking the happy path once.

def test_all_six_task_type_maps_cover_every_task_type():
    """The consistency test, extended to the sixth map.

    `DIMENSIONS_BY_TASK` was the one nobody had noticed: five maps in
    `sections` were kept in step by the test above while a sixth in
    `evaluation` covered none of the nine task types added after it was
    written. A task type missing from it produces dimensions that
    `_unscored_reasons` then reports as unmeasured -- scored and reported
    missing in the same response.
    """
    from app.evaluation import DIMENSIONS_BY_TASK

    missing = [t for t in sections.SKILL_OF_TASK if t not in DIMENSIONS_BY_TASK]
    assert not missing, f"no dimensions declared for {missing}"

    stray = [t for t in DIMENSIONS_BY_TASK if t not in sections.SKILL_OF_TASK]
    assert not stray, f"{stray} have dimensions but no skill"

    for task_type, dims in DIMENSIONS_BY_TASK.items():
        assert dims, f"{task_type} declares no dimensions at all"


def test_a_router_marked_task_type_declares_exactly_one_dimension():
    """`_sole_dimension` reads the table; the table must be readable that way.

    A select-mode or completion task writes one ScoreRecord. If its table
    entry listed two dimensions the helper would fall back to a hard-coded
    name and the two would drift apart silently.
    """
    from app.evaluation import DIMENSIONS_BY_TASK
    from app.routers.attempts import _sole_dimension

    for task_type in ("listening_comprehension", "reading_comprehension",
                      "response_selection", "vocabulary_in_context",
                      "dictation", "sentence_completion"):
        dims = DIMENSIONS_BY_TASK[task_type]
        assert len(dims) == 1, f"{task_type} marks once but declares {dims}"
        assert _sole_dimension(task_type, "wrong") == next(iter(dims))


def test_the_new_task_types_are_classified_the_way_they_measure():
    """Each assumption checked against what the task actually does.

    Written out one at a time rather than as a loop, because the value of
    this test is that somebody had to decide each line.
    """
    # Spoken answers to something heard. Speaking, because the candidate
    # talks and the delivery is what the engine measures.
    for spoken in ("conversation_question", "passage_question"):
        assert sections.skill_of(spoken) == "speaking"
        assert sections.mode_of(spoken) == "speak"
        assert sections.source_of(spoken) == ("task", spoken)
        # Their text is played, not shown -- it lives in reference_text.
        assert sections.speaks_reference(spoken)

    # Which reply fits. Listening, because the line is heard; and its own
    # quiz category, because it is not comprehension.
    assert sections.skill_of("response_selection") == "listening"
    assert sections.mode_of("response_selection") == "select"
    assert sections.source_of("response_selection") == ("quiz",
                                                        "response_selection")
    assert not sections.groups_by_passage("response_selection"), (
        "each exchange is its own item; grouping would make a section of "
        "four unfillable")

    # Word sense. Reading, because the sentence is on the screen.
    assert sections.skill_of("vocabulary_in_context") == "reading"
    assert sections.mode_of("vocabulary_in_context") == "select"
    assert not sections.groups_by_passage("vocabulary_in_context")

    # Read, lose, write back. Writing, and its own prompt kind.
    assert sections.skill_of("passage_reconstruction") == "writing"
    assert sections.mode_of("passage_reconstruction") == "write"
    assert sections.source_of("passage_reconstruction") == ("writing_prompt",
                                                            "reconstruction")


def test_a_reconstruction_passage_is_never_served_as_an_email():
    """Both live in WritingPrompt, and they are not interchangeable."""
    assert "reconstruction" not in sections.COMPOSING_KINDS
    assert sections.prompt_kinds_for("") == sections.COMPOSING_KINDS
    assert sections.prompt_kinds_for("reconstruction") == frozenset(
        {"reconstruction"})


# -- conversation and passage questions --------------------------------------

def test_the_spoken_question_bank_carries_a_markable_rubric():
    """The key must be `key_points` -- the name the content contract reads.

    A synonym parses, matches nothing, and produces a confident zero rather
    than an error. This is the whole failure mode.
    """
    from app.spoken_question_bank import ITEMS

    assert ITEMS
    for task_type, spoken, rubric, _difficulty in ITEMS:
        assert task_type in ("conversation_question", "passage_question")
        assert spoken.strip()
        points = rubric.get("key_points")
        assert points, f"{task_type} has no key points to mark against"
        assert all(str(p).strip() for p in points)
        # The question is inside the audio: it is played once and the
        # candidate answers it, so it must actually be asked.
        assert "?" in spoken, "the spoken text never asks anything"


def test_a_spoken_question_is_not_scored_against_its_own_question():
    """The reference text is the stimulus, not a target utterance.

    `speaks_reference` puts these two in the same set as Repeat Sentence,
    whose reference *is* the answer. What keeps them apart is the accuracy
    provider's own list of scripted tasks -- if these ever joined it, a
    candidate's answer would be scored for word-overlap with the question
    they were asked.
    """
    from app.engine.providers.tier1.accuracy import SCRIPTED_TASKS

    for spoken in ("conversation_question", "passage_question",
                   "story_retell", "dictation"):
        assert spoken not in SCRIPTED_TASKS, (
            f"{spoken} would be word-matched against its own prompt")


async def test_a_spoken_question_never_ships_the_thing_it_asks_about(client):
    """Hearing it once is the task. Shipping it makes it a reading test."""
    admin = await login(client, "tenant_admin")
    profile_id = await _mixed_profile(client, admin, "Heard question", [{
        "title": "Conversations", "task_type": "conversation_question",
        "item_count": 2, "prep_seconds": 0, "response_seconds": 30,
        "prompt_plays_allowed": 1, "allow_replay": False}])

    student = await login(client, "student")
    payload = (await client.post(
        "/api/v1/student/attempts", headers=auth(student),
        json={"profile_id": profile_id, "mode": "practice"})).json()

    assert payload["items"], "no conversation items were served"
    for item in payload["items"]:
        assert item["prompt_text"] == "", "the exchange must not be shown"
        assert item["stimulus_text"] == ""
        assert item["response_mode"] == "speak"
        assert item["has_prompt_audio"]

    # And the words do arrive, once, when the prompt is played.
    first = payload["items"][0]
    played = await client.post(
        f"/api/v1/student/attempts/{payload['attempt_id']}/responses/"
        f"{first['response_id']}/prompt", headers=auth(student), json={})
    assert played.status_code == 200, played.text
    assert "?" in played.json()["text"], "the question was not played"


# -- response selection ------------------------------------------------------

def test_every_response_selection_distractor_is_correct_english():
    """The measure is register, not grammar.

    If a wrong option could be eliminated on grammar the item would be a
    grammar question wearing a listening label.
    """
    from app.selection_bank import RESPONSES

    assert len(RESPONSES) >= 6
    for line, replies, correct, why in RESPONSES:
        assert line.strip() and why.strip()
        assert len(replies) >= 3
        assert 0 <= correct < len(replies)
        for reply in replies:
            assert reply[0].isupper(), f"not a sentence: {reply}"
            assert reply.rstrip()[-1] in ".?!", f"not a sentence: {reply}"


async def test_response_selection_plays_the_line_and_shows_only_the_replies(client):
    """The line is heard; the replies are read. Both halves matter.

    Shipping the line would remove the listening. Playing the replies would
    make the item a memory test rather than a choice.
    """
    admin = await login(client, "tenant_admin")
    profile_id = await _mixed_profile(client, admin, "Replies", [{
        "title": "Choose a reply", "task_type": "response_selection",
        "item_count": 3, "prep_seconds": 0, "response_seconds": 0,
        "prompt_plays_allowed": 1, "allow_replay": False}])

    student = await login(client, "student")
    payload = (await client.post(
        "/api/v1/student/attempts", headers=auth(student),
        json={"profile_id": profile_id, "mode": "practice"})).json()

    assert len(payload["items"]) == 3, payload["items"]
    for item in payload["items"]:
        assert item["stimulus_text"] == "", "the spoken line must be withheld"
        assert item["has_prompt_audio"], "there is nothing to listen to"
        assert item["options"], "the replies must be readable"
        assert item["skill"] == "listening"

    played = (await client.post(
        f"/api/v1/student/attempts/{payload['attempt_id']}/responses/"
        f"{payload['items'][0]['response_id']}/prompt",
        headers=auth(student), json={}))
    assert played.status_code == 200, played.text
    assert played.json()["text"].strip(), "nothing was played"
    assert played.json()["plays_remaining"] == 0


async def test_response_selection_scores_appropriacy_not_comprehension(client):
    """Two different abilities must not arrive under one name.

    A candidate told their listening comprehension is weak, when what they
    actually missed was register, is pointed at the wrong practice.
    """
    admin = await login(client, "tenant_admin")
    profile_id = await _mixed_profile(client, admin, "Register", [{
        "title": "Replies", "task_type": "response_selection",
        "item_count": 3, "prep_seconds": 0, "response_seconds": 0,
        "prompt_plays_allowed": 1, "allow_replay": False}])

    student = await login(client, "student")
    payload = (await client.post(
        "/api/v1/student/attempts", headers=auth(student),
        json={"profile_id": profile_id, "mode": "practice"})).json()
    attempt_id = payload["attempt_id"]

    for item in payload["items"]:
        assert (await client.post(
            f"/api/v1/student/attempts/{attempt_id}/responses/"
            f"{item['response_id']}/answer",
            headers=auth(student), json={"selected_index": 0})
        ).status_code == 201

    result = (await client.post(f"/api/v1/student/attempts/{attempt_id}/submit",
                                headers=auth(student), json={})).json()
    section = result["sections"][0]
    assert set(section["dimensions"]) == {"appropriacy"}, section["dimensions"]
    assert section["skill"] == "listening"


# -- vocabulary in context ---------------------------------------------------

def test_every_vocabulary_distractor_is_a_real_sense_of_the_word():
    """Context is the only discriminator, which is what makes it a reading item."""
    from app.selection_bank import VOCABULARY

    assert len(VOCABULARY) >= 8
    words = [word for _s, word, _senses, _c, _w in VOCABULARY]
    assert len(set(words)) < len(words), (
        "at least one word should appear twice in different senses -- that is "
        "the clearest demonstration that context decides")

    for sentence, word, senses, correct, why in VOCABULARY:
        assert word.lower() in sentence.lower(), (
            f"{word!r} is not in the sentence it is asked about")
        assert len(senses) >= 3
        assert 0 <= correct < len(senses)
        assert why.strip()


async def test_vocabulary_in_context_is_read_not_heard(client):
    """The sentence is the context and it is on the screen.

    Filed as reading rather than listening -- and if the classification were
    wrong the runner would withhold the sentence and ask about a word the
    candidate never saw.
    """
    admin = await login(client, "tenant_admin")
    profile_id = await _mixed_profile(client, admin, "Word sense", [{
        "title": "In context", "task_type": "vocabulary_in_context",
        "item_count": 4, "prep_seconds": 0, "response_seconds": 0,
        "prompt_plays_allowed": 0, "allow_replay": False}])

    student = await login(client, "student")
    payload = (await client.post(
        "/api/v1/student/attempts", headers=auth(student),
        json={"profile_id": profile_id, "mode": "practice"})).json()
    attempt_id = payload["attempt_id"]

    assert len(payload["items"]) == 4, "grouping would have starved this section"
    for item in payload["items"]:
        assert item["question"].strip(), "the sentence must be visible"
        assert "mean here" in item["question"]
        assert not item["has_prompt_audio"], "there is nothing to hear"
        assert len(item["options"]) >= 3

        assert (await client.post(
            f"/api/v1/student/attempts/{attempt_id}/responses/"
            f"{item['response_id']}/answer",
            headers=auth(student), json={"selected_index": 0})
        ).status_code == 201

    result = (await client.post(f"/api/v1/student/attempts/{attempt_id}/submit",
                                headers=auth(student), json={})).json()
    section = result["sections"][0]
    assert section["skill"] == "reading"
    assert set(section["dimensions"]) == {"vocabulary"}, section["dimensions"]


# -- passage reconstruction --------------------------------------------------

def test_the_reading_window_scales_with_the_passage():
    """A fixed clock would make the long passages a reading-speed test."""
    from app import reconstruction

    short = reconstruction.reading_seconds(20)
    long = reconstruction.reading_seconds(60)
    assert short < long
    assert reconstruction.MIN_READING_SECONDS <= short
    assert long <= reconstruction.MAX_READING_SECONDS
    # A passage of nothing still gets a usable window rather than zero.
    assert reconstruction.reading_seconds(0) >= reconstruction.MIN_READING_SECONDS


def test_reconstruction_credits_a_paraphrase():
    """The task asks for the ideas back, not the sentence back.

    A scorer matching the author's wording would mark a correct
    reconstruction wrong, which is the failure the cue lists exist to
    prevent -- and the one the writing bank already learned once.
    """
    from app.reconstruction import content_recall

    units = [("the review moved to Monday", ["monday"]),
             ("the scope is unchanged", ["scope", "nothing else"])]

    paraphrased = content_recall(
        "They pushed the review to Monday. Nothing else about it changed.",
        units)
    assert paraphrased.detail["covered"] == [u[0] for u in units], (
        paraphrased.detail)

    missed = content_recall("Something happened at some point.", units)
    assert missed.detail["missing"] == [u[0] for u in units]
    assert missed.score < paraphrased.score


def test_reconstruction_records_copying_without_punishing_it():
    """The passage is in the payload, so verbatim runs must be visible.

    Recorded and not scored: a threshold nobody has calibrated would charge a
    student who genuinely remembered a sentence well.
    """
    from app.reconstruction import verbatim_share

    source = ("The client has moved the review from Thursday to the following "
              "Monday and wants the draft two days before.")

    copied = verbatim_share(
        "The client has moved the review from Thursday to the following Monday",
        source)
    assert copied > 0.8, copied

    own_words = verbatim_share(
        "They pushed the review back and want the draft sooner.", source)
    assert own_words == 0.0, own_words

    # Too short to contain a run at all -- zero, not a division error.
    assert verbatim_share("Moved.", source) == 0.0


async def test_a_short_reconstruction_scores_low_rather_than_not_at_all():
    """The essay module's forty-word floor is wrong for this task.

    Writing fifteen words back from a fifty-word passage is a *partial*
    reconstruction, which is the observation the task exists to make.
    Refusing to score it would throw the measurement away.
    """
    from app import reconstruction
    from app.writing import MIN_WORDS_TO_SCORE

    units = [("the review moved to Monday", ["monday"]),
             ("the draft is due earlier", ["draft"]),
             ("the scope is unchanged", ["scope"])]
    source = "x " * 50

    fifteen = "The review is now on Monday and the draft is due earlier."
    assert len(fifteen.split()) < MIN_WORDS_TO_SCORE

    result = await reconstruction.score(fifteen, idea_units=units, source=source)
    assert not result.too_short, "an essay-length floor would refuse this"
    assert result.measures, "nothing was measured"

    recall = next(m for m in result.measures if m.name == "content_recall")
    assert recall.confidence > 0
    assert recall.detail["missing"] == ["the scope is unchanged"]

    # Three words, though, is not an attempt at the passage.
    nothing = await reconstruction.score("I forgot", idea_units=units,
                                         source=source)
    assert nothing.too_short
    assert nothing.measures == []


def test_the_reconstruction_bank_is_short_enough_to_hold():
    """Longer than working memory turns the task into note-taking speed."""
    from app.reconstruction_bank import PASSAGES

    assert len(PASSAGES) >= 6
    for title, passage, units in PASSAGES:
        words = len(passage.split())
        assert 30 <= words <= 70, f"{title} is {words} words"
        assert len(units) >= 3, title
        for point, cues in units:
            assert point.strip() and cues, f"{title}: {point} has no cues"
            # A cue the passage does not contain can never be matched by a
            # faithful reconstruction, so it would be a permanently missing
            # point that looks like a candidate's failure.
            assert any(cue in passage.lower() or cue.isdigit()
                       or any(c in passage.lower() for c in cue.split())
                       for cue in cues), f"{title}: no cue for {point!r} is in the passage"


async def test_a_reconstruction_passage_is_shown_then_taken_away(client):
    """Losing the passage is the measurement, not a UI flourish."""
    admin = await login(client, "tenant_admin")
    profile_id = await _mixed_profile(client, admin, "Reconstruct", [{
        "title": "Read and rebuild", "task_type": "passage_reconstruction",
        "item_count": 2, "prep_seconds": 0, "response_seconds": 0,
        "prompt_plays_allowed": 0, "allow_replay": False}])

    student = await login(client, "student")
    payload = (await client.post(
        "/api/v1/student/attempts", headers=auth(student),
        json={"profile_id": profile_id, "mode": "practice"})).json()

    assert len(payload["items"]) == 2, payload["items"]
    for item in payload["items"]:
        assert item["response_mode"] == "write"
        assert item["skill"] == "writing"
        assert item["stimulus_text"].strip(), "there is nothing to read"
        assert item["stimulus_seconds"] > 0, (
            "a passage that never disappears is a copying exercise")
        # The idea units are the answer. Sending them would let a candidate
        # write the list back and score full recall of a passage never read.
        assert item["key_points"] == [], item["key_points"]


async def test_reconstruction_scores_recall_and_form_separately(client):
    """Two different results must not arrive as one number."""
    admin = await login(client, "tenant_admin")
    profile_id = await _mixed_profile(client, admin, "Reconstruct marked", [{
        "title": "Rebuild", "task_type": "passage_reconstruction",
        "item_count": 2, "prep_seconds": 0, "response_seconds": 0,
        "prompt_plays_allowed": 0, "allow_replay": False}])

    student = await login(client, "student")
    payload = (await client.post(
        "/api/v1/student/attempts", headers=auth(student),
        json={"profile_id": profile_id, "mode": "practice"})).json()
    attempt_id = payload["attempt_id"]

    for item in payload["items"]:
        # Answered from what is on the screen, which is what a candidate who
        # remembered the passage would produce.
        marked = (await client.post(
            f"/api/v1/student/attempts/{attempt_id}/responses/"
            f"{item['response_id']}/answer",
            headers=auth(student),
            json={"text": item["stimulus_text"]})).json()
        assert marked["answered"]
        assert marked["verbatim_share"] > 0.5, (
            "an exact copy must be visible in the evidence")

    result = (await client.post(f"/api/v1/student/attempts/{attempt_id}/submit",
                                headers=auth(student), json={})).json()
    section = result["sections"][0]
    assert section["skill"] == "writing"
    assert set(section["dimensions"]) == {"content", "grammar"}, (
        section["dimensions"])
    # A faithful reconstruction is a good one, whatever else is recorded
    # about how faithful it was.
    assert section["dimensions"]["content"] >= 70.0, section["dimensions"]


# -- the bug the writing path had all along ----------------------------------

async def test_a_writing_section_actually_reaches_the_candidate(client):
    """Email Writing had never been run through an attempt.

    A WritingPrompt id is stored in `Response.quiz_item_id`, and the runner
    looked that id up in the QuizItem table only. The lookup missed, the loop
    skipped the item, and the section arrived at the result reporting that no
    answers had been given -- for a candidate who was never shown anything to
    answer.
    """
    admin = await login(client, "tenant_admin")
    profile_id = await _mixed_profile(client, admin, "Write an email", [{
        "title": "Email", "task_type": "email_writing", "item_count": 1,
        "prep_seconds": 0, "response_seconds": 0,
        "prompt_plays_allowed": 0, "allow_replay": False}])

    student = await login(client, "student")
    payload = (await client.post(
        "/api/v1/student/attempts", headers=auth(student),
        json={"profile_id": profile_id, "mode": "practice"})).json()

    assert payload["items"], "the writing section served nothing"
    item = payload["items"][0]
    assert item["response_mode"] == "write"
    assert item["question"].strip(), "there is nothing to write about"
    assert item["key_points"], "an email brief tells you what to cover"
    # A composing task, not a reconstruction: the brief stays on screen.
    assert item["stimulus_seconds"] == 0
    assert item["stimulus_text"].strip(), "there is no thread to reply to"
    # The brief is sent once. It used to arrive in `scenario` as well, which
    # printed it twice on the runner.
    assert item["scenario"] == "", "the brief was sent twice"


async def test_an_email_section_never_draws_a_reconstruction_passage(client):
    """Same table, different kinds, and not interchangeable."""
    admin = await login(client, "tenant_admin")
    profile_id = await _mixed_profile(client, admin, "Email only", [{
        "title": "Email", "task_type": "email_writing", "item_count": 3,
        "prep_seconds": 0, "response_seconds": 0,
        "prompt_plays_allowed": 0, "allow_replay": False}])

    student = await login(client, "student")
    payload = (await client.post(
        "/api/v1/student/attempts", headers=auth(student),
        json={"profile_id": profile_id, "mode": "practice"})).json()

    titles = {i["stimulus_title"] for i in payload["items"]}
    from app.reconstruction_bank import PASSAGES
    reconstruction_titles = {t for t, _p, _u in PASSAGES}
    assert not (titles & reconstruction_titles), (
        f"a reconstruction passage was served as an email brief: "
        f"{titles & reconstruction_titles}")


# -- everything together -----------------------------------------------------

async def test_a_mixed_assessment_covers_four_skills_and_the_new_types(client):
    """One attempt, all four skills, Phase 4 types alongside the old ones.

    The integration test the whole phase is for: three response modes, six
    task types, one lifecycle, and a rollup that names four skills.
    """
    admin = await login(client, "tenant_admin")
    profile_id = await _mixed_profile(client, admin, "All four", [
        {"title": "Replies", "task_type": "response_selection",
         "item_count": 2, "prep_seconds": 0, "response_seconds": 0,
         "prompt_plays_allowed": 1, "allow_replay": False},
        {"title": "Listening", "task_type": "listening_comprehension",
         "item_count": 3, "prep_seconds": 0, "response_seconds": 0,
         "prompt_plays_allowed": 1, "allow_replay": False},
        {"title": "Word sense", "task_type": "vocabulary_in_context",
         "item_count": 2, "prep_seconds": 0, "response_seconds": 0,
         "prompt_plays_allowed": 0, "allow_replay": False},
        {"title": "Reading", "task_type": "reading_comprehension",
         "item_count": 3, "prep_seconds": 0, "response_seconds": 0,
         "prompt_plays_allowed": 0, "allow_replay": False},
        {"title": "Gaps", "task_type": "sentence_completion",
         "item_count": 2, "prep_seconds": 0, "response_seconds": 0,
         "prompt_plays_allowed": 0, "allow_replay": False},
        {"title": "Rebuild", "task_type": "passage_reconstruction",
         "item_count": 1, "prep_seconds": 0, "response_seconds": 0,
         "prompt_plays_allowed": 0, "allow_replay": False},
    ])

    student = await login(client, "student")
    payload = (await client.post(
        "/api/v1/student/attempts", headers=auth(student),
        json={"profile_id": profile_id, "mode": "practice"})).json()
    attempt_id = payload["attempt_id"]

    served = {i["task_type"] for i in payload["items"]}
    assert served == {"response_selection", "listening_comprehension",
                      "vocabulary_in_context", "reading_comprehension",
                      "sentence_completion", "passage_reconstruction"}, served

    for item in payload["items"]:
        if item["has_prompt_audio"]:
            await client.post(
                f"/api/v1/student/attempts/{attempt_id}/responses/"
                f"{item['response_id']}/prompt", headers=auth(student), json={})
        if item["response_mode"] == "select":
            body = {"selected_index": 0}
        elif item["task_type"] == "sentence_completion":
            body = {"text": "because"}
        else:
            body = {"text": item["stimulus_text"] or "Nothing to say."}
        answered = await client.post(
            f"/api/v1/student/attempts/{attempt_id}/responses/"
            f"{item['response_id']}/answer", headers=auth(student), json=body)
        assert answered.status_code == 201, (item["task_type"], answered.text)

    result = (await client.post(f"/api/v1/student/attempts/{attempt_id}/submit",
                                headers=auth(student), json={})).json()

    skills = {s["skill"]: s["score"] for s in result["skills"]}
    assert set(skills) == {"listening", "reading", "writing"}, skills
    for skill, score in skills.items():
        assert score is not None, f"{skill} produced no score"
        assert 20.0 <= score <= 80.0, f"{skill} off the internal scale: {score}"

    # Every section produced the dimensions its task type declares.
    from app.evaluation import DIMENSIONS_BY_TASK
    for section in result["sections"]:
        declared = DIMENSIONS_BY_TASK[section["task_type"]]
        produced = set(section["dimensions"])
        assert produced <= declared, (section["task_type"], produced, declared)
        assert produced, f"{section['task_type']} produced nothing"


async def test_no_answer_key_reaches_the_client_for_any_phase_4_type(client):
    """One sweep over every new task type, checked against the real keys.

    Per-type assertions are easy to write and easy to write incompletely.
    This takes the actual answers out of the banks and looks for them in the
    payload, which catches a leak through a field nobody thought about.
    """
    from app.reconstruction_bank import PASSAGES
    from app.selection_bank import RESPONSES, VOCABULARY

    admin = await login(client, "tenant_admin")
    profile_id = await _mixed_profile(client, admin, "Key leak sweep", [
        {"title": "Replies", "task_type": "response_selection",
         "item_count": 3, "prep_seconds": 0, "response_seconds": 0,
         "prompt_plays_allowed": 1, "allow_replay": False},
        {"title": "Word sense", "task_type": "vocabulary_in_context",
         "item_count": 3, "prep_seconds": 0, "response_seconds": 0,
         "prompt_plays_allowed": 0, "allow_replay": False},
        {"title": "Rebuild", "task_type": "passage_reconstruction",
         "item_count": 2, "prep_seconds": 0, "response_seconds": 0,
         "prompt_plays_allowed": 0, "allow_replay": False},
        {"title": "Conversations", "task_type": "conversation_question",
         "item_count": 2, "prep_seconds": 0, "response_seconds": 30,
         "prompt_plays_allowed": 1, "allow_replay": False},
    ])

    student = await login(client, "student")
    payload = (await client.post(
        "/api/v1/student/attempts", headers=auth(student),
        json={"profile_id": profile_id, "mode": "practice"})).json()

    import json as _json
    wire = _json.dumps(payload).lower()

    # Nothing anywhere in the payload names which option is right.
    #
    # Checked as JSON *keys*, not as substrings of the whole payload. One of
    # the vocabulary distractors is "an explanation of a cost", so a scan for
    # the word "explanation" reports a leak that has not happened -- and a
    # test that fails on honest content is one somebody weakens rather than
    # reads.
    def keys_in(node):
        if isinstance(node, dict):
            for key, value in node.items():
                yield key
                yield from keys_in(value)
        elif isinstance(node, list):
            for value in node:
                yield from keys_in(value)

    present = set(keys_in(payload))
    for leaked in ("correct_index", "is_correct", "correct", "explanation",
                   "cues", "key_points_cues", "accepted", "reference_text",
                   "rubric", "transcript"):
        assert leaked not in present, f"{leaked} reached the client"

    # The spoken line behind a response-selection item is heard, never sent.
    for line, _replies, _correct, _why in RESPONSES:
        assert line.lower() not in wire, f"spoken line leaked: {line}"

    # The rationale behind a vocabulary item names the answer. Compared
    # against the option text as well, because one rationale is "Be in charge
    # of." and one option is "be in charge of" -- a bare substring check here
    # would fail on a payload that leaked nothing, and the next person to see
    # it would weaken the test rather than read it.
    options = {o.lower() for item in payload["items"] for o in item["options"]}
    for _s, _w, _senses, _c, why in VOCABULARY:
        needle = why.lower()
        if any(needle.strip(".") == option for option in options):
            continue
        assert needle not in wire, f"vocabulary rationale leaked: {why}"

    # A reconstruction's idea units are what the scorer marks against, and
    # they must not be sent -- but the passage itself must be, because
    # reading it is the task. So this checks the field rather than scanning
    # the payload for the words: an idea unit is written in the passage's own
    # vocabulary, so "she reports to Anil" appears in the passage it
    # describes and a substring scan flags a leak that has not happened. The
    # first version of this test did exactly that, and passed only on the
    # draws where no label happened to echo its passage.
    for item in payload["items"]:
        if item["task_type"] == "passage_reconstruction":
            assert item["key_points"] == [], (
                f"the answer was sent with the question: {item['key_points']}")

    # And a conversation question's exchange is played, not shipped. The
    # whole spoken text is scanned because it is long and unique; the rubric
    # points are not, and that distinction is the point.
    #
    # One rubric point is the sentence "the team is not growing", which is
    # also a sentence in the "Support hours" reconstruction passage -- and
    # that passage is *supposed* to be in the payload, because reading it is
    # the task. Scanning for the point flagged a leak that had not happened,
    # on the draws where both items happened to be served. The rubric reaches
    # the client through no field at all, which is what the key check above
    # already establishes, so this asserts the structure instead.
    from app.spoken_question_bank import ITEMS
    for _task, spoken, _rubric, _d in ITEMS:
        assert spoken.lower() not in wire, "the exchange leaked"
    for item in payload["items"]:
        if item["task_type"] in ("conversation_question", "passage_question"):
            assert item["prompt_text"] == "", "the exchange must be heard"
            assert item["question"] == ""
            assert item["stimulus_text"] == ""
            assert item["key_points"] == []


async def test_the_speaking_profiles_still_behave_exactly_as_before(client):
    """Nothing in Phase 4 may change what a speaking-only assessment does."""
    from app import formats

    admin = await login(client, "tenant_admin")
    profile_id = await _mixed_profile(client, admin, "Speaking unchanged", [
        {"title": "Read Aloud", "task_type": "read_aloud", "item_count": 2,
         "prep_seconds": 5, "response_seconds": 20,
         "prompt_plays_allowed": 0, "allow_replay": False},
        {"title": "Repeat", "task_type": "repeat_sentence", "item_count": 2,
         "prep_seconds": 0, "response_seconds": 15,
         "prompt_plays_allowed": 1, "allow_replay": False},
    ])

    student = await login(client, "student")
    payload = (await client.post(
        "/api/v1/student/attempts", headers=auth(student),
        json={"profile_id": profile_id, "mode": "practice"})).json()

    for item in payload["items"]:
        assert item["response_mode"] == "speak"
        assert item["skill"] == "speaking"
        assert item["options"] == []
        assert item["stimulus_seconds"] == 0
        if item["task_type"] == "read_aloud":
            assert item["prompt_text"], "read aloud shows its sentence"
        else:
            assert item["prompt_text"] == "", "repeat sentence withholds it"

    # The vendor blueprints are still assembled from task types the builder
    # accepts -- Phase 4 widened that set and must not have narrowed it.
    from app.schemas import TASK_TYPES
    for code, blueprint in formats.BY_CODE.items():
        for section in blueprint.sections:
            assert section.task_type in TASK_TYPES, (code, section.task_type)


# -- content for the two spoken-question types -------------------------------
#
# Scored above the frozen path, because the pipeline gates content on a set of
# three task types written before these two existed and that file cannot be
# edited without retiring the validation baseline. These tests are about the
# thing that makes that arrangement safe: the score must actually arrive, and
# arrive once.

async def _spoken_question_attempt(client, title):
    """An attempt on a conversation-question section, ready for transcripts."""
    admin = await login(client, "tenant_admin")
    profile_id = await _mixed_profile(client, admin, title, [{
        "title": "Conversations", "task_type": "conversation_question",
        "item_count": 2, "prep_seconds": 0, "response_seconds": 30,
        "prompt_plays_allowed": 1, "allow_replay": False}])
    student = await login(client, "student")
    payload = (await client.post(
        "/api/v1/student/attempts", headers=auth(student),
        json={"profile_id": profile_id, "mode": "practice"})).json()
    assert payload["items"], "no items were served"
    return student, payload


async def _transcribe(attempt_id, answers: dict[str, str]):
    """Write the FeatureRecords the engine would have written."""
    from app.models.tenant import FeatureRecord

    async with tenant_sessionmaker(SLUG)() as s:
        for response_id, text in answers.items():
            s.add(FeatureRecord(response_id=response_id, transcript=text))
        await s.commit()


async def _content_scores(attempt_id) -> dict[str, float]:
    from app.models.tenant import ScoreRecord

    async with tenant_sessionmaker(SLUG)() as s:
        rows = (await s.execute(
            select(ScoreRecord).where(ScoreRecord.attempt_id == attempt_id,
                                      ScoreRecord.dimension == "content")
        )).scalars().all()
        return {r.response_id: r.score for r in rows}


async def _run_content_scoring(attempt_id) -> int:
    from app import spoken_content
    from app.db import platform_sessionmaker
    from app.engine.registry import Providers

    async with tenant_sessionmaker(SLUG)() as tenant:
        async with platform_sessionmaker()() as platform:
            return await spoken_content.score_pending(
                tenant, Providers(platform), None, attempt_id)


async def test_a_spoken_question_gets_a_content_score_at_all(client):
    """The dimension the whole task type exists to produce.

    Without it, "answer the question you just heard" measures fluency and
    grammar and never whether the answer was right -- which is the one thing
    it was added to measure.
    """
    from app.models.tenant import Response, TaskItem

    student, payload = await _spoken_question_attempt(client, "Content lands")
    attempt_id = payload["attempt_id"]

    # Answer the first item well and the second with something off-topic, so
    # a scorer that returns one number for everything is visible.
    async with tenant_sessionmaker(SLUG)() as s:
        rows = (await s.execute(
            select(Response).where(Response.attempt_id == attempt_id)
            .order_by(Response.position))).scalars().all()
        items = {r.id: (await s.get(TaskItem, r.item_id)) for r in rows}

    ordered = list(items)
    good_id, poor_id = ordered[0], ordered[1]
    good_points = list(items[good_id].rubric["key_points"])

    await _transcribe(attempt_id, {
        good_id: " ".join(good_points) + " that is what they said",
        poor_id: "I did not really catch any of that sorry about it",
    })

    added = await _run_content_scoring(attempt_id)
    assert added == 2, f"expected two content scores, got {added}"

    scores = await _content_scores(attempt_id)
    assert set(scores) == {good_id, poor_id}
    assert scores[good_id] > scores[poor_id], scores
    assert scores[poor_id] >= 20.0, "the internal floor is 20, never zero"


async def test_content_scoring_is_idempotent(client):
    """Submit retries, and a second run must not stack a second score."""
    from app.models.tenant import Response

    student, payload = await _spoken_question_attempt(client, "Content once")
    attempt_id = payload["attempt_id"]

    async with tenant_sessionmaker(SLUG)() as s:
        rows = (await s.execute(
            select(Response).where(Response.attempt_id == attempt_id)
        )).scalars().all()

    await _transcribe(attempt_id, {r.id: "they agreed to confirm by Friday"
                                   for r in rows})

    first = await _run_content_scoring(attempt_id)
    second = await _run_content_scoring(attempt_id)
    assert first == len(rows), first
    assert second == 0, "a retry added a second content score"


async def test_an_unheard_answer_gets_no_content_score_rather_than_zero(client):
    """A failed transcription is a fact about the recording, not the candidate.

    Scoring it as nought would tell a student they understood nothing, when
    what happened is that the engine heard nothing.
    """
    student, payload = await _spoken_question_attempt(client, "Nothing heard")
    attempt_id = payload["attempt_id"]

    # No FeatureRecords at all -- the engine never got that far.
    assert await _run_content_scoring(attempt_id) == 0
    assert await _content_scores(attempt_id) == {}

    # And an empty transcript is the same thing.
    from app.models.tenant import Response
    async with tenant_sessionmaker(SLUG)() as s:
        rows = (await s.execute(
            select(Response).where(Response.attempt_id == attempt_id)
        )).scalars().all()
    await _transcribe(attempt_id, {r.id: "   " for r in rows})
    assert await _run_content_scoring(attempt_id) == 0
    assert await _content_scores(attempt_id) == {}


async def test_a_skipped_spoken_question_is_not_scored(client):
    """Skipped means the student did not answer. It is not a wrong answer."""
    from app.models.tenant import Response

    student, payload = await _spoken_question_attempt(client, "Skipped")
    attempt_id = payload["attempt_id"]

    for item in payload["items"]:
        skipped = await client.post(
            f"/api/v1/student/attempts/{attempt_id}/responses/"
            f"{item['response_id']}/skip", headers=auth(student), json={})
        assert skipped.status_code == 200

    async with tenant_sessionmaker(SLUG)() as s:
        rows = (await s.execute(
            select(Response).where(Response.attempt_id == attempt_id)
        )).scalars().all()
    await _transcribe(attempt_id, {r.id: "something said anyway" for r in rows})

    assert await _run_content_scoring(attempt_id) == 0


def test_the_content_gate_the_pipeline_uses_still_excludes_these_types():
    """The reason app/spoken_content.py exists, asserted rather than assumed.

    If a later baseline moves these two names into the pipeline's own gate,
    this test fails -- and that is the signal to delete the module rather
    than score content twice.
    """
    import inspect

    from app.engine import pipeline
    from app.spoken_content import SCORED_HERE

    source = inspect.getsource(pipeline.score_response)
    gate = source.split("Capability.CONTENT_RELEVANCE")[0]
    for task_type in SCORED_HERE:
        assert task_type not in gate, (
            f"{task_type} is now scored by the pipeline as well -- "
            f"app/spoken_content.py must be removed")

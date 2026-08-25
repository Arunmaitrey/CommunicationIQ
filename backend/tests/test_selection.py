"""Pool filters, difficulty mixes and the bank classification.

Phase 6. The unit half is deliberately pure: ``app.selection`` takes lists and
returns lists, seeded by a ``random.Random`` the test owns, so a distribution
can be asserted rather than hoped for. The greedy whole-passage selector
misfired on roughly one shuffle in six and survived a passing end-to-end test;
nothing here can repeat that.

The integration half goes through the real database, because the questions
that matter -- does a filter narrow the pool, does the guard notice when it
narrows it to nothing, does an unconfigured section behave exactly as before
-- are about rows, not about dataclasses.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from sqlalchemy import select

from app import selection
from app.db import tenant_sessionmaker
from app.models.tenant import SimulationProfile, TaskItem

from tests.test_game_and_practice import SLUG, auth, login


@dataclass
class Item:
    """Enough of a TaskItem for the pure functions."""

    id: str = "x"
    difficulty: float = 0.0
    topic: str = ""
    role: str = ""
    industry: str = ""
    language: str = ""


def bank(*specs) -> list[Item]:
    return [Item(id=f"i{n}", **spec) for n, spec in enumerate(specs)]


# -- the empty filter is the old behaviour ----------------------------------

def test_an_unconfigured_section_selects_exactly_what_it_used_to():
    """The property everything else depends on.

    Every seeded profile, every template and every speaking-only assessment
    stores no filter. If the empty filter narrowed anything at all, Phase 6
    would have changed the results of assessments nobody touched.
    """
    items = bank({"difficulty": -2.0, "industry": "banking"},
                 {"difficulty": 0.0},
                 {"difficulty": 3.0, "language": "fr", "role": "developer"})

    assert not selection.EMPTY.configured
    assert selection.eligible(items, selection.EMPTY) == items
    assert selection.from_dict({}) == selection.EMPTY
    assert selection.from_dict(None) == selection.EMPTY
    assert selection.to_dict(selection.EMPTY) == {}

    drawn = selection.draw(items, 3, selection.EMPTY, random.Random(1))
    assert len(drawn.items) == 3
    assert not drawn.shortfalls


def test_an_unclassified_item_stays_eligible_under_every_filter():
    """The bank was authored before these columns existed.

    Excluding untagged items would turn one optional filter into a mandatory
    tagging exercise across a hundred items, and the first admin to tick
    "banking" would get an empty section.
    """
    untagged = Item(id="old")
    filtered = selection.from_dict(
        {"industries": ["banking"], "roles": ["teller"], "topics": ["kyc"],
         "languages": ["en"]})
    assert selection.matches(untagged, filtered)


def test_general_material_belongs_to_every_vertical():
    """A banking round built only from banking sentences is a five-item test."""
    general = Item(id="g", industry="general")
    banking = Item(id="b", industry="banking")
    retail = Item(id="r", industry="retail")

    wanted = selection.from_dict({"industries": ["banking"]})
    assert selection.eligible([general, banking, retail], wanted) == [general, banking]


# -- filters ----------------------------------------------------------------

def test_difficulty_bounds_are_inclusive_and_independent():
    items = bank({"difficulty": -1.0}, {"difficulty": 0.0}, {"difficulty": 1.0})

    only_low = selection.from_dict({"difficulty_max": 0.0})
    assert [i.difficulty for i in selection.eligible(items, only_low)] == [-1.0, 0.0]

    only_high = selection.from_dict({"difficulty_min": 0.0})
    assert [i.difficulty for i in selection.eligible(items, only_high)] == [0.0, 1.0]

    both = selection.from_dict({"difficulty_min": -0.5, "difficulty_max": 0.5})
    assert [i.difficulty for i in selection.eligible(items, both)] == [0.0]


def test_filters_combine_as_and_not_or():
    """Two filters narrow. An item satisfying one and failing the other is out
    -- an admin who asked for hard banking items did not ask for easy banking
    items as well."""
    items = bank({"industry": "banking", "difficulty": 1.0},
                 {"industry": "banking", "difficulty": -1.0},
                 {"industry": "it", "difficulty": 1.0})

    wanted = selection.from_dict({"industries": ["banking"], "difficulty_min": 0.5})
    kept = selection.eligible(items, wanted)
    assert len(kept) == 1
    assert kept[0].industry == "banking" and kept[0].difficulty == 1.0


def test_a_filter_a_bank_cannot_honour_is_named_rather_than_ignored():
    """Only TaskItem carries the classification columns.

    A listening section filtered by industry would match nothing and serve an
    empty section, and the admin would never learn why. This is the check the
    builder and the publish guard both use.
    """
    industry = selection.from_dict({"industries": ["bpo"]})
    assert industry.unsupported_for("task") == []
    assert industry.unsupported_for("quiz") == ["industries"]
    assert industry.unsupported_for("writing_prompt") == ["industries"]

    # Difficulty is on every bank, so it is supported everywhere.
    hard = selection.from_dict({"difficulty_min": 0.5})
    for kind in ("task", "quiz", "writing_prompt"):
        assert hard.unsupported_for(kind) == []


def test_a_misspelled_filter_is_an_error_not_a_no_op():
    """Otherwise the section selects on everything except the thing the admin
    typed, and the result looks like a working assessment."""
    import pytest

    with pytest.raises(ValueError, match="unknown selection filter"):
        selection.from_dict({"industrys": ["bpo"]})
    with pytest.raises(ValueError, match="unknown difficulty band"):
        selection.from_dict({"mix": {"very hard": 1}})


def test_a_filter_survives_a_round_trip_through_storage():
    original = {"industries": ["bpo", "it"], "difficulty_min": 0.2,
                "mix": {"hard": 2.0, "easy": 1.0}, "min_pool": 12}
    back = selection.to_dict(selection.from_dict(original))
    assert back == original


# -- difficulty bands and the mix -------------------------------------------

def test_the_bands_split_the_live_bank_rather_than_the_number_line():
    """Round edges would have put four fifths of the bank in "medium" and made
    the mix control a decoration. These come from the bank's own terciles."""
    assert selection.band_of(-0.5) == "easy"
    assert selection.band_of(0.0) == "medium"
    assert selection.band_of(0.9) == "hard"
    # The edges themselves, stated so a change to them is deliberate.
    assert selection.band_of(selection.EASY_BELOW) == "medium"
    assert selection.band_of(selection.HARD_FROM) == "hard"


def _bands(items) -> dict[str, int]:
    out: dict[str, int] = {}
    for item in items:
        band = selection.band_of(item.difficulty)
        out[band] = out.get(band, 0) + 1
    return out


def test_a_mix_is_honoured_exactly_when_the_bank_can_supply_it():
    """Deterministic, and about counts rather than averages."""
    items = bank(*([{"difficulty": -1.0}] * 10
                   + [{"difficulty": 0.0}] * 10
                   + [{"difficulty": 1.0}] * 10))

    drawn = selection.draw(items, 10,
                           selection.from_dict({"mix": {"easy": 2, "medium": 5,
                                                        "hard": 3}}),
                           random.Random(7))
    assert len(drawn.items) == 10
    assert _bands(drawn.items) == {"easy": 2, "medium": 5, "hard": 3}
    assert not drawn.shortfalls


def test_a_mix_that_does_not_divide_evenly_still_sums_to_the_asked_count():
    """Rounding each share down loses items. Largest remainder does not."""
    items = bank(*([{"difficulty": -1.0}] * 10
                   + [{"difficulty": 0.0}] * 10
                   + [{"difficulty": 1.0}] * 10))

    for count in range(1, 12):
        drawn = selection.draw(
            items, count,
            selection.from_dict({"mix": {"easy": 1, "medium": 1, "hard": 1}}),
            random.Random(count))
        assert len(drawn.items) == count, count


def test_a_bank_that_cannot_supply_the_mix_says_so_and_fills_the_section():
    """A short section is a worse measurement than a differently-shaped one --
    but the admin has to be told, because the test they configured is not the
    test that ran."""
    items = bank(*([{"difficulty": -1.0}] * 8 + [{"difficulty": 1.0}] * 2))

    drawn = selection.draw(items, 6,
                           selection.from_dict({"mix": {"hard": 1}}),
                           random.Random(3))
    assert len(drawn.items) == 6, "the section must still be filled"
    assert drawn.shortfalls == {"hard": 4}
    assert "could not supply" in drawn.note
    # Two hard items exist and both were taken before falling back.
    assert _bands(drawn.items)["hard"] == 2


def test_a_draw_never_repeats_an_item():
    """Including on the top-up path, which is where a duplicate would come
    from: a band pick and a fallback pick can reach for the same row."""
    items = bank(*([{"difficulty": -1.0}] * 3 + [{"difficulty": 1.0}] * 3))

    for seed in range(25):
        drawn = selection.draw(
            items, 6, selection.from_dict({"mix": {"hard": 5, "easy": 1}}),
            random.Random(seed))
        ids = [i.id for i in drawn.items]
        assert len(ids) == len(set(ids)), (seed, ids)
        assert len(ids) == 6


def test_asking_for_more_than_exists_returns_what_exists():
    items = bank({"difficulty": 0.0}, {"difficulty": 0.0})
    assert len(selection.draw(items, 9, selection.EMPTY, random.Random(1)).items) == 2
    mixed = selection.draw(items, 9, selection.from_dict({"mix": {"hard": 1}}),
                           random.Random(1))
    assert len(mixed.items) == 2


def test_an_empty_pool_draws_nothing_rather_than_failing():
    assert selection.draw([], 5, selection.EMPTY).items == []
    assert selection.draw(bank({"difficulty": 0.0}), 0, selection.EMPTY).items == []


# -- against the real bank ---------------------------------------------------

async def test_the_seeded_bank_is_classified_with_what_is_known(client):
    """Language and industry were backfilled because they are true of every
    item. Topic and role were not: nobody decided them when the items were
    written, and a guess in a column an admin will filter on is worse than an
    empty one.
    """
    async with tenant_sessionmaker(SLUG)() as session:
        rows = (await session.execute(
            select(TaskItem).where(TaskItem.status == "published")
        )).scalars().all()

    assert rows
    assert all(r.language == "en" for r in rows), "every item is English"
    assert all(r.industry for r in rows), "every item has an industry or general"
    assert all(selection.known_industry(r.industry) for r in rows)

    specific = [r for r in rows if r.industry != selection.GENERAL_INDUSTRY]
    assert len(specific) >= 20, "the filter needs something to discriminate on"
    assert {r.industry for r in specific} >= {"bpo", "it", "banking"}
    # The industry items were authored with a role and a topic; the older bank
    # deliberately has neither.
    assert all(r.role and r.topic for r in specific)


async def test_an_industry_filter_narrows_the_real_bank_without_emptying_it(client):
    async with tenant_sessionmaker(SLUG)() as session:
        items = list((await session.execute(
            select(TaskItem).where(TaskItem.task_type == "read_aloud",
                                   TaskItem.status == "published")
        )).scalars().all())

    banking = selection.eligible(
        items, selection.from_dict({"industries": ["banking"]}), "task")
    assert banking, "a banking filter emptied the read-aloud bank"
    assert len(banking) < len(items), "the filter narrowed nothing"
    kept = {i.industry for i in banking}
    assert kept <= {"banking", selection.GENERAL_INDUSTRY}, kept
    assert "banking" in kept, "no genuinely banking item survived"


# --------------------------------------------------------------------------
# Builder -> persistence -> selection -> attempt
# --------------------------------------------------------------------------

def _section(task_type="read_aloud", **kw):
    base = {"title": kw.pop("title", "Section"), "task_type": task_type,
            "item_count": 4, "prep_seconds": 0, "response_seconds": 20,
            "prompt_plays_allowed": 0, "allow_replay": False}
    base.update(kw)
    return base


async def _build(client, admin, name, sections, **profile):
    body = {"name": name, "style": "company_round", "company": "Testco",
            "description": "x", "estimated_minutes": 10, "sections": sections}
    body.update(profile)
    return await client.post("/api/v1/tenant/profiles", headers=auth(admin),
                             json=body)


async def test_every_configured_value_survives_a_save_and_a_read(client):
    """Storing a value that no serialiser returns is how `scoring_weights`
    spent months looking like a feature. Every field the builder accepts has
    to come back."""
    admin = await login(client, "tenant_admin")
    created = await _build(
        client, admin, "Configured round",
        [_section(selection={"industries": ["banking"], "mix": {"hard": 1},
                             "min_pool": 5})],
        scoring_weights={"pronunciation": 0.5, "fluency": 0.5},
        pass_threshold=55.0,
        skill_thresholds={"pronunciation": 40.0},
        target_role="teller", department="operations", difficulty_band="B2")
    assert created.status_code == 201, created.text
    body = created.json()

    assert body["scoring_weights"] == {"pronunciation": 0.5, "fluency": 0.5}
    assert body["pass_threshold"] == 55.0
    assert body["skill_thresholds"] == {"pronunciation": 40.0}
    assert body["target_role"] == "teller"
    assert body["department"] == "operations"
    assert body["difficulty_band"] == "B2"
    assert body["sections"][0]["selection"] == {
        "industries": ["banking"], "mix": {"hard": 1.0}, "min_pool": 5}


async def test_cloning_a_round_keeps_its_pass_mark(client):
    """Cloning is the supported way to edit a round students have sat.

    It copied `scoring_weights` and nothing else, so the copy of a hiring
    round had no pass mark, no floors and no classification -- and passed
    everybody while looking identical.
    """
    admin = await login(client, "tenant_admin")
    created = (await _build(
        client, admin, "Clone me", [_section()],
        pass_threshold=60.0, skill_thresholds={"fluency": 45.0},
        target_role="agent", department="support",
        difficulty_band="B1")).json()

    clone = await client.post(
        f"/api/v1/tenant/profiles/{created['id']}/clone",
        headers=auth(admin), json={})
    assert clone.status_code == 201, clone.text
    copy = clone.json()

    assert copy["pass_threshold"] == 60.0
    assert copy["skill_thresholds"] == {"fluency": 45.0}
    assert copy["target_role"] == "agent"
    assert copy["department"] == "support"
    assert copy["difficulty_band"] == "B1"


async def test_a_filter_the_bank_cannot_honour_is_refused_at_build_time(client):
    """A listening section filtered by industry would match nothing. Better a
    validation error than an empty section nobody can explain."""
    admin = await login(client, "tenant_admin")
    refused = await _build(client, admin, "Impossible filter", [
        _section("listening_comprehension", response_seconds=0,
                 prompt_plays_allowed=1,
                 selection={"industries": ["bpo"]})])
    assert refused.status_code == 422, refused.text
    assert "industries" in refused.text

    # The same filter on a speaking section is fine.
    fine = await _build(client, admin, "Possible filter",
                        [_section(selection={"industries": ["bpo"]})])
    assert fine.status_code == 201, fine.text


async def test_an_unknown_industry_is_refused_with_the_list(client):
    """An admin who typed "finance" should be told what the values are, not
    handed a section that silently matches nothing."""
    admin = await login(client, "tenant_admin")
    refused = await _build(client, admin, "Bad industry",
                           [_section(selection={"industries": ["finance"]})])
    assert refused.status_code == 422
    assert "banking" in refused.text, "the error must name the known values"


async def test_a_backwards_difficulty_range_is_refused(client):
    admin = await login(client, "tenant_admin")
    refused = await _build(client, admin, "Backwards range", [
        _section(selection={"difficulty_min": 1.0, "difficulty_max": -1.0})])
    assert refused.status_code == 422


async def test_a_filter_that_empties_the_bank_blocks_publishing(client):
    """The publish guard counted the whole bank. A filter that matches nothing
    would have sailed through it and dropped the section at attempt start --
    the same silent truncation the guard exists to prevent, arriving through a
    new door.
    """
    admin = await login(client, "tenant_admin")
    created = (await _build(client, admin, "Empty filter", [
        # Nothing in the bank is this hard.
        _section(selection={"difficulty_min": 2.9})])).json()

    refused = await client.post(
        f"/api/v1/tenant/profiles/{created['id']}/status",
        headers=auth(admin), json={"status": "published"})
    assert refused.status_code == 400, refused.text
    assert "matching the filter" in refused.text


async def test_a_pool_floor_blocks_publishing_when_variety_is_too_thin(client):
    """A bank the size of the section serves the same test on every retake."""
    admin = await login(client, "tenant_admin")
    created = (await _build(client, admin, "Thin pool", [
        _section(selection={"industries": ["banking"], "min_pool": 500})
    ])).json()

    refused = await client.post(
        f"/api/v1/tenant/profiles/{created['id']}/status",
        headers=auth(admin), json={"status": "published"})
    assert refused.status_code == 400, refused.text
    assert "retake would repeat" in refused.text


async def test_a_filtered_section_serves_only_eligible_items(client):
    """Persistence through to the runner payload: the end of the chain."""
    from app.db import tenant_sessionmaker
    from app.models.tenant import Response, TaskItem
    from sqlalchemy import select

    from tests.test_game_and_practice import SLUG

    admin = await login(client, "tenant_admin")
    created = (await _build(client, admin, "Banking round", [
        _section(title="Read Aloud", item_count=6,
                 selection={"industries": ["banking"]})])).json()
    published = await client.post(
        f"/api/v1/tenant/profiles/{created['id']}/status",
        headers=auth(admin), json={"status": "published"})
    assert published.status_code == 200, published.text

    student = await login(client, "student")
    payload = (await client.post(
        "/api/v1/student/attempts", headers=auth(student),
        json={"profile_id": created["id"], "mode": "practice"})).json()
    assert len(payload["items"]) == 6

    async with tenant_sessionmaker(SLUG)() as session:
        rows = (await session.execute(
            select(Response.item_id).where(
                Response.attempt_id == payload["attempt_id"]))).scalars().all()
        items = (await session.execute(
            select(TaskItem).where(TaskItem.id.in_(list(rows))))).scalars().all()

    industries = {i.industry for i in items}
    assert industries <= {"banking", "general"}, industries


async def test_a_difficulty_mix_reaches_the_items_a_candidate_is_served(client):
    """Storing the configuration is not honouring it."""
    from app.db import tenant_sessionmaker
    from app.models.tenant import Response, TaskItem
    from app.selection import band_of
    from sqlalchemy import select

    from tests.test_game_and_practice import SLUG

    admin = await login(client, "tenant_admin")
    created = (await _build(client, admin, "Hard only", [
        _section(title="Read Aloud", item_count=5,
                 selection={"mix": {"hard": 1}})])).json()
    await client.post(f"/api/v1/tenant/profiles/{created['id']}/status",
                      headers=auth(admin), json={"status": "published"})

    student = await login(client, "student")
    payload = (await client.post(
        "/api/v1/student/attempts", headers=auth(student),
        json={"profile_id": created["id"], "mode": "practice"})).json()

    async with tenant_sessionmaker(SLUG)() as session:
        rows = (await session.execute(
            select(Response.item_id).where(
                Response.attempt_id == payload["attempt_id"]))).scalars().all()
        items = (await session.execute(
            select(TaskItem).where(TaskItem.id.in_(list(rows))))).scalars().all()

    assert len(items) == 5
    assert all(band_of(i.difficulty) == "hard" for i in items), (
        [(i.difficulty, band_of(i.difficulty)) for i in items])


async def test_a_mix_never_serves_an_unpublished_item(client):
    """The filters narrow a pool that was already restricted to published
    items. A new code path that rebuilt the query could lose that."""
    from app.db import tenant_sessionmaker
    from app.models.tenant import Response, TaskItem
    from sqlalchemy import select

    from tests.test_game_and_practice import SLUG

    admin = await login(client, "tenant_admin")
    created = (await _build(client, admin, "Published only", [
        _section(title="Read Aloud", item_count=8,
                 selection={"mix": {"easy": 1, "hard": 1}})])).json()
    await client.post(f"/api/v1/tenant/profiles/{created['id']}/status",
                      headers=auth(admin), json={"status": "published"})

    student = await login(client, "student")
    payload = (await client.post(
        "/api/v1/student/attempts", headers=auth(student),
        json={"profile_id": created["id"], "mode": "practice"})).json()

    async with tenant_sessionmaker(SLUG)() as session:
        rows = (await session.execute(
            select(Response.item_id).where(
                Response.attempt_id == payload["attempt_id"]))).scalars().all()
        items = (await session.execute(
            select(TaskItem).where(TaskItem.id.in_(list(rows))))).scalars().all()

    assert items
    assert all(i.status == "published" for i in items)
    assert len({i.id for i in items}) == len(items), "an item was served twice"


async def test_whole_passage_grouping_survives_a_difficulty_filter(client):
    """Filtering questions and grouping afterwards would hand a candidate
    three of a passage's four questions and call it a listening event."""
    from app.db import tenant_sessionmaker
    from app.models.tenant import QuizItem, Response
    from sqlalchemy import select

    from tests.test_game_and_practice import SLUG

    admin = await login(client, "tenant_admin")
    created = (await _build(client, admin, "Filtered listening", [
        _section("listening_comprehension", title="Listening", item_count=3,
                 response_seconds=0, prompt_plays_allowed=1,
                 selection={"difficulty_max": 3.0})])).json()
    published = await client.post(
        f"/api/v1/tenant/profiles/{created['id']}/status",
        headers=auth(admin), json={"status": "published"})
    assert published.status_code == 200, published.text

    student = await login(client, "student")
    payload = (await client.post(
        "/api/v1/student/attempts", headers=auth(student),
        json={"profile_id": created["id"], "mode": "practice"})).json()

    async with tenant_sessionmaker(SLUG)() as session:
        rows = (await session.execute(
            select(Response.quiz_item_id).where(
                Response.attempt_id == payload["attempt_id"]))).scalars().all()
        questions = (await session.execute(
            select(QuizItem).where(QuizItem.id.in_([r for r in rows if r]))
        )).scalars().all()
        served = {q.passage_id for q in questions}
        whole = (await session.execute(
            select(QuizItem.passage_id, func_count())
            .where(QuizItem.passage_id.in_(list(served)),
                   QuizItem.category == "audio_comprehension",
                   QuizItem.status == "published")
            .group_by(QuizItem.passage_id))).all()

    by_passage: dict[str, int] = {}
    for q in questions:
        by_passage[q.passage_id] = by_passage.get(q.passage_id, 0) + 1
    for passage_id, total in whole:
        assert by_passage[passage_id] == total, (
            f"passage {passage_id} was split: served {by_passage[passage_id]} "
            f"of {total}")


def func_count():
    from sqlalchemy import func
    return func.count()


async def test_the_existing_templates_are_all_still_buildable(client):
    """Phase 6 added optional filters. If any of them had become mandatory,
    or if the guard had started counting differently, the four templates and
    the company rounds would stop publishing.

    Scoped to the profiles that came from a blueprint, not to every published
    row. The suite itself creates published profiles -- including, on purpose,
    ones with impossible filters -- so "every published profile is buildable"
    is a claim about whatever the last test left behind rather than about the
    product. The shipped assessments are the ones this is about.
    """
    from app import formats
    from app.db import tenant_sessionmaker
    from app.routers.tenant_writes import _sections_without_items
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from tests.test_game_and_practice import SLUG

    async with tenant_sessionmaker(SLUG)() as session:
        profiles = (await session.execute(
            select(SimulationProfile)
            .where(SimulationProfile.code.in_(sorted(formats.BY_CODE)),
                   SimulationProfile.status == "published")
            .options(selectinload(SimulationProfile.sections))
        )).scalars().all()

        seen = {p.code for p in profiles}
        missing = set(formats.BY_CODE) - seen
        assert not missing, f"blueprinted profiles not seeded: {sorted(missing)}"

        for profile in profiles:
            assert profile.sections, f"{profile.code} has no sections"
            problems = await _sections_without_items(session, profile)
            assert not problems, f"{profile.code}: {problems}"


async def test_a_speaking_only_assessment_is_untouched_by_phase_6(client):
    """No filter configured, so nothing changes: same modes, same counts, no
    answer keys, and the section still fills."""
    admin = await login(client, "tenant_admin")
    created = (await _build(client, admin, "Unchanged speaking", [
        _section(title="Read Aloud", item_count=3),
        _section("repeat_sentence", title="Repeat", item_count=3,
                 response_seconds=15, prompt_plays_allowed=1)])).json()
    await client.post(f"/api/v1/tenant/profiles/{created['id']}/status",
                      headers=auth(admin), json={"status": "published"})

    assert all(s["selection"] == {} for s in created["sections"])

    student = await login(client, "student")
    payload = (await client.post(
        "/api/v1/student/attempts", headers=auth(student),
        json={"profile_id": created["id"], "mode": "practice"})).json()

    assert len(payload["items"]) == 6
    assert all(i["response_mode"] == "speak" for i in payload["items"])
    assert all(i["options"] == [] for i in payload["items"])
    read = [i for i in payload["items"] if i["task_type"] == "read_aloud"]
    repeat = [i for i in payload["items"] if i["task_type"] == "repeat_sentence"]
    assert all(i["prompt_text"] for i in read), "read aloud shows its sentence"
    assert all(i["prompt_text"] == "" for i in repeat), "repeat withholds it"


async def test_a_filtered_section_still_ships_no_answer_key(client):
    """Filtering changes which items are served, never what is sent about
    them."""
    import json as _json

    admin = await login(client, "tenant_admin")
    created = (await _build(client, admin, "Filtered secrecy", [
        _section("short_answer", title="Short Answer", item_count=3,
                 response_seconds=10, prompt_plays_allowed=1,
                 selection={"industries": ["bpo"]})])).json()
    await client.post(f"/api/v1/tenant/profiles/{created['id']}/status",
                      headers=auth(admin), json={"status": "published"})

    student = await login(client, "student")
    payload = (await client.post(
        "/api/v1/student/attempts", headers=auth(student),
        json={"profile_id": created["id"], "mode": "practice"})).json()

    wire = _json.dumps(payload)
    # Field names, not values: `key_points` is part of the RunnerItem schema
    # and is present on every item -- what matters is that it is empty for a
    # task type whose rubric is the answer key. Asserting on the name alone
    # fails on a payload that leaked nothing, which is a test somebody
    # weakens rather than reads.
    for leaked in ("rubric", "reference_text", "correct_index"):
        assert leaked not in wire, f"{leaked} reached the client"
    for item in payload["items"]:
        assert item["key_points"] == [], (
            "a short answer's accepted words are its answer key")
        assert item["options"] == []
        # The question is heard, never shown.
        assert item["prompt_text"] == ""
        assert item["question"] == ""


async def test_a_section_weight_travels_from_the_builder_to_the_rollup(client):
    """The whole trace, because every link in it was individually plausible.

    `SectionResult.weight` existed and was stored. The rollup read it and
    weighted by it. The builder had a scoring panel. And the number was always
    1.0, because `finalise` looked the section's *task type* up in
    `scoring_weights`, which is keyed by *dimension*. Nothing was missing --
    the lookup simply never hit, and no test asked what the weight came out as.

    So this asserts the value, at every stop, rather than that each part
    exists.
    """
    from sqlalchemy import select

    from app.db import tenant_sessionmaker
    from app.models.tenant import ProfileSection

    admin = await login(client, "tenant_admin")
    created = (await client.post(
        "/api/v1/tenant/profiles", headers=auth(admin),
        json={"name": "Weighted round", "style": "company_round",
              "company": "Testco", "description": "x", "estimated_minutes": 10,
              "sections": [
                  {"title": "Warm-up", "task_type": "read_aloud",
                   "item_count": 1, "prep_seconds": 0, "response_seconds": 20,
                   "prompt_plays_allowed": 0, "allow_replay": False,
                   "weight": 0.0},
                  {"title": "The real one", "task_type": "read_aloud",
                   "item_count": 1, "prep_seconds": 0, "response_seconds": 20,
                   "prompt_plays_allowed": 0, "allow_replay": False,
                   "weight": 3.0}]})).json()

    # 1. Persisted.
    async with tenant_sessionmaker(SLUG)() as session:
        rows = sorted((await session.execute(
            select(ProfileSection).where(
                ProfileSection.profile_id == created["id"]))).scalars().all(),
            key=lambda s: s.position)
    assert [r.weight for r in rows] == [0.0, 3.0], (
        "the builder's weights did not reach the database")

    # 2. Read back, so an admin can see and edit what they configured.
    listed = (await client.get("/api/v1/tenant/profiles",
                               headers=auth(admin))).json()
    fetched = next(p for p in listed if p["id"] == created["id"])
    assert [s["weight"] for s in fetched["sections"]] == [0.0, 3.0], (
        "stored but not returned -- which is how a field becomes uneditable")

    # 3. And a default is a default, not a blank.
    plain = (await client.post(
        "/api/v1/tenant/profiles", headers=auth(admin),
        json={"name": "Unweighted round", "style": "company_round",
              "company": "Testco", "description": "x", "estimated_minutes": 10,
              "sections": [{"title": "One", "task_type": "read_aloud",
                            "item_count": 1, "prep_seconds": 0,
                            "response_seconds": 20,
                            "prompt_plays_allowed": 0,
                            "allow_replay": False}]})).json()
    assert plain["sections"][0]["weight"] == 1.0, (
        "an unconfigured section must roll up evenly, not at zero")


async def test_the_rollup_actually_uses_the_section_weight():
    """Arithmetic, at the level the weight is applied.

    Kept separate from the trace above because this is the part that has to be
    right rather than merely wired: a weight that reaches the rollup and is
    then averaged away is the same bug in a different place.
    """
    from app.sections import SectionScore, roll_up

    even = roll_up([
        SectionScore(section_id="a", position=1, title="A",
                     task_type="read_aloud", skill="speaking", score=40.0,
                     weight=1.0),
        SectionScore(section_id="b", position=2, title="B",
                     task_type="read_aloud", skill="speaking", score=60.0,
                     weight=1.0)])
    assert even["speaking"].score == 50.0

    tilted = roll_up([
        SectionScore(section_id="a", position=1, title="A",
                     task_type="read_aloud", skill="speaking", score=40.0,
                     weight=1.0),
        SectionScore(section_id="b", position=2, title="B",
                     task_type="read_aloud", skill="speaking", score=60.0,
                     weight=3.0)])
    assert tilted["speaking"].score == 55.0, (
        f"three parts to one gave {tilted['speaking'].score}, not 55")

    # A warm-up at zero runs and is shown, but does not move the number.
    ignored = roll_up([
        SectionScore(section_id="a", position=1, title="Warm-up",
                     task_type="read_aloud", skill="speaking", score=20.0,
                     weight=0.0),
        SectionScore(section_id="b", position=2, title="B",
                     task_type="read_aloud", skill="speaking", score=60.0,
                     weight=1.0)])
    assert ignored["speaking"].score == 60.0, (
        "a section weighted zero still dragged the skill score")

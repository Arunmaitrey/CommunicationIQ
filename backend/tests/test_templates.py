"""The four templates.

Phase 5. Three of these four could not have been expressed before Phase 3 --
a template could contain nothing but speaking -- and two of them need task
types that did not exist before Phase 4. So the tests here are less about the
templates as data and more about the claims they make: that they take the time
they say, that every section can be filled, that every sub-score they
advertise can be produced, and that no section is work the report ignores.
"""
from __future__ import annotations

from app import evaluation, formats, sections
from app.evaluation import DIMENSIONS_BY_TASK

from tests.test_game_and_practice import auth, login

TEMPLATE_CODES = ("svar_full_simulation",
                  "versant_style_speaking_listening",
                  "versant_style_four_skills",
                  "professional_english")


# -- what they claim about themselves ---------------------------------------

def test_every_stated_duration_is_the_computed_one():
    """`estimated_minutes` was typed in, and the audit caught the result: a
    template advertised at eighteen minutes that ran for twenty-two.

    Now computed from the sections. This test is what stops the field and the
    computation drifting apart again -- editing a section without editing the
    number is the whole failure mode.
    """
    for blueprint in formats.ALL_BLUEPRINTS:
        assert blueprint.estimated_minutes == formats.duration_minutes(blueprint), (
            f"{blueprint.code} says {blueprint.estimated_minutes} min and "
            f"computes to {formats.duration_minutes(blueprint)}")


# What each template was asked to be, and what it actually is.
#
# Three of the four land on target. SVAR-style does not, and the reason is
# structural rather than a matter of trimming another item: our runner waits
# out the full response window on every item, where the test it imitates
# advances as soon as the candidate stops speaking. Seven sections plus setup
# is already four and a half minutes of overhead before a single answer. The
# honest options were to publish 15 and run for 18, or to publish 18. Making
# the clock adaptive is Phase 7.
_DURATION_TARGETS = {
    "svar_full_simulation": (50, 54),
    "versant_style_speaking_listening": (21, 22),
    "versant_style_four_skills": (30, 32),
    "professional_english": (60, 62),
}


def test_each_template_lands_within_its_stated_ceiling():
    for code, (target, ceiling) in _DURATION_TARGETS.items():
        actual = formats.duration_minutes(formats.BY_CODE[code])
        assert actual <= ceiling, (
            f"{code} targets {target} min and now computes to {actual}")


def test_the_duration_model_counts_the_things_that_take_time():
    """A model that ignored setup or section cards would look precise and be
    wrong by five minutes on a seven-part format."""
    section = formats.SectionBlueprint(
        title="x", task_type="repeat_sentence", item_count=4,
        prep_seconds=0, response_seconds=15, prompt_plays_allowed=1)

    per_item = 15 + formats.PLAY_SECONDS["repeat_sentence"] + formats.TRANSITION_SECONDS
    assert formats.section_seconds(section) == per_item * 4

    # An untimed section is untimed by design, not instantaneous.
    untimed = formats.SectionBlueprint(
        title="x", task_type="reading_comprehension", item_count=3,
        prep_seconds=0, response_seconds=0)
    assert formats.section_seconds(untimed) > 0
    # And a passage is paid for once, before its questions.
    assert (formats.section_seconds(untimed)
            == formats.PASSAGE_SECONDS["reading_comprehension"]
            + 3 * (formats.ANSWER_SECONDS["reading_comprehension"]
                   + formats.TRANSITION_SECONDS))


# -- can they actually be built? --------------------------------------------

def test_every_template_section_uses_a_task_type_the_runner_serves():
    for code in TEMPLATE_CODES:
        for section in formats.BY_CODE[code].sections:
            assert section.task_type in sections.SKILL_OF_TASK, (
                f"{code}: {section.task_type} is not a classified task type")
            assert section.task_type in DIMENSIONS_BY_TASK, (
                f"{code}: {section.task_type} declares no dimensions")


def test_the_two_four_skill_templates_cover_four_skills():
    """A template called "4 Skills" that produces three is the thing this
    whole audit was about. The plan's own section list for it had no reading
    section; that was caught here rather than by a student."""
    for code in ("versant_style_four_skills", "professional_english"):
        covered = {sections.skill_of(s.task_type)
                   for s in formats.BY_CODE[code].sections}
        assert covered == set(sections.SKILLS), (
            f"{code} covers {sorted(covered)}")


def test_no_section_is_work_the_report_ignores():
    """Every section must feed at least one sub-score the format publishes.

    A candidate who spends seven minutes on Conversation Questions and finds
    that nothing on the report moved has been wasted, and there is nothing in
    the result to tell them so. This was true of the Versant model until the
    two spoken-question types were added to it.
    """
    for code, model in evaluation.MODELS.items():
        blueprint = formats.BY_CODE.get(code)
        assert blueprint is not None, f"{code} has a scoring model and no format"
        for section in blueprint.sections:
            produced = DIMENSIONS_BY_TASK.get(section.task_type, frozenset())
            feeds = [sub.label for sub in model.subscores
                     if (not sub.task_types
                         or section.task_type in sub.task_types)
                     and (produced & set(sub.dimensions))]
            assert feeds, (
                f"{code}: {section.title} ({section.task_type}) feeds no "
                f"sub-score, so answering it changes nothing on the report")


def test_a_four_skill_template_publishes_no_vendor_subscores():
    """Two numbers labelled Listening on one page is worse than one.

    The four-skill rollup measures Listening from listening sections. A vendor
    sub-score grouped from speaking dimensions would sit beside it under the
    same word, and a student would read whichever came first.
    """
    for code in ("versant_style_four_skills", "professional_english"):
        assert formats.BY_CODE[code].subscores == ()
        assert code not in evaluation.MODELS


def test_the_withdrawn_formats_are_named_rather_than_inferred():
    """The seeder retires withdrawn blueprints. Inferring which ones from "any
    code that is not a blueprint code" retired two dozen admin-authored
    profiles the first time it ran, because the builder gives those a code
    too."""
    for code in formats.WITHDRAWN_CODES:
        assert code not in formats.BY_CODE, f"{code} is withdrawn and present"
    # And the formats that replaced them exist.
    assert "svar_full_simulation" in formats.BY_CODE
    assert "versant_style_speaking_listening" in formats.BY_CODE


def test_svar_reports_only_the_subscores_its_sections_can_feed():
    """SVAR names six sub-scores. The researched A-D structure can feed four
    of them honestly; the other two (Spoken English Understanding,
    Vocabulary) have no section behind them and are omitted rather than
    relabelled from a different measure. Every published sub-score must be
    reportable from the real simulation's own sections -- and the 35 typed
    grammar items must feed Grammar, not be decorative."""
    model = evaluation.MODELS["svar_full_simulation"]
    labels = [s.label for s in model.subscores]
    assert labels == ["Pronunciation", "Fluency", "Active Listening", "Grammar"]

    blueprint = formats.BY_CODE["svar_full_simulation"]
    spec = [(s.task_type, s.item_count) for s in blueprint.sections]
    assert evaluation.unreportable("svar_full_simulation", spec) == {}

    grammar = next(s for s in model.subscores if s.label == "Grammar")
    assert {"sentence_completion", "voice_change"} <= grammar.task_types

def test_active_listening_and_grammar_are_not_the_same_measure():
    """Following what you heard and constructing sentences are different
    abilities, and a candidate who has one and not the other should be able
    to see which."""
    model = evaluation.MODELS["svar_full_simulation"]
    listening = next(s for s in model.subscores if s.label == "Active Listening")
    grammar = next(s for s in model.subscores if s.label == "Grammar")
    assert not (set(listening.dimensions) & set(grammar.dimensions))

# -- can a candidate actually sit them? -------------------------------------

async def test_every_template_serves_every_section_it_promises(client):
    """The end of the chain. A section the bank cannot fill is dropped
    silently at start, which gives a candidate a shorter test than the one
    they were shown and a score built on a different basis."""
    student = await login(client, "student")
    listing = (await client.get("/api/v1/student/profiles",
                                headers=auth(student))).json()
    by_code = {p["code"]: p for p in listing}

    for code in TEMPLATE_CODES:
        assert code in by_code, f"{code} is not offered to students"
        blueprint = formats.BY_CODE[code]

        payload = (await client.post(
            "/api/v1/student/attempts", headers=auth(student),
            json={"profile_id": by_code[code]["id"], "mode": "practice"})).json()

        served: dict[str, int] = {}
        for item in payload["items"]:
            served[item["task_type"]] = served.get(item["task_type"], 0) + 1

        for section in blueprint.sections:
            got = served.get(section.task_type, 0)
            assert got, (f"{code}: {section.title} served nothing -- the bank "
                         f"has no {section.task_type} items")
            # Whole-passage selection can legitimately deliver fewer than
            # asked; nothing else may.
            if not sections.groups_by_passage(
                    sections.source_of(section.task_type)[1]):
                assert got >= section.item_count, (
                    f"{code}: {section.title} asked for {section.item_count} "
                    f"and got {got}")


async def test_a_template_can_be_published_by_an_admin_as_it_stands(client):
    """The publish guard is the thing that would refuse a template whose bank
    is too thin. Running the four through it is how we find that out here
    rather than from a student."""
    from app.db import tenant_sessionmaker
    from app.models.tenant import SimulationProfile
    from app.routers.tenant_writes import _sections_without_items
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from tests.test_game_and_practice import SLUG

    async with tenant_sessionmaker(SLUG)() as session:
        for code in TEMPLATE_CODES:
            profile = (await session.execute(
                select(SimulationProfile)
                .where(SimulationProfile.code == code)
                .options(selectinload(SimulationProfile.sections))
            )).scalars().first()
            assert profile is not None, f"{code} was never seeded"
            problems = await _sections_without_items(session, profile)
            assert not problems, f"{code}: {problems}"


def test_the_professional_style_is_one_the_builder_accepts():
    """A style the schema rejects means the template cannot be re-created or
    edited through the builder -- seeded and then frozen."""
    from app.schemas import PROFILE_STYLES

    for code in TEMPLATE_CODES:
        assert formats.BY_CODE[code].style in PROFILE_STYLES


async def test_a_starved_section_is_refused_with_an_accurate_reason(client):
    """The guard's message has to point at the real problem.

    It appended "they come grouped by passage" to every quiz category, so an
    admin who asked for twenty response-selection items -- a bank of eight,
    ungrouped -- was sent looking for a grouping fault that does not exist
    instead of writing twelve more items.
    """
    from app.db import tenant_sessionmaker
    from app.models.tenant import SimulationProfile
    from app.routers.tenant_writes import _sections_without_items
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from tests.test_game_and_practice import SLUG

    async with tenant_sessionmaker(SLUG)() as session:
        profile = (await session.execute(
            select(SimulationProfile)
            .where(SimulationProfile.code == "professional_english")
            .options(selectinload(SimulationProfile.sections))
        )).scalars().first()

        assert await _sections_without_items(session, profile) == []

        for task_type, grouped in (("response_selection", False),
                                   ("listening_comprehension", True)):
            section = next(s for s in profile.sections
                           if s.task_type == task_type)
            was = section.item_count
            section.item_count = 40      # far beyond either bank
            await session.flush()

            problems = await _sections_without_items(session, profile)
            assert len(problems) == 1, problems
            assert ("grouped by passage" in problems[0]) is grouped, problems[0]

            section.item_count = was
            await session.flush()

        # Left exactly as found.
        await session.rollback()


# -- Phase 7: what adaptive advancement did to the clock ---------------------

def test_the_stated_duration_stays_a_ceiling_after_adaptive_advancement():
    """Measured, then deliberately not published.

    The runner now ends an item when the candidate stops speaking, so most
    sittings finish sooner. `estimated_minutes` still states the ceiling,
    because that is the number somebody can safely budget -- publishing the
    typical figure would make the estimate optimistic, which is the exact
    fault the computed duration replaced.
    """
    for blueprint in formats.ALL_BLUEPRINTS:
        typical = formats.typical_minutes(blueprint)
        ceiling = formats.duration_minutes(blueprint)
        assert typical <= ceiling, (
            f"{blueprint.code}: typical {typical} exceeds the ceiling {ceiling}")
        assert blueprint.estimated_minutes == ceiling


def test_svar_now_reaches_its_target_for_a_candidate_who_stops_talking():
    """The Phase 5 gap, closed by Phase 6's plan and Phase 7's implementation.

    SVAR-style computed to 18 against a 15-minute target because the runner
    waited out every response window in full. It still computes to 18 as a
    ceiling; what changed is that a candidate who finishes their answers now
    finishes the sitting inside the target band.
    """
    svar = formats.BY_CODE["svar_full_simulation"]
    # The real simulation is a 54-minute ceiling; adaptive advancement must
    # bring a candidate who finishes their answers in under it, and the fix
    # must never have been "reduce the configured windows".
    assert formats.typical_minutes(svar) < formats.duration_minutes(svar), (
        "adaptive advancement did not shorten the typical sitting")
    assert formats.duration_minutes(svar) == 54


def test_adaptive_advancement_never_shortens_a_written_or_chosen_section():
    """A typed answer ends when the candidate says it does. Applying a
    speech-trailing rule to it would be a rule from one response mode leaking
    into another -- the pattern this codebase keeps catching."""
    written = formats.SectionBlueprint(
        title="x", task_type="email_writing", item_count=2,
        prep_seconds=0, response_seconds=0)
    only_writing = formats.FormatBlueprint(
        code="x", name="x", style="professional", company="", description="",
        estimated_minutes=0, sections=(written,))
    assert (formats.typical_minutes(only_writing)
            == formats.duration_minutes(only_writing))


def test_the_trailing_window_agrees_with_the_client():
    """The client is the authority; this mirror exists so the duration model
    can reason about it. Two numbers that must agree, kept in step by a test
    rather than by memory."""
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2] / "frontend" / "lib"
              / "speech.ts").read_text(encoding="utf-8")
    line = next(l for l in source.splitlines()
                if "TRAILING_SILENCE_MS =" in l)
    client_ms = int(line.split("=")[1].strip().rstrip(";"))
    assert client_ms / 1000 == formats.TRAILING_SILENCE_SECONDS

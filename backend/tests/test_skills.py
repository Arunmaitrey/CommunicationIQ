"""The four skills must report their own readiness truthfully.

The product measured Speaking and only Speaking, and nothing anywhere said so.
These guard the two ways that could quietly come back: a module claiming to
work when it has no content, and a mastery percentage presented as a
measurement of something it did not measure.
"""
from __future__ import annotations

import pytest

from app.db import tenant_sessionmaker
from app import skills

from tests.test_game_and_practice import SLUG, _student_id, auth, login

pytestmark = pytest.mark.asyncio


async def _modules(client):
    token = await login(client, "student")
    user_id = await _student_id(client, token)
    async with tenant_sessionmaker(SLUG)() as session:
        return {m.key: m for m in await skills.modules_for(session, user_id)}


async def test_all_four_skills_are_listed_even_when_empty(client):
    """A skill you cannot practise still appears, or the gap is invisible.

    Leaving Writing out of the menu until it works is tidier and worse: a
    student cannot tell a missing feature from one they have not found.
    """
    modules = await _modules(client)
    assert set(modules) == {"speaking", "listening", "reading", "writing"}


async def test_status_is_computed_from_content_not_asserted(client):
    """Adding or removing items must move a module's status on its own.

    A stored status field is the same shape as the UNSCORED constant that let
    a blank result page claim everything was fine.
    """
    modules = await _modules(client)

    # Speaking has a real item bank behind it.
    assert modules["speaking"].item_count >= skills.MIN_ITEMS_FOR_LIVE
    assert modules["speaking"].status == "live"

    # Writing is counted in prompts rather than questions, so it has its own
    # threshold -- a prompt is a twenty-minute session, not a twenty-second
    # question. Either way the status has to follow the content.
    writing = modules["writing"]
    if writing.item_count >= skills.MIN_PROMPTS_FOR_LIVE:
        assert writing.status == "live"
        assert writing.measures
    else:
        assert writing.status in ("partial", "planned")
    # Whatever the state, the limits are stated rather than implied.
    assert writing.gap


async def test_a_module_with_no_items_never_claims_to_be_live(client):
    """The invariant, stated directly, for whatever the bank holds today."""
    for module in (await _modules(client)).values():
        floor = (skills.MIN_PROMPTS_FOR_LIVE if module.key == "writing"
                 else skills.MIN_ITEMS_FOR_LIVE)
        if module.item_count < floor:
            assert module.status != "live", module.key
        if module.status != "live":
            assert module.gap or module.summary, module.key


async def test_an_indirect_mastery_number_says_where_it_came_from(client):
    """Listening's percentage is not a measurement of listening.

    The engine maps its `accuracy` dimension onto the `listening` skill, and
    accuracy is scored on Read Aloud as well as Repeat Sentence -- so part of
    that number is earned reading a sentence off a screen, having heard
    nothing. A bare percentage on a module with no comprehension items would
    read as a measurement of comprehension. Any module showing a mastery
    figure has to explain its own provenance.
    """
    for module in (await _modules(client)).values():
        if module.mastery is not None:
            assert module.mastery_basis, (
                f"{module.key} shows {module.mastery}% with no explanation of "
                f"where that number came from")

    # And the disclosure has to track the module's actual state rather than
    # being frozen at whatever was true when this was written. Listening began
    # as a proxy fed by repeat-accuracy and became a real measurement once
    # comprehension items existed; the wording had to move with it, and this
    # test failed exactly when it did.
    listening = (await _modules(client))["listening"]
    if listening.mastery is not None:
        basis = listening.mastery_basis.lower()
        if listening.status == "live":
            # Now measured directly -- it must not still apologise for being
            # a proxy, which would understate a real result.
            assert "indirect" not in basis, basis
            assert "listening" in basis or "comprehension" in basis, basis
        else:
            # Still a proxy: it must say so rather than pass itself off as
            # a measurement of comprehension.
            assert "indirect" in basis, basis


async def test_the_overview_endpoint_leads_with_the_truth(client):
    """The headline says how many of the four really work, in one line."""
    token = await login(client, "student")
    body = (await client.get("/api/v1/student/skills",
                             headers=auth(token))).json()

    assert len(body["modules"]) == 4
    assert body["headline"]

    live = [m["label"] for m in body["modules"] if m["status"] == "live"]
    if len(live) == 4:
        # Nothing to qualify -- the headline says so in one line rather than
        # listing four names back at the reader.
        assert "All four" in body["headline"]
    else:
        assert "All four" not in body["headline"], (
            "the headline must not read as finished while a module is not")
        # Every working skill is named, so a student can see which they are.
        for label in live:
            assert label in body["headline"]

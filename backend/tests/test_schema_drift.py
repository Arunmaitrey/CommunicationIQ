"""A column in a model and not in the database.

This has now happened three times: ``is_practice``, ``profile_sections.weight``,
and whatever the next one is. The shape is always the same and always quiet.

A tenant table is declared against the ``tenant`` placeholder and created by
``create_all`` when an institution is provisioned. A column added afterwards
reaches an *existing* schema only through ``_TENANT_COLUMN_UPGRADES``, and only
when something runs the upgrade. Locally something usually does, because tests
provision fresh schemas. On a deployed database with institutions already in
it, nothing did: ``alembic upgrade head`` owns the control plane and does not
know tenant schemas exist, and ``seed --if-empty`` correctly does nothing when
it finds an institution -- which is exactly why it could never have been the
thing that ran the upgrade.

So the model shipped, the column did not, and the first symptom was a 500 from
``column profile_sections.weight does not exist`` on the assessment list, the
admin console and the start of every attempt. A long way from naming the
cause.

These tests are about the mechanism rather than any one column, because naming
columns is how the last two got missed.
"""
from __future__ import annotations

import pytest

from app import provisioning
from app.db import TenantBase

pytestmark = pytest.mark.asyncio

SLUG = "stmarys"


async def test_the_live_schema_has_every_column_the_models_declare():
    """The assertion the deploy was missing.

    Whatever this test names when it fails is a column that would 500 in
    production, so the failure message is the fix list.
    """
    gaps = await provisioning.missing_columns(SLUG)
    assert not gaps, (
        f"the models declare columns this schema does not have: {gaps}. "
        f"Add each to _TENANT_COLUMN_UPGRADES and run "
        f"`python -m app.provisioning`.")


async def test_the_upgrade_list_only_names_columns_the_models_have():
    """The other direction, which is dead DDL rather than a crash.

    A column removed from a model and left in the upgrade list adds itself to
    every new schema forever, and nobody notices because nothing breaks.
    """
    declared = {(table.name, column.name)
                for table in TenantBase.metadata.tables.values()
                for column in table.columns}

    orphans = [f"{table}.{column}"
               for table, column, _ in provisioning._TENANT_COLUMN_UPGRADES
               if (table, column) not in declared]

    assert not orphans, (
        f"_TENANT_COLUMN_UPGRADES adds columns no model declares: {orphans}")


async def test_the_upgrade_is_safe_to_run_twice():
    """It runs on every deploy now, so idempotence is not a nicety."""
    first = await provisioning.upgrade_tenant_schema(SLUG)
    second = await provisioning.upgrade_tenant_schema(SLUG)

    assert second == [], (
        f"a second run applied {second} -- the presence check is not working, "
        f"and every deploy is now issuing DDL against a live database")
    assert isinstance(first, list)


async def test_upgrade_everything_refuses_to_start_on_a_gap_it_cannot_close():
    """Failing loudly beats serving 500s.

    A column in a model with no matching upgrade cannot be fixed by running
    the upgrade again. The deploy step raises rather than starting, because a
    service that boots and then errors on the assessment list gets diagnosed
    by a user.
    """
    from unittest.mock import patch

    async def _pretend_gap(slug: str) -> list[str]:
        return ["profile_sections.something_nobody_added"]

    with patch.object(provisioning, "missing_columns", _pretend_gap):
        with pytest.raises(RuntimeError, match="declared by the models"):
            await provisioning.upgrade_everything()


async def test_a_schema_that_does_not_exist_is_not_reported_as_every_column():
    """A missing institution is a different fault with a different fix, and
    listing four hundred columns would bury it."""
    gaps = await provisioning.missing_columns("nosuchtenant")
    assert gaps == []


@pytest.mark.filterwarnings("ignore::pytest.PytestWarning")
def test_the_deploy_actually_runs_the_upgrade():
    """The whole bug, in one assertion.

    Every piece of the machinery above existed already --
    `upgrade_all_tenant_schemas` was written, tested and called by nothing on
    the deploy path. What was missing was the line in render.yaml.
    """
    from pathlib import Path

    import yaml

    blueprint = yaml.safe_load(
        (Path(__file__).resolve().parents[2] / "render.yaml").read_text())
    api = next(s for s in blueprint["services"]
               if "app.main:app" in str(s.get("startCommand", "")))
    start = str(api["startCommand"])

    assert "app.provisioning" in start, (
        "the deploy does not upgrade tenant schemas. alembic owns the control "
        "plane and `seed --if-empty` does nothing on a seeded database, so "
        "without this step a new column ships and its DDL does not.")
    assert start.index("app.provisioning") < start.index("uvicorn"), (
        "the upgrade must finish before the service starts serving")


@pytest.mark.filterwarnings("ignore::pytest.PytestWarning")
def test_a_push_does_not_deploy():
    """This product is run locally, and a push must not publish it.

    Render's free tier has 512 MB. faster-whisper and wav2vec2 do not load in
    that, so the instance OOM-kills them and a deployed attempt comes back
    with no scores at all -- which reads to anybody looking at it as a broken
    engine, and is a box that is too small.

    Auto-deploy on top of that publishes, on every push, a version of the
    product that cannot do the thing the product is for. Deploying is a
    deliberate act from the dashboard now, for whenever the instance is worth
    it.
    """
    from pathlib import Path

    import yaml

    blueprint = yaml.safe_load(
        (Path(__file__).resolve().parents[2] / "render.yaml").read_text())

    auto = [s["name"] for s in blueprint["services"]
            if s.get("autoDeploy") is not False]
    assert not auto, f"these services still deploy on push: {auto}"

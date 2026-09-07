"""Bulk export of one institution's reports — the deliberate exception.

Everywhere else the rule holds absolutely: platform staff never read student
data (see platform_admin.py, whose endpoints cannot reach an institution
database at all). This file is the one door through that wall, and it exists
because an operator with database credentials already *has* the data — the
choice is not whether a bulk export is possible, it is whether it happens as
`mongodump` on a laptop, invisibly, or as a product feature with rules:

* **super_admin only.** Not finance, not support, not content. The guard is
  on the router, so a new endpoint added here cannot forget it.
* **Audit-logged before the response leaves.** The archive is assembled in
  memory; if the log write fails, the request fails and nothing is
  disclosed. A completed export therefore always has its row.
* **The slug still never comes from the caller.** The caller names a tenant
  *id*; the slug is read from the control-plane registry row. TEN-12's
  invariant — no code path accepts a database name from outside — survives.
* **Scores only, never audio.** Recordings carry a person's voice and their
  consent covers marking, not redistribution. This exports what a report
  page shows: measures, confidence, provenance.
* **Every tenant status is exportable.** drop_tenant_schema's contract says
  offboarding completes "the contracted data export first" — this endpoint
  is that export, so refusing a suspended or offboarding tenant would break
  the one flow that must work then. A registry row whose database is already
  gone answers 409, not a stack trace.

The roster is everyone who sits assessments: students and invited
candidates. A candidate's report is the entire reason their account exists;
an export that silently dropped them would read as complete and not be.

CSV long format for the same reason the per-attempt export uses it: a wide
row with seven dimensions breaks the day an attempt produces six. Rows are
streamed from the database straight into the archive entry in batches, so
the export of a large tenant holds one compressed copy in memory, not five
uncompressed ones, and yields the event loop while it works.
"""
from __future__ import annotations

import csv
import io
import zipfile
from contextlib import contextmanager
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response as HttpResponse

from app import audit
from app.deps import Principal, require_platform, tenant_models_for
from app.models.platform import Tenant
from app.provisioning import tenant_schema_exists

router = APIRouter(prefix="/platform", tags=["platform"],
                   dependencies=[Depends(require_platform("super_admin"))])

# Who belongs in the export: everyone whose account exists to sit an
# assessment. Trainer and admin accounts trying things out are not student
# data, and their attempts are dropped with them.
ROSTER_ROLES = ("student", "candidate")

# Rows fetched per round-trip while streaming. Large enough that the
# per-batch overhead disappears, small enough that a batch is never a
# meaningful fraction of anyone's memory.
BATCH = 500


def _disarm(value):
    """Stop a cell from executing when the CSV is opened in a spreadsheet.

    Names, roll numbers, branches and profile titles are typed by institution
    staff, and this file's whole audience is an operator double-clicking it
    into Excel. A value like ``=HYPERLINK(...)`` or ``@SUM(...)`` would run
    there, which turns a data export into code the exporting side never
    wrote. The standard defusal: a leading apostrophe, which spreadsheets
    read as "text follows" and drop on display.

    Strings only — numbers arrive as numbers, so a negative score is never
    touched, and only when the first character is one Excel treats as
    executable rather than every cell, because an export full of stray
    apostrophes punishes the common case for the rare attack. The README
    tells programmatic consumers the apostrophe may be there.
    """
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


@contextmanager
def _entry(zf: zipfile.ZipFile, name: str, header: list[str]):
    """One CSV inside the archive, written row by row as they stream in.

    Yields a `write(cells)` function. Writing directly into the open zip
    entry is what keeps memory flat: the row is disarmed, encoded and
    compressed, and only the compressed bytes stay.
    """
    with zf.open(name, "w") as raw, \
         io.TextIOWrapper(raw, encoding="utf-8", newline="") as text:
        writer = csv.writer(text, lineterminator="\n")
        writer.writerow(header)
        yield lambda cells: writer.writerow([_disarm(c) for c in cells])


def _iso(dt) -> str:
    return dt.isoformat() if dt else ""


README = """Report export
=============

Institution: {name} ({slug}, status: {tenant_status})
Exported by: {actor}

Files
-----
students.csv        Everyone who sits assessments — students and invited
                    candidates, told apart by the role column. Candidates
                    have no password and exist for the assessment they were
                    invited to; their reports are as real as anyone's.
attempts.csv        One row per test attempt, with the overall score where
                    one exists. Lifecycle states are included ("created",
                    "abandoned"...) so absence of a score is visible as
                    what it is, not silently dropped. A "scored" attempt
                    with an empty overall is real too: an overall needs at
                    least three measures, and a server without the speech
                    models produces fewer. Its individual measures are in
                    report_measures.csv.
report_measures.csv One row per measurement — the long-format contents of
                    every report. scope says whether the row is an
                    attempt-level dimension or a single response's measure.
skill_mastery.csv   Per-person, per-sub-skill mastery (0-1), with
                    confidence and observation counts.

Reading these files
-------------------
Every score is UNCALIBRATED unless the calibration state says otherwise —
no validation study has tied these numbers to human judgement. The
per-measure rows carry the same confidence values the report pages show.

A text cell that would open as a formula in a spreadsheet (leading =, +, -,
@) is exported with a leading apostrophe, the standard defusal. If you are
parsing these files with code rather than a spreadsheet, strip a single
leading apostrophe from text fields before comparing.

No audio is included, deliberately. Recordings carry a person's voice and
their consent covers scoring, not redistribution. Provenance columns
(provider_key, provider_version) say which implementation produced each
number.
"""


@router.get("/tenants/{tenant_id}/export.zip")
async def export_tenant_reports(tenant_id: str, principal: Principal) -> HttpResponse:
    """Everything reportable about one institution's people, as a ZIP."""
    tenant = await Tenant.get(tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")

    # A registry row whose institution database does not exist — never
    # provisioned, or already dropped during offboarding — must answer a
    # clean 409 rather than produce an empty archive that reads as success.
    # MongoDB answers queries against a missing database with empty results
    # instead of raising, so the check has to be explicit; there is no
    # equivalent of Postgres' undefined_table error to catch afterwards.
    if not await tenant_schema_exists(tenant.slug):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"The schema for '{tenant.slug}' does not exist — the tenant is "
            "half-provisioned or its data has already been dropped during "
            "offboarding.")

    buffer = io.BytesIO()
    counts = {"people": 0, "attempts": 0, "measures": 0}

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("README.txt", README.format(
            name=tenant.name, slug=tenant.slug, tenant_status=tenant.status,
            actor=principal.label))
        models = await tenant_models_for(tenant)
        await _write_reports(models, zf, counts)

    # The log row is written before the response leaves the process. If
    # this write fails the request fails and nothing was disclosed; the
    # surviving invariant is that a completed export always has its row.
    await audit.record(
        principal, "tenant.reports_exported", entity="Tenant",
        entity_id=tenant.id, tenant_id=tenant.id, after=counts)

    return HttpResponse(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition":
                 f'attachment; filename="reports-{tenant.slug}.zip"'},
    )


async def _write_reports(models: SimpleNamespace, zf: zipfile.ZipFile,
                         counts: dict) -> None:
    """Stream the four CSVs into the archive.

    Held in memory across the whole export: the roster (id → email, name),
    the profile names, and one small tuple per attempt — its owner and
    profile, which replaces the join the measures pass used to do in the
    database. The big tables (attempts, score records, mastery) are never
    materialised; they stream through cursors in batches of {BATCH}.
    """
    profiles: dict[str, str] = {
        doc["_id"]: doc["name"]
        async for doc in models.SimulationProfile.get_motor_collection().find(
            {}, {"name": 1})}

    people: dict[str, tuple[str, str]] = {}
    with _entry(zf, "students.csv",
                ["id", "email", "full_name", "role", "roll_number", "branch",
                 "year_of_study", "l1_language", "active", "last_login_at",
                 "created_at"]) as write:
        cursor = models.User.get_motor_collection().find(
            {"role": {"$in": list(ROSTER_ROLES)}},
            sort=[("email", 1)], batch_size=BATCH)
        async for u in cursor:
            people[u["_id"]] = (u["email"], u["full_name"])
            write([u["_id"], u["email"], u["full_name"], u["role"],
                   u["roll_number"],
                   u["year_of_study"] if u.get("year_of_study") is not None else "",
                   u["l1_language"], u["active"],
                   _iso(u.get("last_login_at")), _iso(u.get("created_at"))])
    counts["people"] = len(people)

    # Attempt-level overalls, one small tuple each. Ordered by creation so
    # that if a double-finalise race ever leaves two rows, the newer one
    # wins deterministically instead of whichever the database felt like.
    overall: dict[str, tuple[float, str]] = {}
    cursor = models.ScoreRecord.get_motor_collection().find(
        {"response_id": None, "dimension": "overall", "is_shadow": False},
        sort=[("created_at", 1)], batch_size=BATCH)
    async for s in cursor:
        overall[s["attempt_id"]] = (s["score"], s.get("band", ""))

    # Attempt owner and profile, captured during the attempts pass so the
    # measures pass below needs no lookup beyond the roster already in hand.
    attempt_owner: dict[str, tuple[str, str]] = {}
    with _entry(zf, "attempts.csv",
                ["id", "student_email", "student_name", "profile", "mode",
                 "is_baseline", "status", "overall_score", "band",
                 "started_at", "submitted_at", "scored_at"]) as write:
        cursor = models.Attempt.get_motor_collection().find(
            {}, sort=[("created_at", 1)], batch_size=BATCH)
        async for a in cursor:
            attempt_owner[a["_id"]] = (a["user_id"], a["profile_id"])
            who = people.get(a["user_id"])
            if who is None:
                continue  # a trainer or admin trying things out
            score, band = overall.get(a["_id"], ("", ""))
            write([a["_id"], who[0], who[1],
                   profiles.get(a["profile_id"], ""), a["mode"],
                   a["is_baseline"], a["status"], score, band,
                   _iso(a.get("started_at")), _iso(a.get("submitted_at")),
                   _iso(a.get("scored_at"))])
            counts["attempts"] += 1

    with _entry(zf, "report_measures.csv",
                ["attempt_id", "student_email", "profile", "scope",
                 "response_id", "dimension", "score", "scale_min",
                 "scale_max", "band", "confidence", "provider_key",
                 "provider_version", "created_at"]) as write:
        cursor = models.ScoreRecord.get_motor_collection().find(
            {"is_shadow": False},
            sort=[("attempt_id", 1), ("created_at", 1)], batch_size=BATCH)
        async for s in cursor:
            user_id, profile_id = attempt_owner.get(s["attempt_id"], (None, None))
            who = people.get(user_id)
            if who is None:
                continue
            write([s["attempt_id"], who[0], profiles.get(profile_id, ""),
                   "attempt" if s.get("response_id") is None else "response",
                   s.get("response_id") or "", s["dimension"], s["score"],
                   s["scale_min"], s["scale_max"], s.get("band", ""),
                   s["confidence"] if s.get("confidence") is not None else "",
                   s["provider_key"], s["provider_version"],
                   _iso(s.get("created_at"))])
            counts["measures"] += 1

    with _entry(zf, "skill_mastery.csv",
                ["student_email", "skill", "mastery", "confidence",
                 "observations", "baseline", "updated_at"]) as write:
        cursor = models.SkillMastery.get_motor_collection().find(
            {}, sort=[("user_id", 1), ("skill", 1)], batch_size=BATCH)
        async for m in cursor:
            who = people.get(m["user_id"])
            if who is None:
                continue
            write([who[0], m["skill"], m["mastery"], m["confidence"],
                   m["observations"],
                   m["baseline"] if m.get("baseline") is not None else "",
                   _iso(m.get("updated_at"))])

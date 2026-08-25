"""Bulk import of students and staff (TEN-03).

A placement cell arrives with a spreadsheet exported from whatever their ERP
is. The import has to survive that: unfamiliar column names, blank rows,
trailing whitespace, duplicate roll numbers, an email typo on row 47.

Two rules shape it:

* **All or nothing per run.** A partial import leaves an admin guessing which
  half landed. Every row is validated first; if any row fails, nothing is
  written and every problem is reported at once — not the first one.
* **Never a silent overwrite.** A row whose email already exists updates the
  profile fields and says so in the report. It never touches a password, a
  role, or an attempt history.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

VALID_ROLES = {"student", "trainer", "tenant_admin"}
VALID_L1 = {"", "telugu", "hindi", "tamil", "kannada", "malayalam", "marathi",
            "bengali", "gujarati", "punjabi", "odia", "other"}

# What a column might be called in the wild. The left side is what we store.
ALIASES = {
    "email": {"email", "email id", "emailid", "e-mail", "mail", "email address"},
    "full_name": {"full name", "name", "student name", "fullname"},
    "roll_number": {"roll number", "roll", "roll no", "rollno", "hall ticket",
                    "hall ticket number", "registration number", "reg no"},
    "branch": {"branch", "department", "dept", "stream"},
    "year_of_study": {"year", "year of study", "study year"},
    "l1_language": {"l1", "mother tongue", "first language", "native language",
                    "l1 language"},
    "role": {"role", "type", "user type"},
    "cohort": {"cohort", "section", "class", "batch"},
}


@dataclass
class ImportRow:
    line: int
    email: str
    full_name: str
    role: str = "student"
    roll_number: str = ""
    branch: str = ""
    year_of_study: int | None = None
    l1_language: str = ""
    cohort: str = ""


@dataclass
class ImportProblem:
    line: int
    column: str
    message: str


@dataclass
class ImportPlan:
    rows: list[ImportRow] = field(default_factory=list)
    problems: list[ImportProblem] = field(default_factory=list)
    # Emails already present in the institution — updated, never overwritten.
    existing: set[str] = field(default_factory=set)

    @property
    def ok(self) -> bool:
        return not self.problems

    @property
    def creating(self) -> int:
        return len([r for r in self.rows if r.email not in self.existing])

    @property
    def updating(self) -> int:
        return len([r for r in self.rows if r.email in self.existing])


def _canonical(header: str) -> str | None:
    cleaned = header.strip().lower().replace("_", " ")
    for field_name, names in ALIASES.items():
        if cleaned in names or cleaned == field_name:
            return field_name
    return None


def parse(text: str) -> ImportPlan:
    """Validate a CSV upload without touching the database.

    Returns everything that is wrong with it, not the first thing.
    """
    plan = ImportPlan()

    # Excel exports from Windows machines routinely arrive with a BOM, which
    # otherwise turns the first column name into "﻿email" and makes the
    # whole file look like it has no email column.
    text = text.lstrip("﻿")
    if not text.strip():
        plan.problems.append(ImportProblem(0, "", "The file is empty"))
        return plan

    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        plan.problems.append(ImportProblem(0, "", "The file has no header row"))
        return plan

    columns = [_canonical(h) for h in header]
    if "email" not in columns:
        plan.problems.append(ImportProblem(
            1, "email",
            "No email column. Expected a column named email, e-mail or email id."))
    if "full_name" not in columns:
        plan.problems.append(ImportProblem(
            1, "full_name",
            "No name column. Expected a column named name or full name."))
    if plan.problems:
        return plan

    seen_emails: dict[str, int] = {}
    seen_rolls: dict[str, int] = {}

    for offset, raw in enumerate(reader, start=2):
        if not any(cell.strip() for cell in raw):
            continue    # a blank row in the middle of a sheet is not an error

        values: dict[str, str] = {}
        for index, column in enumerate(columns):
            if column and index < len(raw):
                values[column] = raw[index].strip()

        email = values.get("email", "").lower()
        name = values.get("full_name", "")

        if not EMAIL.match(email):
            plan.problems.append(ImportProblem(offset, "email",
                                               f"{email or '(blank)'} is not an email address"))
            continue
        if not name:
            plan.problems.append(ImportProblem(offset, "full_name", "Name is required"))
            continue

        if email in seen_emails:
            plan.problems.append(ImportProblem(
                offset, "email", f"{email} also appears on line {seen_emails[email]}"))
            continue
        seen_emails[email] = offset

        role = (values.get("role") or "student").lower().replace(" ", "_")
        if role not in VALID_ROLES:
            plan.problems.append(ImportProblem(
                offset, "role", f"{role} is not a role — use student, trainer or tenant_admin"))
            continue

        year: int | None = None
        raw_year = values.get("year_of_study", "")
        if raw_year:
            digits = re.sub(r"\D", "", raw_year)
            if not digits or not (1 <= int(digits) <= 6):
                plan.problems.append(ImportProblem(
                    offset, "year_of_study", f"{raw_year} is not a study year between 1 and 6"))
                continue
            year = int(digits)

        l1 = values.get("l1_language", "").lower()
        if l1 not in VALID_L1:
            plan.problems.append(ImportProblem(
                offset, "l1_language", f"{l1} is not a recognised first language"))
            continue

        roll = values.get("roll_number", "")
        if roll:
            if roll in seen_rolls:
                plan.problems.append(ImportProblem(
                    offset, "roll_number",
                    f"{roll} also appears on line {seen_rolls[roll]}"))
                continue
            seen_rolls[roll] = offset

        plan.rows.append(ImportRow(
            line=offset, email=email, full_name=name, role=role,
            roll_number=roll, branch=values.get("branch", ""),
            year_of_study=year, l1_language=l1,
            cohort=values.get("cohort", ""),
        ))

    if not plan.rows and not plan.problems:
        plan.problems.append(ImportProblem(0, "", "The file has a header but no rows"))

    return plan

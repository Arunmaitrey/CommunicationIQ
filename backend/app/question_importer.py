"""Bulk question import: an uploaded CSV or JSON file, validated into a
plan the operator can preview before anything is written.

Referenced by ``platform_admin.py`` (``/questions/import/preview``,
``/questions/import/confirm``, ``/questions/import/template/{category}``) but
never actually shipped in the merged feat/exam-section PR -- the import
raised ``ModuleNotFoundError`` at startup. Reconstructed here from every call
site in that file: the shape of ``ImportPlan``, what a ``Row`` carries, what
``Problem`` looks like, and the five canonical categories the confirm step
switches on (quiz, reading, listening, writing, speaking) all come from how
that router actually reads this module's return values, not from a guess at
a nicer API.
"""
from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field

# Every alias a CSV's own "category"/"module" column might use, mapped onto
# the five buckets platform_admin.py's import_confirm() switches on. The
# admin UI's own upload dialog always sends one of the five canonical keys
# directly, so this mostly matters for a CSV built outside that dialog.
CATEGORY_ALIASES: dict[str, str] = {
    "quiz": "quiz", "mcq": "quiz", "grammar": "quiz", "vocabulary": "quiz",
    "vocab": "quiz", "grammar_vocab": "quiz", "grammar_and_vocabulary": "quiz",
    "reading": "reading", "reading_comprehension": "reading",
    "passage": "reading", "article": "reading",
    "listening": "listening", "audio_comprehension": "listening",
    "audio": "listening", "listening_comprehension": "listening",
    "writing": "writing", "essay": "writing", "email": "writing",
    "report": "writing", "summary": "writing", "complaint": "writing",
    "speaking": "speaking", "open_response": "speaking", "spoken": "speaking",
}

REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "quiz": ("stem",),
    "reading": ("title", "body"),
    "listening": ("title", "transcript"),
    "writing": ("title",),
    "speaking": (),  # prompt_text falls back to stem; nothing is strictly required
}


def _normalise_header(name: str) -> str:
    """"Question Stem", "question_stem" and " Stem " all mean the same
    column; a header a spreadsheet tool renamed should not fail a row that
    is otherwise fine."""
    return name.strip().lower().replace(" ", "_").replace("-", "_")


@dataclass
class Problem:
    row: int
    field: str
    message: str
    severity: str = "error"  # "error" or "warning"


@dataclass
class Row:
    row_num: int
    raw: dict
    category: str = ""


@dataclass
class ImportPlan:
    rows: list[Row] = field(default_factory=list)
    problems: list[Problem] = field(default_factory=list)
    total: int = 0
    valid: int = 0
    warnings: int = 0
    errors: int = 0
    duplicates: int = 0


def _detect_category(raw: dict, default: str = "") -> str:
    for key in ("category", "module", "type", "section"):
        value = raw.get(key)
        if value:
            return CATEGORY_ALIASES.get(str(value).strip().lower(), str(value).strip().lower())
    return default


def _validate_row(row: Row, plan: ImportPlan, seen_stems: dict[str, int]) -> None:
    cat = row.category or "quiz"
    required = REQUIRED_FIELDS.get(cat, ())
    for name in required:
        val = row.raw.get(name)
        if name == "title" and not val:
            # writing/reading/listening rows sometimes carry the heading
            # under "stem" instead -- accept it before failing the row.
            val = row.raw.get("stem")
        if not str(val or "").strip():
            plan.problems.append(Problem(
                row=row.row_num, field=name,
                message=f"'{name}' is required for a {cat} question but was empty.",
                severity="error",
            ))

    if cat == "quiz":
        options = [row.raw.get(f"option_{c}", "") for c in "abcd" if row.raw.get(f"option_{c}")]
        if len(options) < 2:
            plan.problems.append(Problem(
                row=row.row_num, field="options",
                message="A quiz question needs at least two options (option_a, option_b, ...).",
                severity="error",
            ))
        letter = str(row.raw.get("correct_answer", "")).strip().upper()
        if letter and letter not in ("A", "B", "C", "D"):
            plan.problems.append(Problem(
                row=row.row_num, field="correct_answer",
                message=f"'{letter}' is not one of A, B, C, D — defaulting to A.",
                severity="warning",
            ))

    dedupe_key = str(row.raw.get("stem") or row.raw.get("title")
                     or row.raw.get("prompt_text") or row.raw.get("prompt") or "").strip().lower()
    if dedupe_key:
        if dedupe_key in seen_stems:
            plan.duplicates += 1
            plan.problems.append(Problem(
                row=row.row_num, field="stem",
                message=f"Same question text as row {seen_stems[dedupe_key]} — check before importing both.",
                severity="warning",
            ))
        else:
            seen_stems[dedupe_key] = row.row_num


def _rows_from_csv(content: bytes) -> list[dict]:
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    out = []
    for raw in reader:
        out.append({_normalise_header(k): (v or "").strip() for k, v in raw.items() if k})
    return out


def _rows_from_json(content: bytes) -> list[dict]:
    data = json.loads(content.decode("utf-8", errors="replace"))
    items = data.get("items", data) if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ValueError("JSON import expects {\"items\": [...]} or a top-level array")
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        row = {_normalise_header(k): v for k, v in item.items()}
        # A JSON row may carry real lists/ints rather than CSV's flat
        # strings (options as a list, correct_index instead of a letter) --
        # normalise both onto the same option_a../correct_answer shape the
        # confirm step reads, so one code path handles both sources.
        opts = row.pop("options", None)
        if isinstance(opts, list):
            for i, letter in enumerate("abcd"):
                if i < len(opts):
                    row[f"option_{letter}"] = str(opts[i])
        if "correct_answer" not in row and "correct_index" in row:
            idx = row.pop("correct_index")
            if isinstance(idx, int) and 0 <= idx < 4:
                row["correct_answer"] = "ABCD"[idx]
        out.append({k: ("" if v is None else str(v) if not isinstance(v, (list, dict)) else v)
                   for k, v in row.items()})
    return out


def parse_upload(filename: str, content: bytes) -> ImportPlan:
    """Parse an uploaded file into an :class:`ImportPlan`.

    Supports ``.csv`` (the format the template download hands back) and
    ``.json`` (what the admin UI sends when someone pastes JSON instead of
    picking a file). Anything else is rejected up front rather than parsed
    into garbage.
    """
    name = (filename or "").lower()
    if name.endswith(".json"):
        raw_rows = _rows_from_json(content)
    elif name.endswith(".csv") or "." not in name:
        raw_rows = _rows_from_csv(content)
    else:
        raise ValueError(
            f"Unsupported file type for {filename!r} — upload a .csv or .json file.")

    plan = ImportPlan(total=len(raw_rows))
    seen_stems: dict[str, int] = {}
    for i, raw in enumerate(raw_rows, start=1):
        cat = _detect_category(raw, default="quiz")
        row = Row(row_num=i, raw=raw, category=cat)
        plan.rows.append(row)
        _validate_row(row, plan, seen_stems)

    error_rows = {p.row for p in plan.problems if p.severity == "error"}
    plan.errors = len(error_rows)
    plan.warnings = len([p for p in plan.problems if p.severity == "warning"])
    plan.valid = plan.total - plan.errors
    return plan


_TEMPLATE_COLUMNS: dict[str, list[str]] = {
    "quiz": ["stem", "option_a", "option_b", "option_c", "option_d",
             "correct_answer", "explanation", "difficulty", "company"],
    "reading": ["title", "kind", "body", "difficulty", "company"],
    "listening": ["title", "kind", "transcript", "audio_key", "accent",
                  "plays_allowed", "approx_seconds", "difficulty", "company"],
    "writing": ["title", "kind", "prompt", "scenario", "key_points",
                "min_words", "suggested_minutes", "difficulty", "company"],
    "speaking": ["task_type", "prompt_text", "reference_text", "audio_key",
                 "difficulty", "company"],
}

_TEMPLATE_EXAMPLE_ROW: dict[str, list[str]] = {
    "quiz": ["What is the synonym of 'happy'?", "Sad", "Joyful", "Angry", "Tired",
             "B", "Joyful means happy.", "0.3", ""],
    "reading": ["Sample passage title", "article", "Paste the passage text here.",
               "0.3", ""],
    "listening": ["Sample talk title", "short_talk", "Paste the transcript here.",
                  "", "indian", "1", "45", "0.3", ""],
    "writing": ["Sample essay title", "essay", "Write about your favourite hobby.",
               "", "structure, examples, conclusion", "150", "20", "0.3", ""],
    "speaking": ["open_response", "Describe your daily routine.", "", "", "0.3", ""],
}


def get_template(category: str) -> str:
    """A downloadable CSV template for one of the five import categories."""
    key = CATEGORY_ALIASES.get(category.lower().strip(), category.lower().strip())
    columns = _TEMPLATE_COLUMNS.get(key)
    if columns is None:
        raise ValueError(
            f"No template for category {category!r}; expected one of "
            f"{', '.join(sorted(_TEMPLATE_COLUMNS))}")
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(columns)
    writer.writerow(_TEMPLATE_EXAMPLE_ROW[key])
    return buf.getvalue()

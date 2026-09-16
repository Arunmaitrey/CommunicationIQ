"""Bulk question import for platform admin (preview + confirm flow).

Parses CSV/JSON uploads of quiz, reading, writing, listening, and speaking
questions. Validates rows, detects category, and returns an ImportPlan with
preview data and problems.
"""
from __future__ import annotations

import csv
import io
import json as _json
import re
from dataclasses import dataclass, field

# Category detection aliases
CATEGORY_ALIASES = {
    "quiz": "quiz",
    "grammar": "quiz",
    "vocabulary": "quiz",
    "reading": "reading",
    "listening": "listening",
    "writing": "writing",
    "speaking": "speaking",
    "read_aloud": "speaking",
    "repeat_sentence": "speaking",
    "short_answer": "speaking",
    "open_response": "speaking",
    "story_retell": "speaking",
    "sentence_build": "speaking",
}


def _normalise_header(h: str) -> str:
    """Lowercase, strip, replace spaces/special chars with underscores."""
    return re.sub(r"[^a-z0-9]+", "_", h.strip().lower()).strip("_")


@dataclass
class ImportRow:
    row_num: int
    category: str
    raw: dict = field(default_factory=dict)


@dataclass
class ImportProblem:
    row: int
    field: str
    message: str
    severity: str = "error"  # "error" | "warning"


@dataclass
class ImportPlan:
    total: int = 0
    valid: int = 0
    rows: list[ImportRow] = field(default_factory=list)
    problems: list[ImportProblem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    duplicates: int = 0

    @property
    def ok(self) -> bool:
        return not any(p.severity == "error" for p in self.problems)


def detect_category(headers: list[str]) -> str:
    """Auto-detect question category from CSV headers."""
    normed = {_normalise_header(h) for h in headers}

    # Speaking detection
    if "task_type" in normed or "prompt_text" in normed or "reference_text" in normed:
        return "speaking"
    # Reading detection
    if "body" in normed and ("title" in normed or "kind" in normed):
        return "reading"
    # Listening detection
    if "transcript" in normed or "audio_key" in normed:
        return "listening"
    # Writing detection
    if "prompt" in normed or "scenario" in normed or "key_points" in normed:
        return "writing"
    # Quiz (default if options exist)
    if any(h.startswith("option_") or h == "correct_answer" for h in normed):
        return "quiz"
    # Module column
    if "module" in normed:
        return "quiz"

    return "quiz"  # default


def parse_upload(filename: str, content: bytes) -> ImportPlan:
    """Parse uploaded file and return an ImportPlan with validation results."""
    plan = ImportPlan()

    # Decode content
    text = content.decode("utf-8-sig")  # handles BOM

    # Try JSON first
    if filename.endswith(".json"):
        try:
            data = _json.loads(text)
            if isinstance(data, list):
                for i, item in enumerate(data):
                    plan.total += 1
                    cat = item.get("category", item.get("module", "quiz"))
                    cat = CATEGORY_ALIASES.get(cat.lower(), cat) if cat else "quiz"
                    cleaned = {k: (v.strip() if isinstance(v, str) else v) for k, v in item.items()}

                    # Validate required content
                    has_content = any(cleaned.get(k) for k in ["stem", "prompt_text", "prompt", "body", "title"])
                    if not has_content:
                        plan.problems.append(ImportProblem(
                            row=i + 1, field="content",
                            message="No question content found (need stem, prompt_text, prompt, body, or title)",
                            severity="error",
                        ))
                        continue

                    # Category-specific validation
                    cat_lower = cat.lower() if cat else ""
                    if cat_lower in ("quiz", "grammar", "vocabulary"):
                        options = [cleaned.get(f"option_{c}", "") for c in "abcd" if cleaned.get(f"option_{c}")]
                        if len(options) < 2:
                            plan.problems.append(ImportProblem(
                                row=i + 1, field="options",
                                message="MCQ requires at least 2 options (option_a, option_b required)",
                                severity="error",
                            ))
                            continue
                    elif cat_lower == "reading":
                        if not (cleaned.get("body") or "").strip():
                            plan.problems.append(ImportProblem(
                                row=i + 1, field="body",
                                message="Reading passage requires body text",
                                severity="error",
                            ))
                            continue
                    elif cat_lower == "listening":
                        if not (cleaned.get("transcript") or "").strip():
                            plan.problems.append(ImportProblem(
                                row=i + 1, field="transcript",
                                message="Listening passage requires transcript",
                                severity="error",
                            ))
                            continue
                    elif cat_lower == "writing":
                        prompt_val = cleaned.get("prompt") or cleaned.get("stem") or ""
                        if not prompt_val.strip():
                            plan.problems.append(ImportProblem(
                                row=i + 1, field="prompt",
                                message="Writing prompt requires prompt text",
                                severity="error",
                            ))
                            continue
                    elif cat_lower == "speaking":
                        prompt_val = cleaned.get("prompt_text") or cleaned.get("stem") or ""
                        if not prompt_val.strip():
                            plan.problems.append(ImportProblem(
                                row=i + 1, field="prompt_text",
                                message="Speaking task requires prompt text",
                                severity="error",
                            ))
                            continue

                    plan.rows.append(ImportRow(row_num=i + 1, category=cat, raw=item))
                    plan.valid += 1
            return plan
        except _json.JSONDecodeError as e:
            plan.problems.append(ImportProblem(row=0, field="json", message=f"Invalid JSON: {e}"))
            return plan

    # CSV parsing
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        plan.problems.append(ImportProblem(row=0, field="file", message="No headers found"))
        return plan

    detected_cat = detect_category(reader.fieldnames)

    for i, row in enumerate(reader):
        plan.total += 1
        row_num = i + 2  # 1-indexed, skip header
        cleaned = {_normalise_header(k): v.strip() if v else "" for k, v in row.items()}

        # Determine category from 'category' or 'module' column
        cat = cleaned.get("category") or cleaned.get("module") or detected_cat
        cat = CATEGORY_ALIASES.get(cat.lower(), cat) if cat else detected_cat

        # Validate required fields
        has_content = any(cleaned.get(k) for k in ["stem", "prompt_text", "prompt", "body", "title"])
        if not has_content:
            plan.problems.append(ImportProblem(
                row=row_num, field="content",
                message="No question content found (need stem, prompt_text, prompt, body, or title)",
                severity="error",
            ))
            continue

        # Category-specific validation
        cat_lower = cat.lower() if cat else ""
        if cat_lower in ("quiz", "grammar", "vocabulary"):
            options = [cleaned.get(f"option_{c}", "") for c in "abcd" if cleaned.get(f"option_{c}")]
            if len(options) < 2:
                plan.problems.append(ImportProblem(
                    row=row_num, field="options",
                    message="MCQ requires at least 2 options (option_a, option_b required)",
                    severity="error",
                ))
                continue
        elif cat_lower == "reading":
            if not (cleaned.get("body") or "").strip():
                plan.problems.append(ImportProblem(
                    row=row_num, field="body",
                    message="Reading passage requires body text",
                    severity="error",
                ))
                continue
        elif cat_lower == "listening":
            if not (cleaned.get("transcript") or "").strip():
                plan.problems.append(ImportProblem(
                    row=row_num, field="transcript",
                    message="Listening passage requires transcript",
                    severity="error",
                ))
                continue
        elif cat_lower == "writing":
            prompt_val = cleaned.get("prompt") or cleaned.get("stem") or ""
            if not prompt_val.strip():
                plan.problems.append(ImportProblem(
                    row=row_num, field="prompt",
                    message="Writing prompt requires prompt text",
                    severity="error",
                ))
                continue
        elif cat_lower == "speaking":
            prompt_val = cleaned.get("prompt_text") or cleaned.get("stem") or ""
            if not prompt_val.strip():
                plan.problems.append(ImportProblem(
                    row=row_num, field="prompt_text",
                    message="Speaking task requires prompt text",
                    severity="error",
                ))
                continue

        plan.rows.append(ImportRow(row_num=row_num, category=cat, raw=cleaned))
        plan.valid += 1

    return plan


def get_template(category: str) -> str:
    """Generate a CSV template for the given category."""
    cat = CATEGORY_ALIASES.get(category.lower(), category)

    if cat == "quiz":
        return (
            "stem,option_a,option_b,option_c,option_d,correct_answer,explanation,difficulty,company,category\n"
            '"What is the past tense of \"go\"?",went,goed,gone,goes,A,"Go becomes went",easy,,grammar\n'
        )
    elif cat == "reading":
        return (
            "title,kind,body,company,difficulty\n"
            '"Workplace Email Etiquette",article,"Professional email writing requires...",,easy\n'
        )
    elif cat == "listening":
        return (
            "title,kind,transcript,company,audio_key,accent,plays_allowed,approx_seconds,difficulty\n"
            '"Office Meeting",short_talk,"Today we will discuss...",,,-,indian,1,45,easy\n'
        )
    elif cat == "writing":
        return (
            "title,kind,prompt,company,scenario,key_points,min_words,suggested_minutes,difficulty\n"
            '"Professional Email",email,"Write a follow-up email...",,-,"clear structure,proper greeting",150,20,easy\n'
        )
    elif cat == "speaking":
        return (
            "task_type,prompt_text,company,reference_text,audio_key,difficulty\n"
            '"read_aloud","Please read the following passage aloud",,,-,easy\n'
        )
    else:
        return "stem,option_a,option_b,option_c,option_d,correct_answer,explanation,difficulty,company,category\n"

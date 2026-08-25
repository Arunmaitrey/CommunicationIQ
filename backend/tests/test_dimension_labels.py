"""Every dimension the engine can report must have a name on the report.

This has now happened twice. When the non-speaking modules landed,
``comprehension`` had no label and a listening section's score arrived on a
student's report under its raw column name. That was fixed by adding one
entry and a comment saying what had gone wrong -- and then the very next
dimension anybody added, ``completeness``, did exactly the same thing:

    Word accuracy   ...
    completeness    ...
    Hesitation      ...

Both client maps end in "or the key itself", so a miss is never a blank. It is
always the enum, in the middle of properly written labels, on the page a
candidate is most likely to screenshot.

A comment did not stop it recurring. This does.
"""
from __future__ import annotations

import re
from pathlib import Path

from app.engine.pipeline import WEIGHTS
from app.evaluation import DIMENSIONS_BY_TASK

LABELS = (Path(__file__).resolve().parents[2]
          / "frontend" / "lib" / "dimensions.ts")


def _labelled() -> set[str]:
    text = LABELS.read_text(encoding="utf-8")
    block = re.search(r"DIMENSION_LABEL:\s*Record<string, string>\s*=\s*\{(.*?)\n\};",
                      text, re.S)
    assert block, "DIMENSION_LABEL is not where this test expects it"
    return set(re.findall(r"^\s*([a-z_]+):", block.group(1), re.M))


def _reportable() -> set[str]:
    """Everything that can reach a report: weighted, or produced by a task."""
    return set(WEIGHTS) | {d for dims in DIMENSIONS_BY_TASK.values() for d in dims}


def test_every_reportable_dimension_has_a_label():
    missing = sorted(_reportable() - _labelled())
    assert not missing, (
        f"these dimensions would appear on a report as their own column name: "
        f"{missing}. Add each to frontend/lib/dimensions.ts.")


def test_no_label_names_a_dimension_that_cannot_be_produced():
    """Dead entries make the map untrustworthy, which is how the last two
    misses survived review."""
    orphans = sorted(_labelled() - _reportable())
    assert not orphans, (
        f"labels for dimensions nothing produces: {orphans}")


def test_the_client_keeps_one_map_rather_than_a_copy_per_screen():
    """The two screens that show dimensions had a map each, and both were
    missing the same entry. One of them carried a comment about the previous
    time this happened."""
    frontend = LABELS.parents[1]
    offenders = []
    for path in frontend.rglob("*.tsx"):
        if "node_modules" in str(path) or ".next" in str(path):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for body in re.findall(r"Record<string, string>\s*=\s*\{(.*?)\n\};",
                               text, re.S):
            # The signature of a dimension map specifically. Plenty of screens
            # have a `Record<string, string>` of their own -- task types,
            # engine capabilities, plan names -- and none of those pair these
            # two keys.
            if "disfluency:" in body and "accuracy:" in body:
                offenders.append(str(path.relative_to(frontend)))

    assert not offenders, (
        f"these files declare their own dimension label map instead of "
        f"importing lib/dimensions.ts: {offenders}")

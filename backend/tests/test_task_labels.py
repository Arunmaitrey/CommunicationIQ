"""The client must have a name for every task type this server can serve.

The runner's label map had six of the sixteen. Every one of these maps ends in
"or the key itself", so a missing entry is not a blank -- it renders the enum.
A candidate partway through a hiring assessment saw the words
``reading_comprehension`` where the name of the section belongs, on a screen
they cannot go back from.

The client keeps its own list, because it cannot import Python. This is what
makes the two agree: it reads the client's list and compares it against the
server's. Two lists that match only because somebody remembered to update both
is exactly what produced the bug -- the ten task types added in Phase 4 went
into ``sections.py`` and into nothing else.
"""
from __future__ import annotations

import re
from pathlib import Path

from app.sections import SKILL_OF_TASK

CLIENT_LIST = (Path(__file__).resolve().parents[2]
               / "frontend" / "lib" / "tasks.test.ts")
CLIENT_LABELS = (Path(__file__).resolve().parents[2]
                 / "frontend" / "lib" / "tasks.ts")


def _client_task_types() -> set[str]:
    text = CLIENT_LIST.read_text(encoding="utf-8")
    block = re.search(r"SERVER_TASK_TYPES\s*=\s*\[(.*?)\]", text, re.S)
    assert block, "SERVER_TASK_TYPES is not where this test expects it"
    return set(re.findall(r'"([a-z_]+)"', block.group(1)))


def _client_labelled() -> set[str]:
    text = CLIENT_LABELS.read_text(encoding="utf-8")
    block = re.search(r"TASK_LABEL:\s*Record<string, string>\s*=\s*\{(.*?)\n\};",
                      text, re.S)
    assert block, "TASK_LABEL is not where this test expects it"
    return set(re.findall(r"^\s*([a-z_]+):", block.group(1), re.M))


def test_the_client_knows_every_task_type_the_server_serves():
    """The failure message is the fix list."""
    missing = sorted(set(SKILL_OF_TASK) - _client_task_types())
    assert not missing, (
        f"these task types exist on the server and not in the client's list: "
        f"{missing}. Add them to frontend/lib/tasks.test.ts and give each a "
        f"label in frontend/lib/tasks.ts.")


def test_the_client_does_not_list_task_types_that_do_not_exist():
    """Dead entries are how a list stops being trustworthy."""
    extra = sorted(_client_task_types() - set(SKILL_OF_TASK))
    assert not extra, (
        f"the client lists task types the server cannot serve: {extra}")


def test_every_server_task_type_has_a_label_in_the_client():
    """The list agreeing is not the same as the labels being written.

    Checked separately because the two files can drift apart on their own:
    a type could be added to the list, fail this, and be fixed by adding it to
    the map -- which is the order the fix should happen in.
    """
    missing = sorted(set(SKILL_OF_TASK) - _client_labelled())
    assert not missing, (
        f"these task types have no label and would render as their own enum "
        f"to a candidate: {missing}")

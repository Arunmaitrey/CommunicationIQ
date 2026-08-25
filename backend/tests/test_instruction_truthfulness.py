"""Candidate-facing instructions must describe what the task actually does.

The defect this guards against (PM increment 2026-08-24): TCS Section C told
the candidate to "Read the workplace situation" while the situation was
PLAYED, once, as audio — a candidate who waited to read it lost the one
play. That is not a wording nit; it changes candidate behaviour inside a
live assessment.

The guard is general, not a TCS pin: every blueprint's section instructions
are compared against the section's own configuration (prompt modality,
response mode, replay allowance, timing) using the same task metadata the
runner dispatches on. A new format whose instructions lie about the
mechanics fails here before any candidate meets it.

Known, PM-deferred violations live in ``KNOWN_VIOLATIONS`` — visible,
exactly pinned, and asserted to be the ONLY violations. Fixing one without
removing its ledger entry fails the test, so the ledger can only shrink.
"""
from __future__ import annotations

import re

from app import formats
from app import sections as S

# ---------------------------------------------------------------------------
# The facts, from the same configuration the runner obeys
# ---------------------------------------------------------------------------


def _facts(sec):
    return {
        # A section's prompt is played iff plays are allowed at all.
        "audio_prompt": sec.prompt_plays_allowed > 0,
        # What the candidate cannot read: task types whose played material is
        # the reference text and never shown before answering.
        "unreadable_prompt": (sec.prompt_plays_allowed > 0
                              and S.speaks_reference(sec.task_type)),
        "mode": S.mode_of(sec.task_type),      # speak | select | write
        # Blueprints express replay purely through the play allowance: one
        # play is one-shot; more than one is a replay allowance.
        "replay": sec.prompt_plays_allowed > 1,
        "one_shot": sec.prompt_plays_allowed == 1,
        "response_seconds": sec.response_seconds,
        "prep_seconds": sec.prep_seconds,
        "budget_seconds": getattr(sec, "budget_seconds", None),
    }


# "Type 'Okay'" is a real mechanic (the acknowledgement gate types the word
# Okay), not a claim about how questions are answered. Stripped before the
# type-claims check so it cannot false-positive a select-mode section.
_ACK_GATE = re.compile(r"type\s+['\"]?okay['\"]?", re.I)


def _violations_for(code: str, sec) -> list[str]:
    instr = (sec.instructions or "").lower()
    if not instr:
        return []
    f = _facts(sec)
    out: list[str] = []
    checked = _ACK_GATE.sub(" ", instr)

    # -- prompt modality ---------------------------------------------------
    if f["unreadable_prompt"] and re.search(r"\bread\b", instr):
        out.append("says read, but the prompt is played as audio")
    if not f["audio_prompt"] and re.search(
            r"\b(listen|you (will |)hear|hear (the|a|it)|plays once|beep)\b",
            instr):
        out.append("says listen/hear, but nothing is played")

    # -- response mode -----------------------------------------------------
    if f["mode"] == "select" and re.search(r"\btype\b|\btyping\b|write your answer",
                                           checked):
        out.append("says type, but the answer is chosen")
    if f["mode"] == "write" and re.search(r"\b(choose|select|pick) (the|one|an)\b",
                                          instr):
        out.append("says choose, but the answer is typed")
    if f["mode"] != "speak" and re.search(
            r"\brecord(ing|ed)?\b|say it aloud|\bspeak your\b|\bout loud\b", instr):
        out.append("claims speaking/recording, but none occurs")
    if f["mode"] == "speak" and re.search(
            r"\btype\b|\b(choose|select) (the|one|an)\b", checked):
        out.append("spoken item claims typing/choosing")

    # -- one-shot vs replay ------------------------------------------------
    if f["replay"] and re.search(
            r"\b(only once|plays once|once only|hear (it|each[\w ]*) once|listen once)\b",
            instr):
        out.append("claims one play, but replay is allowed")
    if f["one_shot"] and re.search(
            r"\b(replay|listen again|hear it again|play it again)\b", instr):
        out.append("claims replay, but the play is one-shot")

    # -- timing ------------------------------------------------------------
    m = re.search(r"(\d+)\s*seconds? to (answer|speak|respond|reply)", instr)
    if m and int(m.group(1)) != f["response_seconds"]:
        out.append(f"claims {m.group(1)}s to answer; configured "
                   f"{f['response_seconds']}s")
    m = re.search(r"(\d+)\s*seconds? (of thinking|to think|to prepare|of prep)",
                  instr)
    if m and int(m.group(1)) != f["prep_seconds"]:
        out.append(f"claims {m.group(1)}s to think; configured {f['prep_seconds']}s")
    m = re.search(r"(\d+)\s*minutes? to (complete|finish|answer)", instr)
    if m and f["budget_seconds"] and int(m.group(1)) * 60 != f["budget_seconds"]:
        out.append(f"claims {m.group(1)} minutes; configured "
                   f"{f['budget_seconds']}s budget")
    if "untimed" in instr and f["response_seconds"] > 0:
        out.append("claims untimed, but the item has a clock")

    return [f"{code} / {sec.title}: {v}" for v in out]


def _all_violations() -> list[str]:
    found: list[str] = []
    for blueprint in formats.ALL_BLUEPRINTS:
        for sec in blueprint.sections:
            found.extend(_violations_for(blueprint.code, sec))
    return found


# ---------------------------------------------------------------------------
# The ledger: violations the PM has seen and explicitly deferred
# ---------------------------------------------------------------------------
#
# Each entry is a real instruction/mechanic mismatch, known to the PM, and
# parked by decision — NOT an accepted state. Fixing one requires deleting
# its line here (the equality assertion below enforces that), so this list
# can only shrink. Do not add to it to silence a failure: a new entry means
# a new lie to a candidate, and that needs a PM decision, not a ledger line.
# Empty since 2026-08-24 (Versant Part A was the last entry). Keep it empty:
# a new entry means a new lie to a candidate and needs a PM decision.
KNOWN_VIOLATIONS: set[str] = set()


def test_no_instruction_contradicts_its_own_configuration():
    found = set(_all_violations())
    new = found - KNOWN_VIOLATIONS
    fixed_but_still_listed = KNOWN_VIOLATIONS - found
    assert not new, f"instruction lies to the candidate: {sorted(new)}"
    assert not fixed_but_still_listed, (
        "fixed — remove from KNOWN_VIOLATIONS: "
        f"{sorted(fixed_but_still_listed)}")


def test_tcs_section_c_states_the_audio_mechanic():
    """The fix itself, pinned: the instruction says the situation is spoken
    and one-shot, and no longer tells the candidate to read it."""
    blueprint = formats.BY_CODE["company_round_tcs"]
    sec = next(s for s in blueprint.sections if s.title == "Section C - Conversation")
    # The mechanic is unchanged — only the description of it.
    assert sec.task_type == "conversation_question"
    assert sec.prompt_plays_allowed == 1
    assert sec.item_count == 3 and sec.response_seconds == 40 and sec.prep_seconds == 0
    instr = sec.instructions.lower()
    assert "listen" in instr
    assert "once" in instr
    assert "read" not in instr
    assert _violations_for(blueprint.code, sec) == []


def test_the_guard_actually_catches_the_original_defect():
    """Adversarial: the exact pre-fix TCS wording must be flagged. If the
    guard cannot see the defect that motivated it, it guards nothing."""
    import dataclasses
    blueprint = formats.BY_CODE["company_round_tcs"]
    sec = next(s for s in blueprint.sections if s.title == "Section C - Conversation")
    old = dataclasses.replace(sec, instructions=(
        "Read the workplace situation and respond as you would to a "
        "colleague, in one to three sentences."))
    assert any("says read" in v for v in _violations_for("company_round_tcs", old))


def test_the_guard_is_not_tcs_specific():
    """Adversarial, on a NON-TCS format: plant each class of lie into a
    Cognizant section and the guard must flag every one."""
    import dataclasses
    blueprint = formats.BY_CODE["company_round_cognizant"]
    spoken = next(s for s in blueprint.sections
                  if S.mode_of(s.task_type) == "speak"
                  and s.prompt_plays_allowed > 0
                  and S.speaks_reference(s.task_type))
    cases = [
        ("Read the passage and answer.", "says read"),
        ("You may listen again as often as you like.", "claims replay"),
        ("Type the answer in the box.", "claims typing"),
        ("You have 99 seconds to answer.", "claims 99s"),
        ("This part is untimed.", "claims untimed"),
    ]
    for wording, expect in cases:
        planted = dataclasses.replace(spoken, instructions=wording)
        got = _violations_for(blueprint.code, planted)
        assert any(expect in v for v in got), (wording, got)

    chosen = next(s for s in blueprint.sections
                  if S.mode_of(s.task_type) == "select")
    planted = dataclasses.replace(
        chosen, instructions="Record your spoken answer after the tone.")
    assert any("claims speaking/recording" in v
               for v in _violations_for(blueprint.code, planted))


def test_the_ack_gate_wording_is_not_a_type_claim():
    """SpeechX Section D really does ask the candidate to type 'Okay' — the
    acknowledgement gate — while questions are answered by choosing. That is
    a true statement and must not be flagged."""
    blueprint = formats.BY_CODE["speechx_style_full"]
    sec = next(s for s in blueprint.sections if "Listen & Answer" in s.title)
    assert "type 'okay'" in sec.instructions.lower()
    assert _violations_for(blueprint.code, sec) == []

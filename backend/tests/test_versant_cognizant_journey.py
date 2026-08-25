"""The last two candidate-trust defects (PM increment 2026-08-24).

Versant Part A promised behaviour the product does not deliver — a spoken
sentence number and an end-of-window beep. The claim changed, not the
assessment: the sentence is on screen, a start tone begins the recording,
and the instruction now says exactly that.

Cognizant Section A holds three materially different sub-tasks (read
sentences, read word lists, listen & repeat) whose instructions the
candidate never saw when moving between them, while the question counter
restarted (1/8, 1/3, 1/8) — which reads as the assessment restarting. The
source (Cognizant_Communication_Round.pptx, screenshots "organized
sequence-wise") shows continuous numbering within each lettered section
(A: Q1–Q23; C: Q1–Q8 across MCQ and text entry) and a task line on every
numbered question. Both are now flagged behaviour: ``continuous_numbering``
and ``show_instruction`` on every Cognizant section. Counts, task types,
timing, audio and scoring are untouched, and SVAR's frozen one-card-per-
part presentation gets neither flag.
"""
from __future__ import annotations

from app import formats

VERSANT = formats.BY_CODE["versant_style_speaking_listening"]
COGNIZANT = formats.BY_CODE["company_round_cognizant"]


# --------------------------------------------------------------------------
# Versant Part A
# --------------------------------------------------------------------------

def test_part_a_claims_only_what_the_candidate_experiences():
    sec = VERSANT.sections[0]
    assert sec.title == "Part A - Reading"
    instr = sec.instructions.lower()
    # The unsupported claims, gone.
    assert "sentence number" not in instr
    assert "beep" not in instr
    assert "hear" not in instr
    # What actually happens: the sentence is on screen, read aloud, and the
    # recording begins after the runner's start tone (lib/audio.beep -- the
    # one tone the product genuinely plays).
    assert "read" in instr and "screen" in instr and "aloud" in instr
    assert "tone" in instr
    # The assessment itself is unchanged: on-screen prompt, no audio,
    # one-shot recording, same clock.
    assert sec.task_type == "read_aloud"
    assert sec.prompt_plays_allowed == 0
    assert (sec.item_count, sec.prep_seconds, sec.response_seconds) == (6, 3, 20)


def test_the_old_part_a_wording_can_never_return():
    """Adversarial: the withdrawn wording must fail the cross-format
    truthfulness guard, so reverting it turns the build red."""
    import dataclasses

    from tests.test_instruction_truthfulness import (KNOWN_VIOLATIONS,
                                                     _violations_for)
    old = dataclasses.replace(VERSANT.sections[0], instructions=(
        "Read the sentences out loud when you hear the sentence number. "
        "Stop speaking at the beep."))
    got = _violations_for(VERSANT.code, old)
    assert any("nothing is played" in v for v in got), got
    # And the ledger that once excused it is empty — it may only shrink.
    assert KNOWN_VIOLATIONS == set()


# --------------------------------------------------------------------------
# Cognizant Section A
# --------------------------------------------------------------------------

def test_every_subsection_carries_its_own_instruction():
    a_parts = [s for s in COGNIZANT.sections if s.title.startswith("Section A")]
    assert [s.title for s in a_parts] == [
        "Section A - Reading & Listening", "Section A - Word Lists",
        "Section A - Listen & Repeat"]
    texts = [s.instructions for s in a_parts]
    assert all(texts), "a sub-section without an instruction leaves the candidate guessing"
    assert len(set(texts)) == 3, "the sub-tasks differ; identical wording would mislead"
    # Anchored to the source's own task lines.
    assert "sentence" in texts[0].lower()
    assert "isolated words" in texts[1].lower()
    assert "repeat" in texts[2].lower()


def test_cognizant_presents_like_its_source_and_svar_stays_frozen():
    # Every Cognizant section: a task line on each question screen, and
    # numbering that runs continuously through the lettered section --
    # exactly the two things the source screenshots establish.
    for sec in COGNIZANT.sections:
        assert sec.show_instruction is True, sec.title
        assert sec.continuous_numbering is True, sec.title
    # SVAR's presentation is frozen: one introduction per lettered part,
    # nothing per question. The new flag must not leak into it.
    svar = formats.BY_CODE["svar_full_simulation"]
    assert all(not sec.show_instruction for sec in svar.sections)


def test_structure_is_untouched_by_the_journey_fix():
    assert [(s.task_type, s.item_count, s.prep_seconds, s.response_seconds,
             s.prompt_plays_allowed) for s in COGNIZANT.sections] == [
        ("read_aloud", 8, 0, 15, 0),
        ("read_aloud", 3, 0, 15, 0),
        ("repeat_sentence", 8, 0, 15, 1),
        ("open_response", 3, 30, 60, 0),
        ("sentence_completion", 5, 0, 0, 0),
        ("voice_change", 3, 0, 0, 0),
        ("listening_comprehension", 6, 0, 0, 1),
    ]


# --------------------------------------------------------------------------
# Through the runner payload
# --------------------------------------------------------------------------

async def test_the_payload_carries_the_journey_flags(client):
    from tests.conftest import auth, login
    token = await login(client, "student")
    await client.post("/api/v1/student/consent", headers=auth(token),
                      json={"scopes": ["recording"]})
    profiles = (await client.get("/api/v1/student/profiles",
                                 headers=auth(token))).json()

    cog = next(p for p in profiles if p["code"] == "company_round_cognizant")
    items = (await client.post("/api/v1/student/attempts", headers=auth(token),
                               json={"profile_id": cog["id"],
                                     "mode": "practice"})).json()["items"]
    assert len(items) == 36
    assert all(i["show_instruction"] for i in items)
    assert all(i["continuous_numbering"] for i in items)
    # The three Section A sub-tasks reach the candidate with three different
    # instructions, in the source's order, at the source's counts.
    a_instr = []
    for i in items:
        if i["section_title"].startswith("Section A") and \
                (not a_instr or a_instr[-1][0] != i["section_title"]):
            a_instr.append((i["section_title"], i["instructions"]))
    assert [t for t, _ in a_instr] == [
        "Section A - Reading & Listening", "Section A - Word Lists",
        "Section A - Listen & Repeat"]
    assert len({instr for _, instr in a_instr}) == 3
    counts = {}
    for i in items:
        counts[i["section_title"]] = counts.get(i["section_title"], 0) + 1
    assert counts["Section A - Reading & Listening"] == 8
    assert counts["Section A - Word Lists"] == 3
    assert counts["Section A - Listen & Repeat"] == 8

    # SVAR payload: the new flag stays off -- its presentation is frozen.
    svar = next(p for p in profiles if p["code"] == "svar_full_simulation")
    svar_items = (await client.post(
        "/api/v1/student/attempts", headers=auth(token),
        json={"profile_id": svar["id"], "mode": "practice"})).json()["items"]
    assert len(svar_items) == 67
    assert all(not i["show_instruction"] for i in svar_items)

"""The SVAR-style profile says what it is -- and nothing it is not.

PM acceptance (2026-08-23): our profile imitates a specific four-section
communication assessment as deployed on the SVAR platform, which is what our
reference screenshots and walkthrough show. It is not SHL's core SVAR Spoken
English product (a ~15-minute, max-38-question spoken test, per SHL's own
fact sheet), so it must never call itself that. These tests pin the copy so
the overclaim cannot creep back in, and pin the structure so that fixing the
copy did not touch the assessment.
"""
from __future__ import annotations

import re

from app import formats, evaluation

SVAR = formats.BY_CODE["svar_full_simulation"]

# Phrases that would turn "modelled on" into "is". Case-insensitive.
# "Not official SHL or employer material" is the one permitted use of the
# word; any other "official" is the claim this list exists to stop.
FORBIDDEN = (
    r"\bthe svar test\b", r"\bfull svar\b", r"(?<!not )\bofficial\b",
    r"\bexact svar\b", r"\bactual svar\b", r"\bfull simulation\b",
    r"\bthe full svar", r"\bdelivered on the svar platform\b", r"\bwipro\b",
)


def _all_copy() -> str:
    return " ".join([SVAR.name, SVAR.description, SVAR.provenance,
                     *SVAR.what_to_expect,
                     *(s.instructions for s in SVAR.sections)])


def test_name_is_the_approved_positioning():
    assert SVAR.name == "SVAR-style Communication Assessment (4-section)"
    assert "delivered on the SVAR platform" not in SVAR.description


def test_no_copy_claims_to_be_the_svar_test():
    text = _all_copy()
    for pattern in FORBIDDEN:
        assert not re.search(pattern, text, re.IGNORECASE), pattern


def test_provenance_is_stated_briefly_and_without_legalese():
    assert "third-party walkthrough" in SVAR.provenance
    assert "our own configuration" in SVAR.provenance
    # Discreet, not a disclaimer wall: one short paragraph, no legal framing
    # in the student's line of sight.
    assert len(SVAR.provenance) < 200
    for word in ("affiliated", "endorsed", "trademark"):
        assert word not in SVAR.provenance.lower()


def test_section_b_presents_speaking_points_as_suggestions():
    """The reference shows speaking points as questions under the topic and
    calls them "just suggestions". Our copy says exactly that, and the topic
    is a visible prompt (VISIBLE_PROMPT_TASKS includes open_response)."""
    b = next(s for s in SVAR.sections if s.task_type == "open_response")
    text = b.instructions.lower()
    assert "speaking points" in text and "suggestions" in text
    assert "other points" in text
    assert "topic" in text


def test_untimed_sections_are_the_typed_and_chosen_ones():
    # The card renders response_seconds == 0 as "Untimed". Pin which sections
    # that is, so a per-item timer cannot be introduced by accident.
    untimed = [s.task_type for s in SVAR.sections if s.response_seconds == 0]
    assert untimed == ["sentence_completion"] * 4 + ["voice_change",
                                                     "listening_comprehension"]


# ---------------------------------------------------------------------------
# The closure structure (PM decision 2026-08-23), pinned item by item.
#
# Source: observed third-party walkthrough evidence. Directly evidenced:
# A = 18, A1 15 s, A2 30 s, A3 15 s/once, A budget 10 min; B = 3 topics,
# 90 s think, 60 s speak, speaking points as suggestions; C = 34 in
# 8/8/6/6/6, 15 min; D three questions per clip, once, 10 min. Inferred:
# A1 = 8, A2 = 2, A3 = 8. Ours: D clip count (4) and D answer format.
# ---------------------------------------------------------------------------

def _by_title(prefix):
    return [s for s in SVAR.sections if s.title.startswith(prefix)]


def test_section_a_is_eighteen_items_8_2_8():
    a = _by_title("Section A")
    assert [s.item_count for s in a] == [8, 2, 8]
    assert sum(s.item_count for s in a) == 18
    assert [s.task_type for s in a] == ["read_aloud", "read_aloud", "repeat_sentence"]
    assert [s.response_seconds for s in a] == [15, 30, 15]
    assert a[2].prompt_plays_allowed == 1
    assert all(s.budget_seconds == 600 for s in a), "Section A: 10-minute budget"
    assert "18 statements or audio clips" in a[0].instructions
    assert "10 minutes" in a[0].instructions


def test_section_b_is_three_topics_with_think_time_and_suggestions():
    b = _by_title("Section B")
    assert len(b) == 1
    assert (b[0].task_type, b[0].item_count, b[0].prep_seconds,
            b[0].response_seconds) == ("open_response", 3, 90, 60)
    assert "suggestions" in b[0].instructions.lower()
    assert "speaking points" in b[0].instructions.lower()
    assert b[0].budget_seconds == 0, "no section budget is evidenced for B"


def test_section_c_is_thirty_four_in_five_categories():
    c = _by_title("Section C")
    assert [s.item_count for s in c] == [8, 8, 6, 6, 6]
    assert sum(s.item_count for s in c) == 34
    assert [s.task_type for s in c] == ["sentence_completion"] * 4 + ["voice_change"]
    assert [tuple(s.selection.get("topics", ())) for s in c[:4]] == [
        ("verb_forms",), ("tenses",), ("articles",), ("prepositions",)]
    assert all(s.budget_seconds == 900 for s in c), "Section C: 15-minute budget"
    assert "34" in c[0].instructions and "15 minutes" in c[0].instructions


def test_section_d_is_three_questions_per_clip_once_with_budget():
    d = _by_title("Section D")
    assert len(d) == 1
    assert d[0].task_type == "listening_comprehension"
    assert d[0].item_count % 3 == 0, "three questions per clip is evidenced"
    assert d[0].prompt_plays_allowed == 1
    assert d[0].budget_seconds == 600, "Section D: 10-minute budget"
    assert "three questions" in d[0].instructions
    # The clip count is OUR configuration; the source does not show it. If
    # this changes, change the disclosure too.
    assert d[0].item_count == 12


def test_whole_structure_is_67_items_in_ten_subsections():
    assert len(SVAR.sections) == 10
    assert sum(s.item_count for s in SVAR.sections) == 67
    assert SVAR.estimated_minutes == 54 == formats.duration_minutes(SVAR)
    assert formats.section_budgets(SVAR.code) == {
        s.title: s.budget_seconds for s in SVAR.sections if s.budget_seconds}


def test_no_stale_structure_remains():
    """The superseded assumptions must be gone: A = 20, A3 = 10, C = 25 + 10."""
    counts = [s.item_count for s in SVAR.sections]
    assert 10 not in counts and 25 not in counts
    assert sum(s.item_count for s in _by_title("Section A")) != 20


def test_grammar_bank_matches_the_categories_and_is_clean():
    """Automated content checks for the Section C bank (PM decision 7)."""
    from app import grammar_bank, completion_bank
    from collections import Counter
    counts = Counter(cat for _, _, cat in grammar_bank.ITEMS)
    assert counts == {"verb_forms": 8, "tenses": 8, "articles": 6, "prepositions": 6}
    stems = [s for s, _, _ in grammar_bank.ITEMS]
    assert len(set(stems)) == len(stems), "duplicate stems"
    legacy = {s for s, _, _ in completion_bank.ITEMS}
    assert not legacy & set(stems), "reused an old item to reach 34"
    for stem, accepted, _ in grammar_bank.ITEMS:
        assert "___" in stem, stem
        choices = grammar_bank.choices_in(stem)
        assert len(choices) >= 2, f"no bracketed choices: {stem}"
        right = [c for c in choices if completion_bank.is_correct(c, accepted)]
        assert len(right) == 1, f"exactly one correct choice expected: {stem}"
        assert all(completion_bank.is_correct(a, accepted) for a in accepted)
        # Every wrong choice must be marked wrong.
        for c in choices:
            if c not in right:
                assert not completion_bank.is_correct(c, accepted), (stem, c)


def test_every_topic_has_three_suggestion_questions():
    from app.seed import OPEN_RESPONSE, TOPIC_CUES
    for topic in OPEN_RESPONSE:
        cues = TOPIC_CUES.get(topic)
        assert cues and len(cues) == 3, topic
        assert all(c.strip().endswith("?") for c in cues), topic
    # The one reference-evidenced topic and its wording.
    assert TOPIC_CUES["The Importance of Healthy Eating."][0] == \
        "Why is maintaining a healthy diet important?"


def test_positioning_copy_is_the_approved_final_wording():
    assert SVAR.description == (
        "A simulation of an observed four-section communication assessment "
        "— reading & listening, speaking, grammar and comprehension.")
    assert SVAR.provenance == (
        "Based on a publicly available third-party walkthrough of one "
        "assessment sitting. Not official SHL or employer material; some "
        "details are our own configuration.")
    text = _all_copy().lower()
    for bad in ("delivered on the svar platform", "wipro", "shl assessment",
                "actual svar", "exact svar", "exact reproduction", "full svar",
                "the svar test"):
        assert bad not in text, bad
    assert "official" not in text.replace("not official", "")


def test_results_note_is_for_the_student_and_claims_no_unsupported_competency():
    note = evaluation.MODELS["svar_full_simulation"].structure_source
    assert "four-section format" in note
    assert "does not reproduce every competency" in note
    labels = {s.label for s in evaluation.MODELS["svar_full_simulation"].subscores}
    assert labels == {"Pronunciation", "Fluency", "Active Listening", "Grammar"}
    assert "Vocabulary" not in labels and "Spoken English Understanding" not in labels


def test_other_formats_do_not_carry_the_svar_provenance():
    for b in formats.ALL_BLUEPRINTS:
        if b.code != "svar_full_simulation":
            assert "SVAR" not in b.provenance, b.code


def test_one_authoritative_svar_subscore_definition():
    """The blueprint grouping is derived from the scoring model, not retyped.

    The audit suspected the hand-typed tuple had drifted from the model on
    Active Listening. Checked: it had not -- both carried
    (comprehension, accuracy), fed by Listen & Answer and Listen & Repeat.
    The derivation makes that agreement structural rather than lucky.
    """
    model = evaluation.MODELS["svar_full_simulation"]
    assert [(s.label, tuple(s.from_dimensions)) for s in SVAR.subscores] == \
        [(s.label, tuple(s.dimensions)) for s in model.subscores]
    active = next(s for s in model.subscores if s.label == "Active Listening")
    assert active.task_types == frozenset({"listening_comprehension", "repeat_sentence"})
    assert active.dimensions == ("comprehension", "accuracy")


def test_duration_fields_describe_the_implementation():
    """Pace range + hard stop, never 'up to' the estimate.

    `estimated_minutes` is the ceiling of the timed windows; untimed sections
    have no clock; the sitting is bounded by app/deadline.py's allowance.
    """
    from app import deadline
    assert formats.typical_minutes(SVAR) < SVAR.estimated_minutes
    assert deadline.allowance_minutes(SVAR.estimated_minutes) == 81
    assert deadline.allowance_minutes(SVAR.estimated_minutes) > SVAR.estimated_minutes


async def test_runner_payload_carries_budgets_cues_and_counts(client):
    """Live payload, not the blueprint: 67 items; every A/C/D item carries its
    section budget (the written and chosen builders too -- the first cut set
    it only on spoken items); every Section B topic has three suggestions."""
    from collections import Counter
    from tests.conftest import auth, login
    token = await login(client, "student")
    await client.post("/api/v1/student/consent", headers=auth(token),
                      json={"scopes": ["recording"]})
    profiles = (await client.get("/api/v1/student/profiles", headers=auth(token))).json()
    svar = next(p for p in profiles if p["code"] == "svar_full_simulation")
    assert [(s["title"].split(" - ")[0], s["budget_seconds"]) for s in svar["sections"]] == [
        ("Section A1", 600), ("Section A2", 600), ("Section A3", 600), ("Section B", 0),
        ("Section C1", 900), ("Section C2", 900), ("Section C3", 900), ("Section C4", 900),
        ("Section C5", 900), ("Section D", 600)]
    payload = (await client.post("/api/v1/student/attempts", headers=auth(token),
                                 json={"profile_id": svar["id"], "mode": "practice"})).json()
    items = payload["items"]
    assert len(items) == 67
    per = Counter(i["section_title"].split(" - ")[0] for i in items)
    assert per == {"Section A1": 8, "Section A2": 2, "Section A3": 8, "Section B": 3,
                   "Section C1": 8, "Section C2": 8, "Section C3": 6, "Section C4": 6,
                   "Section C5": 6, "Section D": 12}
    for i in items:
        letter = i["section_title"].split(" ")[1][0]
        expected = {"A": 600, "B": 0, "C": 900, "D": 600}[letter]
        assert i["section_budget_seconds"] == expected, i["section_title"]
    for i in items:
        if i["task_type"] == "open_response":
            assert len(i["key_points"]) == 3, "three speaking-point questions"
        elif i["task_type"] == "sentence_completion":
            assert "___" in i["question"] and "(" in i["question"], "bracketed choices"


async def test_prompt_audio_is_prewarmed_at_attempt_start(client):
    """Hardware UAT D2: the first Listen & Repeat clip took 12 s and a later
    one over 20 s because each was synthesised on first request. Starting an
    attempt now schedules every clip it will play into the tts cache."""
    from app import tts
    from app.routers import attempts as attempts_router
    from app.db import tenant_sessionmaker
    from tests.conftest import auth, login

    token = await login(client, "student")
    await client.post("/api/v1/student/consent", headers=auth(token),
                      json={"scopes": ["recording"]})
    profiles = (await client.get("/api/v1/student/profiles", headers=auth(token))).json()
    svar = next(p for p in profiles if p["code"] == "svar_full_simulation")
    payload = (await client.post("/api/v1/student/attempts", headers=auth(token),
                                 json={"profile_id": svar["id"], "mode": "practice"})).json()

    async with tenant_sessionmaker("stmarys")() as s:
        texts = await attempts_router._spoken_texts_for(s, payload["attempt_id"])
    # A3 has 8 heard sentences and D four clips: 12 distinct clips, and
    # nothing for the read-aloud, speaking or typed items.
    assert len(texts) == 8 + 4, [t[:30] for t, _ in texts]
    assert all(t.strip() for t, _ in texts)

    # The background task is best-effort; on a host that can synthesise it
    # must leave every clip in the cache so Play Audio is immediate.
    attempts_router._prewarm_prompt_audio(texts)
    if tts._available():
        for text, accent in texts:
            assert tts.synthesize(text, accent) is not None
            assert tts._key(text, tts._VOICE.get(accent, tts._VOICE["indian"])) in tts._cache


async def test_runner_payload_marks_answered_items_so_a_reload_resumes(client):
    """Hardware UAT D7: a reload restarted at item 1. The payload now says
    which items the server already holds; the runner starts at the first
    open one."""
    from tests.conftest import auth, login
    token = await login(client, "student")
    await client.post("/api/v1/student/consent", headers=auth(token),
                      json={"scopes": ["recording"]})
    profiles = (await client.get("/api/v1/student/profiles", headers=auth(token))).json()
    svar = next(p for p in profiles if p["code"] == "svar_full_simulation")
    payload = (await client.post("/api/v1/student/attempts", headers=auth(token),
                                 json={"profile_id": svar["id"], "mode": "practice"})).json()
    aid = payload["attempt_id"]
    assert all(i["answered"] is False for i in payload["items"])

    first, second = payload["items"][0], payload["items"][1]
    # A deliberate skip counts as answered; so does a chosen/typed answer.
    r = await client.post(f"/api/v1/student/attempts/{aid}/responses/{first['response_id']}/skip",
                          headers=auth(token))
    assert r.status_code == 200, r.text
    again = (await client.get(f"/api/v1/student/attempts/{aid}/runner", headers=auth(token))).json()
    flags = [i["answered"] for i in again["items"]]
    assert flags[0] is True and flags[1] is False, flags
    assert again["items"][1]["response_id"] == second["response_id"]
    assert sum(flags) == 1

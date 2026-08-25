"""SpeechX-style (Mercer | Mettl): structure, flags and content guard.

Source: the supplied Mettl screens. Pinned here so the profile cannot drift
back to the 10+8 / 3 / 10+6 / 6 shape that contradicted them. Also the
regression guard that the section-behaviour flags reproduce SVAR's frozen
behaviour exactly (SVAR itself is not touched by this work).
"""
from __future__ import annotations

from collections import Counter

from app import evaluation, formats

SX = formats.BY_CODE["speechx_style_full"]
SVAR = formats.BY_CODE["svar_full_simulation"]


def _by(prefix, b=SX):
    return [s for s in b.sections if s.title.startswith(prefix)]


def test_speechx_section_a_is_18_read_and_record_items_in_10_minutes():
    a = _by("Section A")
    assert sum(s.item_count for s in a) == 18
    assert [s.task_type for s in a] == ["read_aloud", "repeat_sentence"]
    assert all(s.response_seconds == 15 for s in a)
    assert all(s.budget_seconds == 600 for s in a)
    assert "18 statements/audio clips" in a[0].instructions and "10 min" in a[0].instructions


def test_speechx_section_b_is_3_topics_30s_think_60s_speak_with_skip_thinking():
    b = _by("Section B")
    assert len(b) == 1
    assert (b[0].item_count, b[0].prep_seconds, b[0].response_seconds) == (3, 30, 60)
    assert b[0].skip_prep is True, "source: 'you can skip and start recording'"
    assert b[0].allow_skip is False and b[0].fixed_window is False and b[0].show_cues is False
    assert b[0].budget_seconds == 600
    assert "30 seconds to think" in b[0].instructions and "1 minute" in b[0].instructions


def test_speechx_section_c_is_34_in_15_minutes():
    c = _by("Section C")
    assert sum(s.item_count for s in c) == 34
    assert [s.item_count for s in c] == [8, 8, 6, 6, 6]
    assert [s.task_type for s in c] == ["sentence_completion"] * 4 + ["voice_change"]
    assert all(s.budget_seconds == 900 for s in c)
    assert "34 questions" in c[0].instructions and "15 minutes" in c[0].instructions


def test_speechx_section_d_is_4_clips_x_3_with_a_clip_level_okay_gate():
    d = _by("Section D")
    assert len(d) == 1
    assert d[0].item_count == 12 and d[0].item_count % 3 == 0
    assert d[0].ack_gate == "clip"
    assert d[0].prompt_plays_allowed == 1
    assert d[0].budget_seconds == 600
    assert "next three questions" in d[0].instructions and "10 minutes" in d[0].instructions


def test_speechx_numbering_runs_through_each_section():
    assert all(s.continuous_numbering for s in SX.sections)
    assert SX.estimated_minutes == formats.duration_minutes(SX)


def test_speechx_positioning_copy():
    assert SX.name == "SpeechX-style Communication Assessment (Mercer | Mettl)"
    assert "Full" not in SX.name
    assert "shown in our reference material" in SX.description
    assert "Not official Mercer" in SX.provenance
    text = (SX.name + SX.description + SX.provenance).lower()
    for bad in ("official speechx", "the speechx test", "exact", "actual"):
        assert bad not in text


def test_speechx_subscores_are_the_models_not_a_retyped_copy():
    model = evaluation.MODELS["speechx_style_full"]
    assert [(s.label, tuple(s.from_dimensions)) for s in SX.subscores] == \
        [(s.label, tuple(s.dimensions)) for s in model.subscores]
    assert "Active Listening" not in [s.label for s in SX.subscores]


# -- the flags reproduce SVAR's frozen behaviour -----------------------------

def test_svar_behaviour_flags_match_its_frozen_behaviour():
    """What the runner did for svar_style by name, it now does by flag. The
    SVAR structure itself is pinned in test_svar_positioning and untouched."""
    f = formats.section_behaviour("svar_full_simulation")
    b = f["Section B - Speak on the Topic"]
    assert b["fixed_window"] and b["allow_skip"] and b["show_cues"]
    assert not b["skip_prep"] and b["ack_gate"] == ""
    d = f["Section D - Listen & Answer"]
    assert d["ack_gate"] == "section" and not d["allow_skip"]
    assert all(v["continuous_numbering"] for v in f.values())
    assert all(not v["fixed_window"] for t, v in f.items() if "Section B" not in t)
    assert {t: v["budget_seconds"] for t, v in f.items()} == formats.section_budgets("svar_full_simulation") | {
        "Section B - Speak on the Topic": 0}


def test_no_other_format_carries_the_svar_flags_by_accident():
    """Behaviour flags are deliberate, per-format, PM-approved decisions.

    SVAR and SpeechX carry their evidenced sets. Cognizant carries exactly
    continuous numbering and the per-question task line (PM increment
    2026-08-24; both established by its source deck) and nothing else.
    Everything else carries nothing."""
    for b in formats.ALL_BLUEPRINTS:
        if b.code in ("svar_full_simulation", "speechx_style_full"):
            continue
        for s in b.sections:
            assert not (s.fixed_window or s.allow_skip or s.skip_prep or s.ack_gate
                        or s.show_cues or s.budget_seconds), (b.code, s.title)
            if b.code == "company_round_cognizant":
                assert s.continuous_numbering and s.show_instruction, (b.code, s.title)
            else:
                assert not (s.continuous_numbering or s.show_instruction), (b.code, s.title)


# -- content guard (live estate) --------------------------------------------

async def test_speechx_content_pools_support_one_sitting_without_repetition(client):
    from tests.conftest import auth, login
    token = await login(client, "student")
    await client.post("/api/v1/student/consent", headers=auth(token), json={"scopes": ["recording"]})
    profiles = (await client.get("/api/v1/student/profiles", headers=auth(token))).json()
    sx = next(p for p in profiles if p["code"] == "speechx_style_full")
    payload = (await client.post("/api/v1/student/attempts", headers=auth(token),
                                 json={"profile_id": sx["id"], "mode": "practice"})).json()
    items = payload["items"]
    per = Counter(i["section_title"].split(" - ")[0] for i in items)
    assert per == {"Section A1": 10, "Section A2": 8, "Section B": 3, "Section C1": 8, "Section C2": 8,
                   "Section C3": 6, "Section C4": 6, "Section C5": 6, "Section D": 12}
    assert len(items) == 67
    # no within-attempt repetition
    texts = [i["prompt_text"] or i["question"] for i in items if i["task_type"] != "repeat_sentence"]
    assert len(texts) == len(set(texts)), "an item repeated within one sitting"
    # D: four clips, three questions each, clip-level gate on every item of D
    d = [i for i in items if i["task_type"] == "listening_comprehension"]
    assert Counter(i["passage_ref"] for i in d) == Counter({r: 3 for r in {i["passage_ref"] for i in d}})
    assert len({i["passage_ref"] for i in d}) == 4
    assert all(i["ack_gate"] == "clip" and i["continuous_numbering"] for i in d)
    b = [i for i in items if i["task_type"] == "open_response"]
    assert all(i["skip_prep"] and not i["allow_skip"] and not i["fixed_window"] and i["key_points"] == [] for i in b)
    # budgets reach the runner for every section
    assert {i["section_title"].split(" - ")[0]: i["section_budget_seconds"] for i in items} == {
        "Section A1": 600, "Section A2": 600, "Section B": 600, "Section C1": 900, "Section C2": 900,
        "Section C3": 900, "Section C4": 900, "Section C5": 900, "Section D": 600}


async def test_svar_payload_carries_the_same_behaviour_it_had_by_name(client):
    """SVAR is frozen: its runner payload must expose, as flags, exactly what
    the runner used to do for `svar_style` by name."""
    from tests.conftest import auth, login
    token = await login(client, "student")
    await client.post("/api/v1/student/consent", headers=auth(token), json={"scopes": ["recording"]})
    profiles = (await client.get("/api/v1/student/profiles", headers=auth(token))).json()
    svar = next(p for p in profiles if p["code"] == "svar_full_simulation")
    items = (await client.post("/api/v1/student/attempts", headers=auth(token),
                               json={"profile_id": svar["id"], "mode": "practice"})).json()["items"]
    assert len(items) == 67
    assert all(i["continuous_numbering"] for i in items)
    b = [i for i in items if i["task_type"] == "open_response"]
    assert all(i["fixed_window"] and i["allow_skip"] and not i["skip_prep"] and len(i["key_points"]) == 3 for i in b)
    d = [i for i in items if i["task_type"] == "listening_comprehension"]
    assert all(i["ack_gate"] == "section" for i in d)
    others = [i for i in items if i["task_type"] not in ("open_response", "listening_comprehension")]
    assert all(not i["fixed_window"] and not i["allow_skip"] and i["ack_gate"] == "" for i in others)


async def test_unflagged_formats_get_the_engines_original_behaviour(client):
    from tests.conftest import auth, login
    token = await login(client, "student")
    await client.post("/api/v1/student/consent", headers=auth(token), json={"scopes": ["recording"]})
    profiles = (await client.get("/api/v1/student/profiles", headers=auth(token))).json()
    tcs = next(p for p in profiles if p["code"] == "company_round_tcs")
    items = (await client.post("/api/v1/student/attempts", headers=auth(token),
                               json={"profile_id": tcs["id"], "mode": "practice"})).json()["items"]
    assert all(not i["fixed_window"] and not i["allow_skip"] and not i["skip_prep"]
               and i["ack_gate"] == "" and not i["continuous_numbering"]
               and i["section_budget_seconds"] == 0 for i in items)


def test_speechx_keeps_the_platforms_adaptive_window_and_never_inherits_svar_fixed_window():
    """PM decision: the source does not establish a silence rule, so SpeechX
    runs on the engine's adaptive advancement. Every SpeechX section must
    carry fixed_window=False, and the flag must come from SpeechX's own
    blueprint -- not from SVAR's -- so sharing the engine cannot leak SVAR's
    rule across. A = 15 s maximum and B = 30 s think / 60 s speak stay."""
    f = formats.section_behaviour("speechx_style_full")
    assert f and all(v["fixed_window"] is False for v in f.values())
    svar = formats.section_behaviour("svar_full_simulation")
    assert svar["Section B - Speak on the Topic"]["fixed_window"] is True
    b = next(s for s in SX.sections if s.task_type == "open_response")
    assert (b.prep_seconds, b.response_seconds) == (30, 60)
    assert all(s.response_seconds == 15 for s in SX.sections if s.title.startswith("Section A"))


async def test_speechx_runner_payload_has_no_fixed_window_items(client):
    from tests.conftest import auth, login
    token = await login(client, "student")
    await client.post("/api/v1/student/consent", headers=auth(token), json={"scopes": ["recording"]})
    profiles = (await client.get("/api/v1/student/profiles", headers=auth(token))).json()
    sx = next(p for p in profiles if p["code"] == "speechx_style_full")
    items = (await client.post("/api/v1/student/attempts", headers=auth(token),
                               json={"profile_id": sx["id"], "mode": "practice"})).json()["items"]
    assert items and all(i["fixed_window"] is False for i in items)
    assert all(i["response_seconds"] == 60 and i["prep_seconds"] == 30
               for i in items if i["task_type"] == "open_response")

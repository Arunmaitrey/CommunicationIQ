"""End-to-end acceptance of the SVAR-style Communication Assessment (4-section).

Drives a real 67-item attempt through the actual production endpoints — the
same endpoints the runner UI calls — because the browser runner sits behind a
microphone/environment gate this harness cannot pass. This is the sanctioned
mechanism the rest of the suite uses (audio fixtures + the real audio/answer
routes); nothing here is test-only production behaviour.

What is validated at Tier 0 (no speech models installed, this host's state):
the whole lifecycle (start -> answer every item -> submit -> finalise ->
deterministic scoring -> report), and the chosen/typed rounds in full —
voice_change (grammar), fill-in-the-blanks (grammar), comprehension. The
spoken rounds upload real audio and are accepted and stored, but their
acoustic scores need the Tier-1 engine and so report as unscored here, exactly
as every spoken item on a Tier-0 host does. That boundary is stated, not
hidden.
"""
from __future__ import annotations

import pytest
from sqlalchemy import delete, select

from app.db import tenant_sessionmaker
from app.models.tenant import (Attempt, AttemptNarration, QuizItem, Response,
                               ScoreRecord)
from tests.audio_fixtures import FLUENT, to_wav
from tests.conftest import auth, login

pytestmark = pytest.mark.asyncio
SLUG = "stmarys"


async def _svar_profile_id(client, token) -> str:
    profiles = (await client.get("/api/v1/student/profiles",
                                 headers=auth(token))).json()
    return next(p["id"] for p in profiles if p["code"] == "svar_full_simulation")


async def _consent(client, token):
    await client.post("/api/v1/student/consent", headers=auth(token),
                      json={"scopes": ["recording"]})


async def _start(client, token, profile_id):
    return (await client.post("/api/v1/student/attempts", headers=auth(token),
                              json={"profile_id": profile_id,
                                    "mode": "practice"})).json()


async def _quiz_key(response_id: str) -> tuple[str, int, list]:
    """(quiz_item_id, correct_index, accepted-words/options) for a response."""
    async with tenant_sessionmaker(SLUG)() as ts:
        r = await ts.get(Response, response_id)
        q = await ts.get(QuizItem, r.quiz_item_id or "")
        return (q.id, q.correct_index, list(q.options or []))


async def _answer_all(client, token, attempt_id, items, *, wrong_voice=(),
                      skip_voice=()):
    """Answer every item through the real endpoints, by mode.

    wrong_voice / skip_voice: response_ids of voice_change items to answer with
    a distractor / to leave unanswered, for the scoring checks.
    """
    for it in items:
        rid, mode, tt = it["response_id"], it["response_mode"], it["task_type"]
        if mode == "speak":
            if it["prompt_plays_allowed"] > 0:
                await client.post(
                    f"/api/v1/student/attempts/{attempt_id}/responses/{rid}/prompt",
                    headers=auth(token))
            await client.post(
                f"/api/v1/student/attempts/{attempt_id}/responses/{rid}/audio",
                files={"file": ("a.wav", to_wav(FLUENT()), "audio/wav")},
                headers=auth(token))
        elif mode == "select":
            if rid in skip_voice:
                continue
            _, correct, opts = await _quiz_key(rid)
            idx = correct
            if rid in wrong_voice:
                idx = (correct + 1) % max(2, len(opts))
            await client.post(
                f"/api/v1/student/attempts/{attempt_id}/responses/{rid}/answer",
                headers=auth(token), json={"selected_index": idx})
        else:  # write
            _, _, accepted = await _quiz_key(rid)
            await client.post(
                f"/api/v1/student/attempts/{attempt_id}/responses/{rid}/answer",
                headers=auth(token),
                json={"text": accepted[0] if accepted else "the"})


# --------------------------------------------------------------------------
# 1. Full lifecycle
# --------------------------------------------------------------------------

async def test_full_svar_attempt_lifecycle(client):
    token = await login(client, "student")
    await _consent(client, token)
    pid = await _svar_profile_id(client, token)
    payload = await _start(client, token, pid)
    attempt_id = payload["attempt_id"]
    items = payload["items"]

    assert len(items) == 67, f"expected 67 items (18 + 3 + 34 + 12), got {len(items)}"
    # every section is represented
    kinds = {i["task_type"] for i in items}
    assert {"read_aloud", "repeat_sentence", "open_response", "sentence_completion",
            "voice_change", "listening_comprehension"} <= kinds

    await client.post(f"/api/v1/student/attempts/{attempt_id}/env-check",
                      headers=auth(token),
                      json={"mic_ok": True, "playback_ok": True, "headphones": True,
                            "noise_dbfs": -58.0, "input_peak_dbfs": -12.0,
                            "device_label": "Test mic", "user_agent": "pytest"})

    await _answer_all(client, token, attempt_id, items)

    result = (await client.post(f"/api/v1/student/attempts/{attempt_id}/submit",
                                headers=auth(token))).json()

    assert result["status"] == "scored"
    assert len(result["responses"]) == 67, "every item is represented in the report"
    # The chosen/typed rounds score without a speech engine:
    assert "grammar" in result["dimensions"], "voice_change + fill-blanks -> grammar"
    assert "comprehension" in result["dimensions"], "listen & answer -> comprehension"
    # The report was assembled.
    assert result["summary"], "a plain-language summary is generated"
    # Spoken rounds are accepted; their acoustic scores need Tier 1 and are
    # reported as unscored here rather than guessed — documented, not hidden.
    assert isinstance(result.get("unscored"), dict)


# --------------------------------------------------------------------------
# 2. voice_change scoring: correct / distractor / unanswered -> grammar only
# --------------------------------------------------------------------------

async def test_voice_change_scores_correct_distractor_and_unanswered(client):
    token = await login(client, "student")
    await _consent(client, token)
    pid = await _svar_profile_id(client, token)
    payload = await _start(client, token, pid)
    attempt_id = payload["attempt_id"]
    items = payload["items"]

    voice = [i for i in items if i["task_type"] == "voice_change"]
    assert len(voice) == 6, "Section C5 voice change is six questions"
    correct_rid = voice[0]["response_id"]
    wrong_rid = voice[1]["response_id"]
    skip_rid = voice[2]["response_id"]

    # Answer just the three voice_change items we care about.
    _, correct_idx, opts = await _quiz_key(correct_rid)
    await client.post(
        f"/api/v1/student/attempts/{attempt_id}/responses/{correct_rid}/answer",
        headers=auth(token), json={"selected_index": correct_idx})
    _, w_idx, w_opts = await _quiz_key(wrong_rid)
    await client.post(
        f"/api/v1/student/attempts/{attempt_id}/responses/{wrong_rid}/answer",
        headers=auth(token),
        json={"selected_index": (w_idx + 1) % len(w_opts)})
    # skip_rid: left unanswered on purpose.

    async with tenant_sessionmaker(SLUG)() as ts:
        rows = {r.response_id: r for r in (await ts.execute(
            select(ScoreRecord).where(ScoreRecord.attempt_id == attempt_id))
        ).scalars().all()}

    # Correct -> grammar at the top of the scale; wrong -> the bottom.
    assert rows[correct_rid].dimension == "grammar"
    assert rows[correct_rid].score == rows[correct_rid].scale_max
    assert rows[wrong_rid].dimension == "grammar"
    assert rows[wrong_rid].score == rows[wrong_rid].scale_min
    # Unanswered -> no ScoreRecord at all (not a zero, not a guess).
    assert skip_rid not in rows
    # It touched nothing but grammar on these items.
    assert {rows[correct_rid].dimension, rows[wrong_rid].dimension} == {"grammar"}


# --------------------------------------------------------------------------
# 3. Determinism boundary: AI narration never moves a score
# --------------------------------------------------------------------------

async def test_narration_does_not_alter_svar_scores(client, monkeypatch):
    from app.config import settings
    from app.narration import worker

    # The real, grounded echo provider — it references the biggest_lever and
    # uses only supplied numbers, so it clears the same validator every
    # provider must. (A generic stub would be rejected once a real lever
    # exists, which is the validator working, not a scoring defect.)
    monkeypatch.setattr(settings, "narration_enabled", True)
    monkeypatch.setattr(settings, "narration_provider", "echo")

    token = await login(client, "student")
    await _consent(client, token)
    # ai_explanation consent so a job is created
    await client.post("/api/v1/student/consent", headers=auth(token),
                      json={"scopes": ["recording", "ai_explanation"]})
    pid = await _svar_profile_id(client, token)
    payload = await _start(client, token, pid)
    attempt_id = payload["attempt_id"]
    await _answer_all(client, token, attempt_id, payload["items"])
    result = (await client.post(f"/api/v1/student/attempts/{attempt_id}/submit",
                                headers=auth(token))).json()

    async def snapshot():
        async with tenant_sessionmaker(SLUG)() as ts:
            return {(r.dimension, r.response_id): r.score for r in (
                await ts.execute(select(ScoreRecord)
                                 .where(ScoreRecord.attempt_id == attempt_id))
            ).scalars().all()}

    before = await snapshot()
    await worker.tick_tenant(SLUG)   # generate the narration
    after = await snapshot()
    assert before == after, "narration must not change any score"

    async with tenant_sessionmaker(SLUG)() as ts:
        n = (await ts.execute(select(AttemptNarration)
             .where(AttemptNarration.attempt_id == attempt_id))).scalars().first()
    assert n is not None and n.status == "ready"
    # tidy
    async with tenant_sessionmaker(SLUG)() as ts:
        await ts.execute(delete(AttemptNarration)
                         .where(AttemptNarration.attempt_id == attempt_id))
        await ts.commit()


# --------------------------------------------------------------------------
# 4. Section B — Speak on a Topic actually receives its topic
#
# The topic is the prompt: you speak *about* it, so it must be visible. The bug
# this guards against is the runner receiving an open_response item with an
# empty prompt while a real topic exists in the item bank -- which made the
# whole section impossible to perform.
# --------------------------------------------------------------------------

async def test_open_response_topic_reaches_the_runner(client):
    token = await login(client, "student")
    await _consent(client, token)
    pid = await _svar_profile_id(client, token)
    payload = await _start(client, token, pid)
    items = payload["items"]

    topics = [i for i in items if i["task_type"] == "open_response"]
    assert len(topics) == 3, "Section B is three topics"

    for it in topics:
        # The regression: a topic exists in the bank, so it must not arrive
        # empty. (The item was seeded with prompt_text; withholding it here is
        # exactly the defect.)
        assert it["prompt_text"].strip(), \
            "Speak-on-Topic reached the runner with no topic"
        # And it must not claim an audio prompt it does not have, nor offer a
        # play: the topic is read, not heard.
        assert it["has_prompt_audio"] is False
        assert it["prompt_plays_allowed"] == 0

    # Three distinct topics, not the same one three times.
    assert len({it["prompt_text"].strip() for it in topics}) == 3

    # The withholding rule still holds for the tasks that depend on it: a
    # Repeat Sentence prompt is heard, never shown, and must stay empty.
    for it in items:
        if it["task_type"] == "repeat_sentence":
            assert it["prompt_text"] == "", \
                "Repeat Sentence prompt must stay withheld"


# --------------------------------------------------------------------------
# 5. Section D — one listening event per passage (4 passages x 3 questions)
#
# The comprehension section is four clips, three questions each. The audio is
# heard once per clip, not once per question: the runner plays the first item
# of each passage group and never replays for the other two. The measurable
# invariant is "12 questions, 4 plays".
# --------------------------------------------------------------------------

def _passage_playbacks(listening_items) -> set[str]:
    """Mirror the runner's rule: the first item per passage_ref owns playback.

    Returns the response_ids that would trigger a play. Its size is the number
    of times the audio is heard -- the invariant under test.
    """
    seen: set[str] = set()
    owners: set[str] = set()
    for it in listening_items:
        ref = it["passage_ref"]
        if ref and ref not in seen:
            seen.add(ref)
            owners.add(it["response_id"])
    return owners


async def test_listening_is_four_passages_of_three_and_plays_four_times(client):
    token = await login(client, "student")
    await _consent(client, token)
    pid = await _svar_profile_id(client, token)
    payload = await _start(client, token, pid)
    attempt_id = payload["attempt_id"]
    items = payload["items"]

    dee = [i for i in items if i["task_type"] == "listening_comprehension"]
    assert len(dee) == 12, "Section D is twelve questions"

    # (1) Every question carries a passage ref, grouping into 4 passages x 3.
    assert all(i["passage_ref"] for i in dee), "each question names its passage"
    groups: dict[str, list] = {}
    for i in dee:
        groups.setdefault(i["passage_ref"], []).append(i)
    assert len(groups) == 4, f"expected 4 passages, got {len(groups)}"
    assert all(len(q) == 3 for q in groups.values()), "3 questions per passage"

    # A passage's three questions are consecutive in the sitting -- you hear
    # the clip, then answer its questions, before the next clip.
    order = [i["passage_ref"] for i in dee]
    runs = [ref for n, ref in enumerate(order) if n == 0 or order[n - 1] != ref]
    assert len(runs) == 4, "each passage's questions are contiguous, not interleaved"

    # (2) Playback count = 4, not 12. The runner plays once per passage.
    plays = _passage_playbacks(dee)
    assert len(plays) == 4, f"audio should be heard 4 times, not {len(plays)}"
    # The owners are exactly the first question of each passage.
    firsts = {q[0]["response_id"] for q in groups.values()}
    assert plays == firsts

    # (3) Attempting to replay a clip is refused by the server itself -- a
    # backstop under the runner's rule, so a second play cannot leak in.
    owner_rid = next(iter(plays))
    first = await client.post(
        f"/api/v1/student/attempts/{attempt_id}/responses/{owner_rid}/prompt",
        headers=auth(token))
    assert first.status_code == 200
    again = await client.post(
        f"/api/v1/student/attempts/{attempt_id}/responses/{owner_rid}/prompt",
        headers=auth(token))
    assert again.status_code == 409, "a clip cannot be played a second time"


async def test_all_twelve_listening_answers_persist_and_score(client):
    token = await login(client, "student")
    await _consent(client, token)
    pid = await _svar_profile_id(client, token)
    payload = await _start(client, token, pid)
    attempt_id = payload["attempt_id"]
    items = payload["items"]

    dee = [i for i in items if i["task_type"] == "listening_comprehension"]
    assert len(dee) == 12

    # (4) Answer all twelve correctly. None is skipped by the grouping.
    for it in dee:
        _, correct, _ = await _quiz_key(it["response_id"])
        r = await client.post(
            f"/api/v1/student/attempts/{attempt_id}/responses/{it['response_id']}/answer",
            headers=auth(token), json={"selected_index": correct})
        assert r.status_code in (200, 201), "every listening answer is accepted"

    # (5) All twelve persist as comprehension scores, and correct answers score
    # at the top of the scale -- the grouping is a playback concern only and
    # changes nothing about how a stored answer is marked.
    async with tenant_sessionmaker(SLUG)() as ts:
        rows = [r for r in (await ts.execute(
            select(ScoreRecord).where(ScoreRecord.attempt_id == attempt_id))
        ).scalars().all() if r.dimension == "comprehension"]
    scored = {r.response_id: r for r in rows}
    assert len(scored) == 12, f"12 comprehension scores persisted, got {len(scored)}"
    for it in dee:
        rec = scored[it["response_id"]]
        assert rec.score == rec.scale_max, "a correct answer scores full comprehension"

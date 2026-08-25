"""A candidate who reloads must not lose their assessment.

The bug this file exists for, found by sitting the invitation journey in a
browser:

A candidate opens their link, gives their name, and reaches the consent
screen. They refresh -- because the page was slow, because their phone locked,
because they closed the tab and clicked the link again. The link is
single-use, so the preview now reports it as used, and the page showed them
"This invitation has already been used. If that was not you, tell whoever
invited you, because somebody else has your link."

They had used it, ninety seconds earlier. The screen had no button and no
link on it. They still held a valid candidate session, and every other route
in the product refuses a candidate by role -- `/student/home`,
`/student/attempts`, all of it -- so there was genuinely nowhere to go.

In a one-shot assessment that is the entire thing lost, to a refresh.

The state that went missing was React state. The fix is that the server can
answer "where was I", from the invitation that names the candidate.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db import tenant_sessionmaker
from app.models.tenant import Invitation
from tests.test_game_and_practice import SLUG, auth, login

pytestmark = pytest.mark.asyncio


async def _published_profile(client, admin, name: str) -> str:
    created = (await client.post(
        "/api/v1/tenant/profiles", headers=auth(admin),
        json={"name": name, "style": "company_round", "company": "Testco",
              "description": "x", "estimated_minutes": 6,
              "sections": [{"title": "Read Aloud", "task_type": "read_aloud",
                            "item_count": 1, "prep_seconds": 0,
                            "response_seconds": 20,
                            "prompt_plays_allowed": 0,
                            "allow_replay": False}]})).json()
    await client.post(f"/api/v1/tenant/profiles/{created['id']}/status",
                      headers=auth(admin), json={"status": "published"})
    return created["id"]


async def _invited_candidate(client, name="Resume Candidate"):
    """An invitation, claimed. Returns (candidate token, profile id, token)."""
    admin = await login(client, "tenant_admin")
    profile_id = await _published_profile(client, admin, f"Resume - {name}")

    invitation = (await client.post(
        "/api/v1/tenant/invitations", headers=auth(admin),
        json={"profile_id": profile_id, "invited_name": name,
              "invited_email": "", "reference": "", "valid_days": 7})).json()

    claimed = (await client.post(
        f"/api/v1/invite/{invitation['token']}/claim",
        json={"full_name": name, "email": ""})).json()

    return claimed["token"], profile_id, invitation["token"]


async def test_a_candidate_who_reloads_can_still_find_their_assessment(client):
    """The whole bug, at the layer it belongs to.

    Before this endpoint existed, a candidate in exactly this position -- link
    spent, session valid, nothing started -- had no request they were allowed
    to make that would tell them what they had been invited to.
    """
    token, profile_id, _ = await _invited_candidate(client)

    resumed = await client.get("/api/v1/student/attempts/resume",
                               headers=auth(token))
    assert resumed.status_code == 200, resumed.text
    body = resumed.json()

    assert body["profile_id"] == profile_id, (
        "the candidate cannot be told which assessment is theirs")
    assert body["profile_name"]
    assert body["attempt_id"] is None, "nothing has been started yet"


async def test_the_spent_link_still_refuses_everybody_else(client):
    """Resuming must not turn a single-use link into a reusable one.

    The link is the thing that is spent. The *session* is what survives, and
    only in the browser that spent it.
    """
    _, _, link_token = await _invited_candidate(client, "Second Reader")

    preview = (await client.get(f"/api/v1/invite/{link_token}")).json()
    assert preview["ok"] is False
    assert preview["reason"] == "used"

    again = await client.post(f"/api/v1/invite/{link_token}/claim",
                              json={"full_name": "Somebody Else", "email": ""})
    assert again.status_code == 409, (
        "a spent link minted a second session -- two people would be sitting "
        "one invitation")


async def test_resume_sends_a_candidate_back_to_an_attempt_in_progress(client):
    """Refreshing after starting is the same fault one step later."""
    token, profile_id, _ = await _invited_candidate(client, "Mid Attempt")

    await client.post("/api/v1/student/consent", headers=auth(token),
                      json={"scopes": ["recording"]})
    started = (await client.post(
        "/api/v1/student/attempts", headers=auth(token),
        json={"profile_id": profile_id, "mode": "official"})).json()

    body = (await client.get("/api/v1/student/attempts/resume",
                             headers=auth(token))).json()

    assert body["attempt_id"] == started["attempt_id"], (
        "a candidate mid-assessment was not pointed back at it")
    assert body["consent_given"] is True


async def test_resume_reports_consent_so_nobody_is_asked_twice(client):
    token, _, _ = await _invited_candidate(client, "Not Yet Consented")

    before = (await client.get("/api/v1/student/attempts/resume",
                               headers=auth(token))).json()
    assert before["consent_given"] is False

    await client.post("/api/v1/student/consent", headers=auth(token),
                      json={"scopes": ["recording"]})

    after = (await client.get("/api/v1/student/attempts/resume",
                              headers=auth(token))).json()
    assert after["consent_given"] is True, (
        "consent was recorded and the resume path could not see it")


async def test_one_candidate_cannot_resume_into_another_persons_assessment(client):
    """The obvious way to get this wrong.

    `resume` answers from the invitation that names the caller. If it answered
    from anything looser -- the most recent invitation, say -- one candidate
    would be handed another's assessment.
    """
    first_token, first_profile, _ = await _invited_candidate(client, "Candidate A")
    second_token, second_profile, _ = await _invited_candidate(client, "Candidate B")

    assert first_profile != second_profile

    a = (await client.get("/api/v1/student/attempts/resume",
                          headers=auth(first_token))).json()
    b = (await client.get("/api/v1/student/attempts/resume",
                          headers=auth(second_token))).json()

    assert a["profile_id"] == first_profile
    assert b["profile_id"] == second_profile


async def test_an_enrolled_student_gets_an_empty_answer_not_an_error(client):
    """A student has a home page and never needs this. Asking is not a fault,
    and 404ing would make the client handle an error for a normal case."""
    student = await login(client, "student")

    res = await client.get("/api/v1/student/attempts/resume",
                           headers=auth(student))
    assert res.status_code == 200, res.text
    assert res.json()["profile_id"] == ""


async def test_resume_is_not_read_as_an_attempt_id(client):
    """`/resume` sits under the same prefix as `/{attempt_id}/runner`.

    Declared first so the literal wins. If a later edit moves it below a bare
    `/{attempt_id}` route, this is what says so.
    """
    token, _, _ = await _invited_candidate(client, "Route Order")

    res = await client.get("/api/v1/student/attempts/resume",
                           headers=auth(token))
    assert res.status_code == 200
    assert "profile_id" in res.json(), (
        "something other than the resume endpoint answered this path")


async def test_a_candidate_still_cannot_reach_the_student_surfaces(client):
    """The fix widens one endpoint and must not widen the role.

    A candidate came to sit one assessment. Practice, drills, progress and the
    student home stay closed -- and the reason the dead end was total is that
    they *are* closed, so the resume path is the only way out and must not
    have brought friends.
    """
    token, _, _ = await _invited_candidate(client, "Still Fenced")

    for path in ("/api/v1/student/home", "/api/v1/student/attempts",
                 "/api/v1/student/skills", "/api/v1/student/practice/next"):
        res = await client.get(path, headers=auth(token))
        assert res.status_code in (403, 404, 405), (
            f"a candidate reached {path} with {res.status_code}")


async def test_the_invitation_records_who_claimed_it(client):
    """`resume` answers from `candidate_id`, so that link is load-bearing."""
    token, profile_id, link_token = await _invited_candidate(client, "Linked")

    async with tenant_sessionmaker(SLUG)() as session:
        row = (await session.execute(
            select(Invitation).where(Invitation.token == link_token)
        )).scalars().first()

    assert row is not None
    assert row.status == "redeemed"
    assert row.candidate_id, (
        "the invitation does not name the candidate it admitted, so nothing "
        "can answer 'which assessment is mine'")


async def test_resume_carries_what_the_consent_screen_has_to_say(client):
    """No invented values on the screen before somebody agrees to be recorded.

    The first version of the resume path let the page synthesise a preview to
    render, and it rendered "About 0 minutes, in one sitting" with no
    institution named. A candidate deciding whether to be recorded was being
    shown a fabricated duration by an unnamed organisation.
    """
    token, _, _ = await _invited_candidate(client, "Consent Screen")

    body = (await client.get("/api/v1/student/attempts/resume",
                             headers=auth(token))).json()

    assert body["estimated_minutes"] > 0, (
        "the resumed consent screen would say 'about 0 minutes'")
    assert body["tenant_name"], (
        "the resumed consent screen would not name who is assessing them")
    assert body["profile_name"]


async def test_a_candidate_gets_one_sitting_not_as_many_as_they_like(client):
    """An invitation buys one assessment.

    A student may attempt a simulation as often as they want -- that is what
    practice is. An invited candidate is a different arrangement: an employer
    sent one link, once, and the result is a hiring decision.

    Nothing enforced it. The link was correctly single-use, and the session it
    minted could start a fresh attempt at the same profile as often as the
    candidate liked, so anybody unhappy with their score could sit it again
    until they were happy. Found by doing exactly that in a browser.
    """
    token, profile_id, _ = await _invited_candidate(client, "One Sitting")

    await client.post("/api/v1/student/consent", headers=auth(token),
                      json={"scopes": ["recording"]})

    first = await client.post("/api/v1/student/attempts", headers=auth(token),
                              json={"profile_id": profile_id, "mode": "official"})
    assert first.status_code == 201, first.text

    second = await client.post("/api/v1/student/attempts", headers=auth(token),
                               json={"profile_id": profile_id, "mode": "official"})
    assert second.status_code == 409, (
        f"a candidate started a second attempt at the same assessment "
        f"({second.status_code}) -- the invitation is not one-shot")
    assert "one sitting" in second.text

    # Practice mode is not a way around it either.
    practice = await client.post("/api/v1/student/attempts", headers=auth(token),
                                 json={"profile_id": profile_id, "mode": "practice"})
    assert practice.status_code == 409, (
        "practice mode let a candidate re-sit a hiring assessment")


async def test_a_student_may_still_attempt_a_simulation_repeatedly(client):
    """The rule is about candidates, and must not have caught students.

    Repeated attempts are the entire point of practice, and a limit applied to
    everybody would be a far worse bug than the one being fixed.
    """
    admin = await login(client, "tenant_admin")
    profile_id = await _published_profile(client, admin, "Student repeats")

    student = await login(client, "student")
    await client.post("/api/v1/student/consent", headers=auth(student),
                      json={"scopes": ["recording"]})

    first = await client.post("/api/v1/student/attempts", headers=auth(student),
                              json={"profile_id": profile_id, "mode": "practice"})
    second = await client.post("/api/v1/student/attempts", headers=auth(student),
                               json={"profile_id": profile_id, "mode": "practice"})

    assert first.status_code == 201
    assert second.status_code == 201, (
        "a student was blocked from practising twice")


async def test_the_invitation_records_the_attempt_it_produced(client):
    """`Invitation.attempt_id` is described in the model as "the attempt that
    followed" and was written by nothing.

    An operator asking which sitting a link produced had to infer it from the
    candidate id and a timestamp.
    """
    token, profile_id, link_token = await _invited_candidate(client, "Linked Attempt")

    await client.post("/api/v1/student/consent", headers=auth(token),
                      json={"scopes": ["recording"]})
    started = (await client.post(
        "/api/v1/student/attempts", headers=auth(token),
        json={"profile_id": profile_id, "mode": "official"})).json()

    async with tenant_sessionmaker(SLUG)() as session:
        row = (await session.execute(
            select(Invitation).where(Invitation.token == link_token)
        )).scalars().first()

    assert row.attempt_id == started["attempt_id"], (
        "the invitation does not name the attempt it produced")


async def test_the_institution_can_read_the_result_it_commissioned(client):
    """The last step of the external-hiring flow, which did not exist.

    An institution could build an assessment, send a link, and watch the
    invitation turn "redeemed" -- and then had no way to see what the
    candidate scored. The candidate's own report is scoped to the person who
    sat it; every trainer route is cohort-scoped, and a candidate is in no
    cohort. There was no route at all, so the feature stopped one step short
    of the reason anybody would buy it.
    """
    admin = await login(client, "tenant_admin")
    profile_id = await _published_profile(client, admin, "Commissioned round")

    invitation = (await client.post(
        "/api/v1/tenant/invitations", headers=auth(admin),
        json={"profile_id": profile_id, "invited_name": "Read My Result",
              "invited_email": "", "reference": "REQ-1", "valid_days": 7})).json()

    # Before anybody sits it, the honest answer is that there is no result.
    early = await client.get(
        f"/api/v1/tenant/invitations/{invitation['id']}/result",
        headers=auth(admin))
    assert early.status_code == 409
    assert "nobody has sat" in early.text.lower()

    claimed = (await client.post(
        f"/api/v1/invite/{invitation['token']}/claim",
        json={"full_name": "Read My Result", "email": ""})).json()
    token = claimed["token"]

    await client.post("/api/v1/student/consent", headers=auth(token),
                      json={"scopes": ["recording"]})
    started = (await client.post(
        "/api/v1/student/attempts", headers=auth(token),
        json={"profile_id": profile_id, "mode": "official"})).json()
    await client.post(f"/api/v1/student/attempts/{started['attempt_id']}/submit",
                      headers=auth(token), json={})

    res = await client.get(
        f"/api/v1/tenant/invitations/{invitation['id']}/result",
        headers=auth(admin))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["attempt_id"] == started["attempt_id"], (
        "the institution was shown a different sitting")
    assert body["profile_name"]


async def test_the_employer_report_keeps_the_same_caveats_as_the_candidates(client):
    """One set of numbers, one set of warnings.

    An employer-facing report with the hedging stripped out would be a
    different claim about the same measurements.
    """
    admin = await login(client, "tenant_admin")
    profile_id = await _published_profile(client, admin, "Caveat round")
    invitation = (await client.post(
        "/api/v1/tenant/invitations", headers=auth(admin),
        json={"profile_id": profile_id, "invited_name": "Caveats",
              "invited_email": "", "reference": "", "valid_days": 7})).json()
    claimed = (await client.post(f"/api/v1/invite/{invitation['token']}/claim",
                                 json={"full_name": "Caveats", "email": ""})).json()
    await client.post("/api/v1/student/consent", headers=auth(claimed["token"]),
                      json={"scopes": ["recording"]})
    started = (await client.post(
        "/api/v1/student/attempts", headers=auth(claimed["token"]),
        json={"profile_id": profile_id, "mode": "official"})).json()
    await client.post(f"/api/v1/student/attempts/{started['attempt_id']}/submit",
                      headers=auth(claimed["token"]), json={})

    employer = (await client.get(
        f"/api/v1/tenant/invitations/{invitation['id']}/result",
        headers=auth(admin))).json()
    candidate = (await client.get(
        f"/api/v1/student/attempts/{started['attempt_id']}/result",
        headers=auth(claimed["token"]))).json()

    assert employer["calibrated"] == candidate["calibrated"]
    assert employer["calibration_note"] == candidate["calibration_note"]
    assert employer["unscored"] == candidate["unscored"]
    assert employer["overall"] == candidate["overall"]


async def test_another_institution_cannot_read_this_invitation(client):
    """Isolation is structural here -- the query runs in the schema the
    caller's token names -- but the claim is worth stating where a new
    cross-tenant route is added."""
    admin = await login(client, "tenant_admin")
    profile_id = await _published_profile(client, admin, "Not yours")
    invitation = (await client.post(
        "/api/v1/tenant/invitations", headers=auth(admin),
        json={"profile_id": profile_id, "invited_name": "Private",
              "invited_email": "", "reference": "", "valid_days": 7})).json()

    other = await login(client, "other_admin")
    res = await client.get(
        f"/api/v1/tenant/invitations/{invitation['id']}/result",
        headers=auth(other))
    assert res.status_code == 404, (
        f"another institution reached this invitation ({res.status_code})")


async def test_a_candidate_cannot_read_the_admin_view_of_their_own_result(client):
    """The route is tenant-admin only. A candidate has their own report and
    must not reach an institution-scoped endpoint to get it."""
    token, _, _ = await _invited_candidate(client, "No Admin Route")

    res = await client.get("/api/v1/tenant/invitations", headers=auth(token))
    assert res.status_code in (403, 404)

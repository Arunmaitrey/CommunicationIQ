"""The recovery path, proven across both halves of the product.

    record before the deadline -> bell -> upload fails -> reload ->
    IndexedDB restores the audio -> retry -> upload succeeds -> submit ->
    the answer is still there and it scored

No part of this is stubbed. The audio is a real WAV, the upload is a real
HTTP request to a real server, the queue is a real IndexedDB, and the score
at the end comes from the real pipeline.

**Why it takes two processes.** The chain has three links and no single
runtime owns all of them. IndexedDB exists only in the JavaScript half;
`Attempt.started_at` and the scoring pipeline exist only in the Python half.
Testing either side alone leaves the seam between them untested, and the seam
is where an answer goes missing -- a client that keeps audio perfectly is
worthless against a server that refuses it, and a server that would accept it
is worthless if the client threw it away.

So: pytest builds the situation, hands it to vitest through the environment,
and checks the consequences afterwards.

Skipped, loudly, when Node or the frontend dependencies are absent. It is
marked ``e2e`` so it can be excluded from a quick run --
``pytest -m "not e2e"``.
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

from app.db import tenant_sessionmaker
from app.models.tenant import Attempt, Response, ScoreRecord

from tests.test_game_and_practice import SLUG, auth, login

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
pytestmark = pytest.mark.e2e


# The client half needs a socket to post to.
#
# The pytest fixture is an in-process ASGI client with no socket, so a separate
# Node process cannot reach it. The first version of this test therefore
# required a dev server to be running by hand and skipped when it was not --
# which meant the one test proving answers are not lost would sit out every
# unattended run. A test that skips in the only environment nobody watches is
# barely a test.
#
# So it starts its own. A real uvicorn on an ephemeral port, against the same
# database and the same JWT secret, torn down afterwards whatever happens.
# ``E2E_API_URL`` still overrides it for anyone who would rather point at a
# server they already have.


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _healthy(base: str, timeout: float) -> bool:
    import urllib.error
    import urllib.request

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{base}/healthz", timeout=2) as res:
                if res.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            time.sleep(0.5)
    return False


@contextmanager
def _api_for_the_client_half():
    """A server the Node process can actually reach, for as long as it needs.

    Yields a base URL. Borrowed if one is already running -- a developer with
    a dev server up should not pay thirty seconds of start-up per run -- and
    started fresh otherwise.
    """
    borrowed = os.environ.get("E2E_API_URL")
    if borrowed:
        if not _healthy(borrowed, timeout=5):
            pytest.fail(f"E2E_API_URL={borrowed} is set and not answering")
        yield borrowed
        return

    existing = "http://127.0.0.1:8010"
    if _healthy(existing, timeout=1):
        yield existing
        return

    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        if not _healthy(base, timeout=90):
            process.terminate()
            out = ""
            try:
                out = process.communicate(timeout=10)[0] or ""
            except subprocess.TimeoutExpired:
                process.kill()
            pytest.fail("the API this test starts never became healthy:"
                        + chr(10) + out[-2000:])
        yield base
    finally:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()


def _can_run() -> str:
    if shutil.which("npx") is None:
        return "npx is not on PATH"
    if not (FRONTEND / "node_modules" / "vitest").exists():
        return "frontend dependencies are not installed"
    return ""


async def test_a_recording_made_in_time_survives_everything(client, tmp_path):
    """The whole sequence, once, with nothing faked."""
    reason = _can_run()
    if reason:
        # Node genuinely may not be installed on a machine doing backend work,
        # and failing there teaches nobody anything. Everywhere it matters --
        # CI -- ``E2E_REQUIRED=1`` turns the same condition into a failure, so
        # this cannot quietly sit out the only run nobody is watching.
        if os.environ.get("E2E_REQUIRED") == "1":
            pytest.fail(f"E2E_REQUIRED is set and the client half cannot run: "
                        f"{reason}")
        pytest.skip(f"cannot drive the client half: {reason}")

    # -- a round with one spoken item ------------------------------------
    admin = await login(client, "tenant_admin")
    created = (await client.post(
        "/api/v1/tenant/profiles", headers=auth(admin),
        json={"name": "Recovery E2E", "style": "company_round",
              "company": "Testco", "description": "x", "estimated_minutes": 10,
              "sections": [{"title": "Read Aloud", "task_type": "read_aloud",
                            "item_count": 1, "prep_seconds": 0,
                            "response_seconds": 20, "prompt_plays_allowed": 0,
                            "allow_replay": False},
                           # A typed item as well, because the probe below
                           # needs something that is actually answered by
                           # typing. It used to probe the spoken item, where
                           # the refusal it asserted came from the response
                           # mode rather than from the clock -- the assertion
                           # passed, and would have kept passing if the
                           # deadline stopped working entirely.
                           {"title": "Reading",
                            "task_type": "reading_comprehension",
                            # A whole passage's worth. Reading questions come
                            # grouped, so asking for two gets nothing.
                            "item_count": 3, "prep_seconds": 0,
                            "response_seconds": 0, "prompt_plays_allowed": 0,
                            "allow_replay": False}]})).json()
    published = await client.post(
        f"/api/v1/tenant/profiles/{created['id']}/status",
        headers=auth(admin), json={"status": "published"})
    assert published.status_code == 200, published.text

    student_token = await login(client, "student")
    payload = (await client.post(
        "/api/v1/student/attempts", headers=auth(student_token),
        json={"profile_id": created["id"], "mode": "practice"})).json()
    attempt_id = payload["attempt_id"]
    spoken = [i for i in payload["items"] if i["response_mode"] == "speak"]
    typed = [i for i in payload["items"] if i["response_mode"] != "speak"]
    assert spoken and len(typed) >= 2, (
        f"need one spoken item and two typed ones, got {payload['items']}")
    response_id = spoken[0]["response_id"]

    started = await client.post(
        f"/api/v1/student/attempts/{attempt_id}/env-check",
        headers=auth(student_token),
        json={"mic_ok": True, "playback_ok": True, "headphones": True,
              "noise_dbfs": -60.0, "input_peak_dbfs": -20.0,
              "device_label": "e2e", "user_agent": "e2e"})
    assert started.status_code == 200, started.text

    # -- the bell ---------------------------------------------------------
    #
    # Wound forward rather than waited out. The candidate recorded while there
    # was still time; everything that follows is a late *delivery* of audio
    # that already existed, which is the case the upload path must never
    # refuse.
    async with tenant_sessionmaker(SLUG)() as session:
        attempt = (await session.execute(
            select(Attempt).where(Attempt.id == attempt_id))).scalars().first()
        attempt.started_at = datetime.now(timezone.utc) - timedelta(minutes=17)
        await session.commit()

    # A *fresh* answer at this moment is refused, which is what makes the
    # recovery window a deliberate exception rather than an oversight.
    assert not await _answer_would_be_accepted(
        client, student_token, attempt_id, typed[0]["response_id"])

    # A typed answer given before the bell and delivered now is taken, which
    # is the other half of the same rule -- and the half a typed answer went
    # without for six phases, during which a failed POST made the runner
    # record the candidate as not having answered at all.
    assert await _answer_would_be_accepted(
        client, student_token, attempt_id, typed[1]["response_id"],
        composed_at=datetime.now(timezone.utc) - timedelta(minutes=5))

    # -- hand the client half a real attempt ------------------------------
    with _api_for_the_client_half() as api_base:
        env = {
            **os.environ,
            "E2E_API": f"{api_base}/api/v1",
            "E2E_TOKEN": student_token,
            "E2E_ATTEMPT": attempt_id,
            "E2E_RESPONSE": response_id,
            # A cache of its own, so a developer's own IndexedDB state cannot
            # make this pass or fail.
            "TMPDIR": str(tmp_path),
        }
        result = subprocess.run(
            ["npx", "vitest", "run", "lib/e2e.recovery.test.ts"],
            cwd=FRONTEND, env=env, capture_output=True, text=True, timeout=300,
            shell=os.name == "nt",
        )
    assert result.returncode == 0, (
        "the client half failed:\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}")
    # Demand positive proof that the client half ran.
    #
    # The first version checked `"skipped" not in stdout`, which is true of
    # output that never mentions skipping -- including a run where zero tests
    # executed. A green test proving nothing is the exact failure mode that
    # made this whole file necessary.
    assert "1 passed" in result.stdout, (
        f"the client half did not actually run:" + chr(10) + result.stdout)

    # -- the audio is on the server, after the bell -----------------------
    async with tenant_sessionmaker(SLUG)() as session:
        from app.models.tenant import ResponseAudio

        audio = (await session.execute(
            select(ResponseAudio).where(
                ResponseAudio.response_id == response_id))).scalars().first()
    assert audio is not None, (
        "the recording never reached the server -- the recovery path lost it")
    assert audio.bytes > 1000
    assert audio.duration_ms > 1000

    # -- submit, and the answer is still an answer ------------------------
    submitted = await client.post(
        f"/api/v1/student/attempts/{attempt_id}/submit",
        headers=auth(student_token), json={})
    assert submitted.status_code == 200, submitted.text
    body = submitted.json()

    async with tenant_sessionmaker(SLUG)() as session:
        row = (await session.execute(
            select(Response).where(Response.id == response_id))).scalars().first()
        scores = (await session.execute(
            select(ScoreRecord).where(
                ScoreRecord.response_id == response_id))).scalars().all()

    assert not row.skipped, (
        "the recovered answer was recorded as a skip -- which is the false "
        "statement this whole phase exists to prevent")
    assert scores, (
        "the recovered answer reached the server and was never scored")
    assert body["responses"], "the result carries no responses"


async def _answer_would_be_accepted(client, token, attempt_id, response_id,
                                    composed_at=None) -> bool:
    """Whether a typed answer is still taken at this moment.

    Asserted as part of the scenario rather than assumed. Without
    ``composed_at`` this is somebody answering after the bell and must be
    refused; with a stamp from before it, this is a queued answer whose
    delivery is late and must be taken. A change that collapsed the two --
    in either direction -- would either extend the sitting or resume losing
    answers, and this is where that shows up.
    """
    body = {"selected_index": 0}
    if composed_at is not None:
        body["composed_at"] = composed_at.isoformat()
    probe = await client.post(
        f"/api/v1/student/attempts/{attempt_id}/responses/{response_id}/answer",
        headers=auth(token), json=body)
    return probe.status_code == 201

"""The attempt: create, check the room, answer, submit, score.

Three rules are enforced here rather than in the browser, because the browser
is the one part of this we do not control:

* **Consent first.** No recording is accepted from a student who has not
  granted it (STU-02). The check is on the ingest endpoint, not the UI.
* **One shot.** A prompt is counted when it is served. Asking twice past the
  allowance is refused (SIM-02) — reloading the page does not buy a replay.
* **The student owns the attempt.** Every route resolves the attempt through
  the caller's own id, so there is no attempt anyone else can address.
"""
from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone

from fastapi import (APIRouter, BackgroundTasks, Depends, File, Form, HTTPException,
                     Request, Response as HttpResponse, UploadFile, status)
from app.config import settings
from app.invitations import CANDIDATE_ROLE
from app.db import ensure_platform_models, ensure_tenant_models, func, select, Session
from app import formats
from app.deps import Principal, PlatformSession, TenantSession, require_roles
from app.engine.audio import AudioDecodeError, decode_wav, signal_quality
from app import deadline as app_deadline
from app import reconstruction as app_reconstruction
from app import sections as app_sections
from app import selection as app_selection
from app import spoken_content
from app import tts
from app import weighting
from app.evaluation import DIMENSIONS_BY_TASK
from app.engine.pipeline import (NO_TRANSCRIPT, SCALE_MAX, SCALE_MIN,
                                 UNSCORED, AttemptScorer, band_label,
                                 finalise_attempt, pending_responses,
                                 score_response)
from app.engine.psychometrics import irt
from app.engine.registry import Providers
from app.gamification import engine as game
from app.models.tenant import (Attempt, ConsentRecord, ExamReview, FeatureRecord,
                                Invitation, ProfileSection, Response,
                                ResponseAudio, ScoreRecord, SimulationProfile,
                                TaskItem)
from app.schemas import (AnswerSubmission, AttemptResult, CandidateResume,
                         NarrationOut, PromptResponse, ResponseMetrics,
                         ReviewRequest, ReviewOut, RunnerItem, RunnerPayload,
                         StartAttemptRequest, WordTimingOut)
from app.storage import get_storage, recording_key


def _client_ip(request: Request) -> str:
    """Extract client IP from request, respecting X-Forwarded-For behind proxies."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""

# Students and invited candidates, and nobody else.
#
# A candidate is admitted here because this is the only thing they came to do
# -- sit one assessment -- and every other student surface (`/student/home`,
# `/student/profiles`, practice, drills, progress) still names `student`
# alone, so the widening is to this router and no further.
#
# What stops a candidate reaching somebody else's attempt is not this guard
# but `_own_attempt`, which has always compared `attempt.user_id` against the
# caller and 404s otherwise. The role check decides which doors exist; that
# check decides whose rooms are behind them.
router = APIRouter(prefix="/student/attempts", tags=["attempt"],
                   dependencies=[Depends(require_roles("student", "candidate"))])

# Task types whose text the student is meant to read. Everything else is
# heard, and its text must not reach the client before the prompt is served.
# Tasks whose prompt is shown on screen. Read Aloud and Sentence Build are
# read off the display, and Speak on a Topic is spoken *about* -- the topic
# has to be visible or the candidate cannot perform the task at all. It is not
# withheld the way Repeat Sentence / Dictation are, where hearing (not seeing)
# the sentence is the whole measurement.
VISIBLE_PROMPT_TASKS = {"read_aloud", "sentence_build", "open_response", "short_answer"}

# Which field carries the words to be spoken aloud. For Repeat Sentence and
# Story Retell the reference *is* the prompt — the sentence to repeat, the
# story to retell. For everything else the reference is the expected answer,
# and reading it out would hand the student the mark.
# Moved to app.sections, where the rest of the per-task-type knowledge
# lives. Kept as an alias so nothing importing it breaks.
SPEAK_THE_REFERENCE = app_sections.SPEAKS_REFERENCE

MAX_UPLOAD_BYTES = 25 * 1024 * 1024

# How long submit waits for the last answers to finish before handing back a
# "still scoring" result for the page to poll. Sized for one long response on
# a local model, not for a whole batch — everything earlier was scored while
# the student was still talking.
SUBMIT_WAIT_SECONDS = 12.0

log = logging.getLogger(__name__)


async def _score_in_background(slug: str, tenant_id: str | None,
                               response_id: str) -> None:
    """Transcribe and score one answer while the student moves to the next.

    Opens its own sessions: the request that triggered it has already been
    answered, and its session closed with it.
    """
    try:
        models = await ensure_tenant_models(slug)
        session = Session(models)
        platform_models = await ensure_platform_models()
        platform_session = Session(platform_models)
        providers = Providers(platform_session)
        await score_response(session, providers, tenant_id, response_id)
    except Exception as exc:  # noqa: BLE001
        # Recoverable: submit retries anything still pending, and
        # score_response is idempotent so the retry is safe.
        log.warning("background scoring failed for response %s: %s", response_id, exc)


async def _recording_still_welcome(session: TenantSession,
                                   attempt: Attempt) -> None:
    """Whether audio for an item may still arrive.

    Looser than the answer rule on purpose. The audio existed before the bell;
    the request carrying it may be a retry after a dropped connection or a
    reload, and refusing that would discard an answer the candidate gave
    inside their own time. That is the silent loss this phase exists to
    prevent, arriving through the door built to prevent it.
    """
    profile = await session.get(SimulationProfile, attempt.profile_id)
    minutes = profile.estimated_minutes if profile else 0
    if not app_deadline.accepts_recording(attempt.started_at, minutes):
        # 410 rather than 409, and the distinction carries weight. The runner
        # keeps unsent work in IndexedDB and retries it, and it reads 409 as
        # "the server already has this" -- which is true of the duplicate
        # refusal below and false here. Answering both with 409 would have the
        # client delete audio the server never took.
        raise HTTPException(status.HTTP_410_GONE,
                            app_deadline.RECORDING_TOO_LATE_MESSAGE)


async def _within_deadline(session: TenantSession, attempt: Attempt,
                           composed_at: datetime | None = None) -> None:
    """Refuse a new answer after the sitting has run out. Never refuse a submit.

    The asymmetry is the whole point. Expiry means the candidate did not reach
    the remaining questions; it does not mean the answers they gave are void,
    and the only way those answers get kept is by letting `submit` through
    whatever the clock says.

    Enforced here rather than trusted to the countdown in the browser, because
    a device clock can be wrong by minutes and because a closed tab does not
    stop a determined POST.
    """
    profile = await session.get(SimulationProfile, attempt.profile_id)
    minutes = profile.estimated_minutes if profile else 0
    if app_deadline.accepts_answer(attempt.started_at, minutes):
        return

    # Past the bell. That refuses a *new* answer, but a chosen or written one
    # can also be late for the reason a recording can: the candidate gave it
    # in time and the request carrying it failed, so it sat in the browser's
    # queue until the connection came back. Refusing that discards work done
    # inside the candidate's own time -- the silent loss this phase exists to
    # prevent, arriving through the door built to prevent it.
    #
    # The runner stamps `composed_at` when the answer was set down, and the
    # stamp has to beat the bell for the recovery window to open. That is
    # weaker than proof, since it comes from the client. It is not nothing:
    # a candidate still typing after the bell stamps after the bell, and the
    # one-answer-per-item rule below already blocks the interesting abuse,
    # which is trying options until one scores.
    if composed_at is not None and composed_at.tzinfo is None:
        composed_at = composed_at.replace(tzinfo=timezone.utc)
    if composed_at is not None and app_deadline.accepts_answer(
            attempt.started_at, minutes, now=composed_at)             and app_deadline.accepts_recording(attempt.started_at, minutes):
        return

    raise HTTPException(status.HTTP_410_GONE, app_deadline.EXPIRED_MESSAGE)


async def _own_attempt(session: TenantSession, principal: Principal,
                       attempt_id: str) -> Attempt:
    attempt = await session.get(Attempt, attempt_id)
    if attempt is None or attempt.user_id != principal.user_id:
        # 404 rather than 403 — confirming an attempt exists is a disclosure.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Attempt not found")
    return attempt


async def _recording_consent(session: TenantSession, user_id: str) -> ConsentRecord | None:
    return (await session.execute(
        select(ConsentRecord)
        .where(ConsentRecord.user_id == user_id, ConsentRecord.scope == "recording")
        .order_by(ConsentRecord.at.desc())
    )).scalars().first()


@router.post("", response_model=RunnerPayload, status_code=status.HTTP_201_CREATED)
async def start_attempt(body: StartAttemptRequest, principal: Principal,
                        session: TenantSession,
                        background: BackgroundTasks,
                        request: Request) -> RunnerPayload:
    """Create an attempt and fix its items up front.

    The item list is decided here and stored, not generated per request: a
    student who reloads mid-test must get the same test back, and an attempt
    whose questions changed under it is not a measurement of anything.
    """
    consent = await _recording_consent(session, principal.user_id)
    if consent is None or not consent.granted:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Recording consent is required before an attempt can start",
        )

    profile = (await session.execute(
        select(SimulationProfile)
        .where(SimulationProfile.id == body.profile_id)
    )).scalars().first()
    if profile is None or profile.status != "published":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Simulation not available")

    # SimulationProfile carries no relationship to its sections — they are a
    # separate collection, addressed by profile_id, and were never anything
    # SQLAlchemy's selectinload could actually eager-load once this became a
    # Beanie document; fetched explicitly instead.
    sections = (await session.execute(
        select(ProfileSection).where(ProfileSection.profile_id == profile.id)
    )).scalars().all()

    if not sections:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"This assessment ({profile.name}) has no sections configured. "
            "Contact your institution admin to add sections before starting.",
        )

    # A practice session may carry the assessment attempt that prescribed it.
    # Validated here so the loop can trust it later: it must be the caller's
    # own scored attempt. Anything else is dropped, not stored.
    source_attempt_id = None
    if body.source_attempt_id:
        source = await session.get(Attempt, body.source_attempt_id)
        if (source is not None and source.user_id == principal.user_id
                and source.status == "scored"):
            source_attempt_id = source.id

    prior = (await session.execute(
        select(func.count()).select_from(Attempt)
        .where(Attempt.user_id == principal.user_id, Attempt.profile_id == profile.id)
    )).scalar_one()

    # Students may attempt a simulation as often as they like -- that is what
    # practice is. Only invited candidates (with an active invitation) are
    # limited to one sitting.
    has_invitation = False
    if body.source_attempt_id:
        has_invitation = True
    if principal.role == CANDIDATE_ROLE and prior and has_invitation:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "You have already sat this assessment. An invitation is for one "
            "sitting -- ask whoever invited you if you need another.")

    attempt = Attempt(
        source_attempt_id=source_attempt_id,
        user_id=principal.user_id,
        profile_id=profile.id,
        attempt_number=int(prior) + 1,
        status="created",
        mode=body.mode if body.mode in {"practice", "official", "stress"} else "practice",
        is_baseline=profile.is_baseline and int(prior) == 0,
        ip_address=_client_ip(request),
    )
    session.add(attempt)
    await session.flush()

    # Tie the invitation to the attempt it produced.
    #
    # `Invitation.attempt_id` has existed since Phase 9, described in the model
    # as "the attempt that followed", and nothing ever wrote it. An operator
    # asking "which sitting did this link produce" had to infer it from the
    # candidate id and a timestamp.
    if principal.role == CANDIDATE_ROLE:
        invitation = (await session.execute(
            select(Invitation).where(
                Invitation.candidate_id == principal.user_id,
                Invitation.profile_id == profile.id)
        )).scalars().first()
        if invitation is not None and not invitation.attempt_id:
            invitation.attempt_id = attempt.id

    position = 1

    # An unscored item first, where the assessment asks for one.
    #
    # Somebody sitting a hiring assessment has usually never used this before,
    # and the first thing they say is spent finding the tone, the timing and
    # whether the microphone works at all. Scoring that measures the software's
    # unfamiliarity rather than their English. One item, from the first
    # section, marked so nothing it produces counts.
    if getattr(profile, "practice_item", False) and sections:
        first = min(sections, key=lambda s: s.position)
        kind, key = app_sections.source_of(first.task_type)
        if kind == "task":
            for item in await _pick_items(session, first, principal.user_id,
                                          task_type=key,
                                          company=getattr(profile, "company", "")):
                session.add(Response(
                    attempt_id=attempt.id, section_id=first.id,
                    item_id=item.id, position=position, is_practice=True))
                position += 1
                break

    for section in sorted(sections, key=lambda s: s.position):
        # Where the items come from is a property of the task type, not of
        # how it is answered -- Dictation is typed and draws on the spoken
        # sentence bank. The Response row is the same shape whichever bank it
        # points at, which is what keeps one attempt lifecycle across all
        # three modes rather than an engine per skill.
        kind, key = app_sections.source_of(section.task_type)

        if kind == "task":
            for item in await _pick_items(session, section, principal.user_id,
                                          task_type=key,
                                          company=getattr(profile, "company", "")):
                session.add(Response(
                    attempt_id=attempt.id, section_id=section.id,
                    item_id=item.id, position=position,
                ))
                position += 1
        elif kind == "quiz":
            for quiz in await _pick_quiz_items(session, section, key,
                                              company=getattr(profile, "company", ""),
                                              user_id=principal.user_id):
                session.add(Response(
                    attempt_id=attempt.id, section_id=section.id,
                    quiz_item_id=quiz.id, position=position,
                ))
                position += 1
        else:
            for prompt in await _pick_writing_prompts(session, section, key,
                                                    company=getattr(profile, "company", ""),
                                                    user_id=principal.user_id):
                session.add(Response(
                    attempt_id=attempt.id, section_id=section.id,
                    prompt_id=prompt.id, position=position,
                ))
                position += 1

    await session.commit()
    payload = await _runner_payload(session, attempt, profile)
    # Warm the prompt-audio cache for every clip this attempt will play. On
    # real hardware the first Listen & Repeat clip took 12 s and a later one
    # over 20 s to arrive because each was synthesised on first request
    # (UAT D2); synthesising them now, off the request, makes Play Audio
    # near-instant. Best effort: a failure here changes nothing that
    # serve_prompt does not already handle.
    background.add_task(_prewarm_prompt_audio,
                        await _spoken_texts_for(session, attempt.id))
    return payload


def _pool_of(section: ProfileSection) -> "app_selection.PoolFilter":
    """This section's configured filter, or the empty one.

    A stored configuration that will not parse is treated as no configuration
    rather than as a reason to fail the attempt: a candidate mid-test is not
    the person who can fix an admin's typo, and the publish guard is where a
    bad filter is supposed to be caught.
    """
    try:
        return app_selection.from_dict(getattr(section, "selection", None))
    except (ValueError, TypeError) as exc:
        log.warning("unusable selection on section %s: %s", section.id, exc)
        return app_selection.EMPTY


async def _previously_used_ids(session: TenantSession, user_id: str,
                               model, id_field: str) -> set[str]:
    """Get question IDs already used by this user in previous attempts.

    Avoids repeating the same questions across different exams of the same
    type, providing better coverage of the question bank.
    """
    from app.models.tenant import Response, Attempt
    try:
        resp = await session.execute(
            select(Response.item_id, Response.quiz_item_id, Response.prompt_id)
            .join(Attempt, Attempt.id == Response.attempt_id)
            .where(Attempt.user_id == user_id, Attempt.status == "scored")
        )
        rows = resp.all()
        ids = set()
        for row in rows:
            val = getattr(row, id_field, None)
            if val:
                ids.add(val)
        return ids
    except Exception:
        return set()


def _deduplicate(pool: list, used: set[str], key: str = "id") -> list:
    """Remove items already used by this user from the pool."""
    if not used:
        return pool
    return [i for i in pool if getattr(i, key, None) not in used]


# The most questions any single exam section will ever serve, whatever the
# profile asks for. The question banks (superadmin) hold far more than one
# sitting needs; a cap keeps every exam legible and answerable (Option B),
# while still drawing from the shared bank first.
MAX_QUESTIONS_PER_SECTION = 10


async def _pick_writing_prompts(session: TenantSession,
                                section: ProfileSection,
                                kind: str = "",
                                company: str = "",
                                user_id: str = "") -> list:
    """Choose writing tasks for a written section.

    Filtered by kind, which it was not: every published prompt was a
    composition task until reconstruction passages joined the same table, and
    an unfiltered pool would have served a candidate a printer notice to
    reply to. `prompt_kinds_for` is the authority on which kinds belong to
    which section, so the rule lives with the other task-type properties
    rather than as a condition here.
    """
    from app.models.tenant import WritingPrompt

    allowed = app_sections.prompt_kinds_for(kind)
    pool = list((await session.execute(
        select(WritingPrompt).where(WritingPrompt.status == "published",
                                    WritingPrompt.kind.in_(sorted(allowed)))
    )).scalars().all())

    # Prefer company-tagged prompts, fall back to general pool.
    if company:
        company_pool = [i for i in pool if getattr(i, "company", "") == company]
        general_pool = [i for i in pool if getattr(i, "company", "") != company]
        pool = company_pool + general_pool
    pool = app_selection.eligible(pool, _pool_of(section), "writing_prompt")

    # Cross-exam deduplication: avoid prompts already used by this user.
    if user_id:
        used = await _previously_used_ids(session, user_id, WritingPrompt, "prompt_id")
        pool = _deduplicate(pool, used, "id")

    if not pool:
        return []
    target = min(section.item_count, MAX_QUESTIONS_PER_SECTION)
    return app_selection.draw(pool, target, _pool_of(section)).items


async def _pick_quiz_items(session: TenantSession, section: ProfileSection,
                           category: str = "", company: str = "",
                           user_id: str = "") -> list:
    """Choose the questions for a listening or reading section.

    Comprehension is measured over a whole passage, so questions are drawn
    passage by passage rather than individually: four questions about one
    announcement is one listening event, and mixing four questions from four
    different passages would mean four separate listenings crammed into a
    section budgeted for one.

    Randomised across passages so a retake is not the identical test.
    """
    from app.models.tenant import QuizItem

    # The caller normally passes the category; falling back to the central
    # map rather than a local copy is what stopped the two drifting the last
    # three times a task type was added.
    if not category:
        kind, key = app_sections.source_of(section.task_type)
        category = key if kind == "quiz" else ""
    if not category:
        return []

    pool = list((await session.execute(
        select(QuizItem).where(QuizItem.category == category,
                               QuizItem.status == "published")
    )).scalars().all())

    # Prefer company-tagged questions, fall back to general pool.
    if company:
        company_pool = [i for i in pool if getattr(i, "company", "") == company]
        general_pool = [i for i in pool if getattr(i, "company", "") != company]
        pool = company_pool + general_pool

    # Cross-exam deduplication: avoid questions already used by this user.
    if user_id:
        used = await _previously_used_ids(session, user_id, QuizItem, "quiz_item_id")
        pool = _deduplicate(pool, used, "id")

    if not pool:
        return []

    # Standalone questions are picked individually; only comprehension is
    # drawn whole passages at a time.
    if not app_sections.groups_by_passage(category):
        pool = app_selection.eligible(pool, _pool_of(section), "quiz")
        if not pool:
            return []
        target = min(section.item_count, MAX_QUESTIONS_PER_SECTION)
        return app_selection.draw(pool, target, _pool_of(section)).items

    # Grouped categories filter whole passages, never individual questions.
    #
    # Filtering the questions first and grouping afterwards would hand a
    # candidate three of a passage's four questions and call it a listening
    # event -- the exact thing whole-passage selection exists to prevent. So a
    # difficulty filter here means "passages whose questions are all in
    # range", applied before the subset-sum runs.
    pool_filter = _pool_of(section)
    if pool_filter.configured:
        by_id: dict[str, list] = {}
        for item in pool:
            by_id.setdefault(item.passage_id or "", []).append(item)
        keep = {pid for pid, group in by_id.items()
                if all(app_selection.matches(q, pool_filter, "quiz")
                       for q in group)}
        pool = [i for i in pool if (i.passage_id or "") in keep]
        if not pool:
            return []

    by_passage: dict[str, list] = {}
    for item in pool:
        by_passage.setdefault(item.passage_id or "", []).append(item)

    passages = list(by_passage)
    random.shuffle(passages)

    # Whole passages that fill the section. The algorithm lives in
    # app.sections so it can be tested directly: routed through the API it
    # only misfires on certain shuffles, which is how the greedy version it
    # replaced survived a passing test.
    best = app_sections.fill_from_passages(
        {pid: len(by_passage[pid]) for pid in passages},
        min(section.item_count, MAX_QUESTIONS_PER_SECTION))

    chosen: list = []
    for pid in best:
        chosen.extend(sorted(by_passage[pid], key=lambda x: x.id))
    return chosen


async def _pick_items(session: TenantSession, section: ProfileSection,
                      user_id: str = "",
                      task_type: str | None = None,
                      company: str = "") -> list[TaskItem]:
    """Choose this section's items.

    Adaptive where the item bank has been calibrated, random where it has not
    (ENG-14). The fallback is not a degraded mode to apologise for -- until
    responses exist, "at the edge of your ability" is a claim with nothing
    behind it, and choosing among authored guesses would not make it true.
    """
    # Usually the section's own task type; Dictation borrows the Repeat
    # Sentence bank, so the caller can say which.
    wanted = task_type or section.task_type
    pool = list((await session.execute(
        select(TaskItem).where(TaskItem.task_type == wanted,
                               TaskItem.status == "published")
    )).scalars().all())

    # When a profile targets a company, prefer its questions and fall back
    # to general pool so the section is never empty.
    if company:
        company_pool = [i for i in pool if getattr(i, "company", "") == company]
        general_pool = [i for i in pool if getattr(i, "company", "") != company]
        pool = company_pool + general_pool

    # Narrow before choosing, never after. Choosing adaptively and then
    # filtering would discard exactly the items the ability estimate picked.
    pool_filter = _pool_of(section)
    pool = app_selection.eligible(pool, pool_filter, "task")

    # Cross-exam deduplication: avoid questions already used by this user.
    if user_id:
        used = await _previously_used_ids(session, user_id, TaskItem, "item_id")
        pool = _deduplicate(pool, used, "id")

    if not pool:
        return []

    count = min(section.item_count, len(pool),
                    MAX_QUESTIONS_PER_SECTION)

    # An explicit difficulty mix beats adaptive selection.
    #
    # Both control difficulty and they cannot both be in charge. An admin who
    # configured "half hard" asked a question about the assessment; adaptive
    # selection answers a question about the candidate. When somebody has
    # stated the shape of the test, that is the one to honour -- and a
    # diagnostic, which configures nothing, still adapts exactly as before.
    if pool_filter.mix:
        return app_selection.draw(pool, count, pool_filter).items

    calibrated = [i for i in pool if i.calibrated]
    if len(calibrated) < count or not user_id:
        return random.sample(pool, count)

    theta = await _ability_of(session, user_id)
    candidates = [irt.ItemParameters(item_id=i.id, difficulty=i.difficulty,
                                     discrimination=i.discrimination,
                                     calibrated=True)
                  for i in calibrated]
    by_id = {i.id: i for i in calibrated}

    chosen: list[TaskItem] = []
    seen: set[str] = set()
    for _ in range(count):
        pick = irt.select_next(theta, candidates, exclude=seen)
        if pick is None:
            break
        seen.add(pick.item_id)
        chosen.append(by_id[pick.item_id])
    return chosen or random.sample(pool, count)


async def _ability_of(session: TenantSession, user_id: str) -> float:
    """A working ability estimate from what this student has already scored."""
    scores = list((await session.execute(
        select(ScoreRecord.score)
        .join(Attempt, Attempt.id == ScoreRecord.attempt_id)
        .where(Attempt.user_id == user_id,
               ScoreRecord.dimension == "overall",
               ScoreRecord.response_id.is_(None),
               ScoreRecord.is_shadow.is_(False))
        .order_by(ScoreRecord.created_at.desc()).limit(5)
    )).scalars().all())
    return irt.ability_from_scores(scores)


async def _institution_name(principal: Principal) -> str:
    """Whose assessment this is, for the screen that says so.

    Read from the control plane because a tenant schema does not carry its own
    display name -- the same lookup the invitation preview does.
    """
    from app.db import platform_sessionmaker
    from app.models.platform import Tenant

    if not principal.tenant_id:
        return ""
    async with platform_sessionmaker()() as platform:
        tenant = await platform.get(Tenant, principal.tenant_id)
        return tenant.name if tenant else ""


@router.get("/resume", response_model=CandidateResume)
async def resume(principal: Principal,
                 session: TenantSession) -> CandidateResume:
    """Where an invited candidate left off.

    A candidate holds one thing: a session minted when they spent their
    invitation link. That link is single-use, so it cannot tell them anything
    a second time -- and the invite page recomputed its refusal from the
    invitation row alone, which meant a reload after claiming showed "this
    link has already been used, somebody else has your link" to the person who
    had used it a minute earlier. Every other route refuses a candidate by
    role, so they were stranded with a valid session and nowhere to go.

    Declared before the ``/{attempt_id}/...`` routes so a literal path can
    never be read as an attempt id.

    Returns an empty answer rather than 404 for anybody with no invitation.
    An enrolled student asking where they left off is not an error; the answer
    is just that this is not how they get there.
    """
    invitation = (await session.execute(
        select(Invitation)
        .where(Invitation.candidate_id == principal.user_id)
        .order_by(Invitation.redeemed_at.desc())
    )).scalars().first()

    if invitation is None:
        return CandidateResume()

    profile = await session.get(SimulationProfile, invitation.profile_id)

    # The attempt is looked up rather than read off the invitation, because
    # the invitation records the *first* one and the source of truth for
    # "where am I now" is the attempt table.
    attempt = (await session.execute(
        select(Attempt)
        .where(Attempt.user_id == principal.user_id,
               Attempt.profile_id == invitation.profile_id)
        .order_by(Attempt.attempt_number.desc())
    )).scalars().first()

    consented = (await session.execute(
        select(ConsentRecord.id).where(
            ConsentRecord.user_id == principal.user_id,
            ConsentRecord.scope == "recording",
            ConsentRecord.granted.is_(True))
    )).scalars().first()

    return CandidateResume(
        profile_id=invitation.profile_id,
        profile_name=profile.name if profile else "",
        profile_description=profile.description if profile else "",
        estimated_minutes=profile.estimated_minutes if profile else 0,
        tenant_name=await _institution_name(principal),
        attempt_id=attempt.id if attempt else None,
        attempt_status=attempt.status if attempt else "",
        consent_given=consented is not None,
    )


@router.get("/{attempt_id}/runner", response_model=RunnerPayload)
async def runner(attempt_id: str, principal: Principal,
                 session: TenantSession) -> RunnerPayload:
    attempt = await _own_attempt(session, principal, attempt_id)
    profile = (await session.execute(
        select(SimulationProfile).where(SimulationProfile.id == attempt.profile_id)
    )).scalars().first()
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Simulation not found")
    # The attempt starts when the runner is opened, not against a separate
    # screen. A standalone environment check used to be that boundary; with it
    # gone, opening the runner is what starts the sitting and its clock. A
    # created-but-never-opened attempt (deep link, abandoned tab) stays idle.
    if attempt.status == "created" and attempt.started_at is None:
        attempt.status = "in_progress"
        attempt.started_at = datetime.now(timezone.utc)
        await session.commit()
    return await _runner_payload(session, attempt, profile)


async def _select_mode_sources(session: TenantSession, responses):
    """Everything a non-speaking item is built from.

    Three dictionaries, one per bank -- the same three kinds ``ITEM_SOURCE``
    names. A written task's prompt now has its own id column; before it did,
    a writing section could not even be started, because the column it was
    borrowing has a foreign key pointing somewhere else.
    """
    from app.models.tenant import (ListeningPassage, QuizItem, ReadingPassage,
                                   WritingPrompt)

    quiz_ids = [r.quiz_item_id for r in responses if r.quiz_item_id]
    prompt_ids = [r.prompt_id for r in responses if r.prompt_id]
    if not quiz_ids and not prompt_ids:
        return {}, {}, {}

    quiz = {q.id: q for q in (await session.execute(
        select(QuizItem).where(QuizItem.id.in_(quiz_ids or [""]))
    )).scalars().all()}

    prompts = {w.id: w for w in (await session.execute(
        select(WritingPrompt).where(WritingPrompt.id.in_(prompt_ids or [""]))
    )).scalars().all()}

    passage_ids = [q.passage_id for q in quiz.values() if q.passage_id]
    passages: dict[str, object] = {}
    for model in (ListeningPassage, ReadingPassage):
        for row in (await session.execute(
            select(model).where(model.id.in_(passage_ids or [""]))
        )).scalars().all():
            passages[row.id] = row
    return quiz, passages, prompts


def _written_item(response, section, prompt) -> RunnerItem:
    """One written task: something to compose, or a passage to reconstruct.

    The two differ in what the candidate is allowed to keep looking at. An
    email prompt stays on screen -- reading the brief is not the test. A
    reconstruction passage is taken away after `stimulus_seconds`, because
    holding it is the entire measurement.

    They also differ in what the rubric is. An email's key points are the
    instructions and are shown. A reconstruction's key points are the answer,
    and sending them would let a candidate write the list back and score full
    recall of a passage they never read.

    What they share: the material sits in `stimulus_text` and nowhere else.
    Sending it in `scenario` as well printed the thread twice on the runner
    -- once in the panel above the question and once as small grey text below
    it -- which reads as a bug in the test rather than a brief.
    """
    reconstruction = section.task_type == "passage_reconstruction"
    body = prompt.scenario or prompt.prompt

    return RunnerItem(
        response_id=response.id,
        position=response.position,
        section_id=section.id,
        section_title=section.title,
        task_type=section.task_type,
        instructions=section.instructions,
        prep_seconds=section.prep_seconds,
        response_seconds=section.response_seconds,
        prompt_plays_allowed=section.prompt_plays_allowed,
        response_mode=app_sections.mode_of(section.task_type),
        skill=app_sections.skill_of(section.task_type),
        stimulus_title=prompt.title,
        stimulus_text=body if reconstruction else prompt.scenario,
        stimulus_seconds=(app_reconstruction.reading_seconds(
            len(body.split())) if reconstruction else 0),
        question=prompt.prompt,
        scenario="",
        key_points=([] if reconstruction
                    else _visible_key_points(prompt.key_points)),
        min_words=int(prompt.min_words or 0),
    )


def _visible_key_points(key_points) -> list[str]:
    """A writing prompt's rubric with the scorer's cue words removed."""
    out: list[str] = []
    for entry in key_points or []:
        if isinstance(entry, dict):
            label = str(entry.get("point", ""))
        else:
            label = str(entry)
        if label:
            out.append(label)
    return out


def _select_item(response, section, question, passages) -> RunnerItem:
    """One multiple-choice item, with its passage attached.

    The correct answer never leaves the server here -- it arrives with the
    result, the same rule the standalone quiz and the practice modules follow.

    A listening passage's words are withheld from the payload for the same
    reason a Repeat Sentence prompt is: the candidate is meant to hear it, and
    shipping the transcript alongside the question would turn a listening test
    into a reading one. A reading passage is sent, because reading it is the
    task.
    """
    passage = passages.get(question.passage_id or "")
    listening = app_sections.skill_of(section.task_type) == "listening"

    mode = app_sections.mode_of(section.task_type)

    return RunnerItem(
        response_id=response.id,
        position=response.position,
        section_id=section.id,
        section_title=section.title,
        task_type=section.task_type,
        instructions=section.instructions,
        prep_seconds=section.prep_seconds,
        response_seconds=section.response_seconds,
        prompt_plays_allowed=section.prompt_plays_allowed,
        response_mode=mode,
        skill=app_sections.skill_of(section.task_type),
        has_prompt_audio=listening,
        # An opaque handle to the passage this question belongs to, so the
        # runner can group a listening event -- one clip, then its questions --
        # and play the audio exactly once per passage rather than once per
        # question. It is only an id: the transcript and the answer key stay on
        # the server, so exposing it leaks nothing a candidate could use.
        passage_ref=(question.passage_id or "") if listening else "",
        stimulus_title=getattr(passage, "title", "") if passage else "",
        stimulus_text=("" if listening
                       else getattr(passage, "body", "") if passage else ""),
        question=question.stem,
        # Only a chosen answer gets options. Sentence completion stores its
        # accepted words in the same column, and shipping those would hand
        # the candidate the answer key.
        options=list(question.options or []) if mode == "select" else [],
    )


async def _runner_payload(session: TenantSession, attempt: Attempt,
                          profile: SimulationProfile) -> RunnerPayload:
    responses = list((await session.execute(
        select(Response).where(Response.attempt_id == attempt.id)
        .order_by(Response.position)
    )).scalars().all())

    profile_sections = (await session.execute(
        select(ProfileSection).where(ProfileSection.profile_id == profile.id)
    )).scalars().all()
    sections = {s.id: s for s in profile_sections}
    item_ids = [r.item_id for r in responses if r.item_id]
    items = {i.id: i for i in (await session.execute(
        select(TaskItem).where(TaskItem.id.in_(item_ids or [""]))
    )).scalars().all()}

    quiz, passages, prompts = await _select_mode_sources(session, responses)

    budgets = formats.section_budgets(profile.code)
    behaviour = formats.section_behaviour(profile.code)

    def _flags(section) -> dict:
        b = behaviour.get(section.title, {})
        return {
            "fixed_window": bool(b.get("fixed_window")),
            "allow_skip": bool(b.get("allow_skip")),
            "skip_prep": bool(b.get("skip_prep")),
            "ack_gate": str(b.get("ack_gate") or ""),
            "continuous_numbering": bool(b.get("continuous_numbering")),
            "show_instruction": bool(b.get("show_instruction")),
        }
    # What the server already holds, so a reload resumes rather than restarts.
    response_ids = [r.id for r in responses] or [""]
    with_audio = set((await session.execute(
        select(ResponseAudio.response_id).where(
            ResponseAudio.response_id.in_(response_ids),
            ResponseAudio.deleted_at.is_(None)))).scalars().all())
    with_features = set((await session.execute(
        select(FeatureRecord.response_id).where(
            FeatureRecord.response_id.in_(response_ids)))).scalars().all())

    def _answered(r: Response) -> bool:
        return bool(r.skipped or r.selected_index is not None
                    or r.id in with_audio or r.id in with_features)

    payload_items: list[RunnerItem] = []
    for r in responses:
        section = sections.get(r.section_id or "")
        if section is None:
            continue

        # Which bank this item came from is a property of the task type
        # rather than a guess from whichever id column happens to be set.
        kind, _ = app_sections.source_of(section.task_type)

        if kind == "writing_prompt":
            prompt = prompts.get(r.prompt_id or "")
            if prompt is None:
                continue
            built = _written_item(r, section, prompt)
            built.section_budget_seconds = budgets.get(section.title, 0)
            built.answered = _answered(r)
            for k, v in _flags(section).items():
                setattr(built, k, v)
            payload_items.append(built)
            continue

        if r.quiz_item_id:
            question = quiz.get(r.quiz_item_id)
            if question is None:
                continue
            built = _select_item(r, section, question, passages)
            built.section_budget_seconds = budgets.get(section.title, 0)
            built.answered = _answered(r)
            for k, v in _flags(section).items():
                setattr(built, k, v)
            payload_items.append(built)
            continue

        item = items.get(r.item_id or "")
        if item is None:
            continue
        visible = section.task_type in VISIBLE_PROMPT_TASKS
        # Speak on the Topic: the suggestion questions under the topic. They
        # live in the item's rubric as `cues`, apart from `key_points`, so
        # they are shown and never scored against -- the reference calls
        # them "just suggestions".
        cues = (list((item.rubric or {}).get("cues", []))
                if section.task_type == "open_response"
                and behaviour.get(section.title, {}).get("show_cues") else [])
        payload_items.append(RunnerItem(
            response_id=r.id,
            position=r.position,
            section_id=section.id,
            section_title=section.title,
            task_type=section.task_type,
            instructions=section.instructions,
            prep_seconds=section.prep_seconds,
            response_seconds=section.response_seconds,
            prompt_plays_allowed=section.prompt_plays_allowed,
            # A Repeat Sentence prompt is withheld until it is played, and
            # then it is played once. Shipping it here would defeat both.
            prompt_text=item.prompt_text if visible else "",
            has_prompt_audio=bool(item.prompt_audio_key) or not visible,
            # How this item is answered. Everything authored before the other
            # two modes existed answers "speak", which is what it always did.
            response_mode=app_sections.mode_of(section.task_type),
            skill=app_sections.skill_of(section.task_type),
            # Dictation borrows the spoken-sentence bank but is typed. Its
            # words are never shown -- hearing them is the task -- so the
            # question is an instruction rather than the sentence itself.
            question=("Type what you heard, exactly as you heard it."
                      if section.task_type == "dictation" else ""),
            key_points=[str(c) for c in cues if str(c).strip()],
            section_budget_seconds=budgets.get(section.title, 0),
            answered=_answered(r),
            **_flags(section),
        ))

    # The whole-sitting clock, computed here rather than in the browser. The
    # client is given the deadline *and* what time this server thinks it is,
    # so a countdown can correct for a device clock that is wrong by minutes
    # instead of quietly running on it.
    clock = app_deadline.clock_for(attempt.started_at, profile.estimated_minutes)

    return RunnerPayload(
        attempt_id=attempt.id, profile_id=profile.id, profile_name=profile.name,
        style=profile.style, company=profile.company,
        status=attempt.status, mode=attempt.mode, is_baseline=attempt.is_baseline,
        items=payload_items,
        deadline_at=clock.deadline_at, server_now=clock.server_now,
        seconds_remaining=clock.seconds_remaining,
    )


async def _spoken_texts_for(session, attempt_id: str) -> list[tuple[str, str]]:
    """(text, accent) for every prompt this attempt will play, deduplicated."""
    from app.models.tenant import ListeningPassage, QuizItem

    rows = list((await session.execute(
        select(Response).where(Response.attempt_id == attempt_id)
        .order_by(Response.position))).scalars().all())
    section_ids = {r.section_id for r in rows if r.section_id} or {""}
    sections = {s.id: s for s in (await session.execute(
        select(ProfileSection).where(ProfileSection.id.in_(section_ids)))).scalars().all()}
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for r in rows:
        section = sections.get(r.section_id or "")
        if section is None or section.prompt_plays_allowed <= 0:
            continue
        spoken, accent = "", "indian"
        if r.item_id:
            item = await session.get(TaskItem, r.item_id)
            if item is not None:
                spoken = (item.reference_text
                          if app_sections.speaks_reference(section.task_type)
                          else item.prompt_text)
                accent = item.prompt_accent
        elif r.quiz_item_id:
            question = await session.get(QuizItem, r.quiz_item_id)
            if question is not None and question.passage_id:
                passage = await session.get(ListeningPassage, question.passage_id)
                if passage is not None:
                    spoken, accent = passage.transcript, passage.accent
        if spoken and spoken not in seen:
            seen.add(spoken)
            out.append((spoken, accent))
    return out


def _prewarm_prompt_audio(texts: list[tuple[str, str]]) -> None:
    """Synthesise each clip into app.tts's cache. Runs after the response."""
    for text, accent in texts:
        try:
            tts.synthesize(text, accent)
        except Exception:  # noqa: BLE001 - best effort, never surfaces
            continue


@router.post("/{attempt_id}/responses/{response_id}/prompt",
             response_model=PromptResponse)
async def serve_prompt(attempt_id: str, response_id: str, principal: Principal,
                       session: TenantSession) -> PromptResponse:
    """Serve a prompt and count it. This is where one-shot is enforced.

    Hiding the replay button would be theatre — the count lives here, so a
    reload, a second tab, or a hand-written request all hit the same limit.

    Until real prompt audio exists (SIM-06), the text is returned for the
    browser to speak. That does put the sentence in a network response a
    determined student could read, which is an accepted M1 trade-off in
    practice mode and the reason pre-rendered audio is part of the Tier-1
    work rather than optional polish.
    """
    await _own_attempt(session, principal, attempt_id)

    response = await session.get(Response, response_id)
    if response is None or response.attempt_id != attempt_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")

    section = await session.get(ProfileSection, response.section_id or "")
    if section is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")

    item = (await session.get(TaskItem, response.item_id)
            if response.item_id else None)
    # A listening item's words live on the passage, not on a TaskItem -- it
    # has none. Looking only at TaskItem is why a Listening Comprehension
    # section played nothing at all: the endpoint 404ed, the runner caught it
    # as "the prompt could not be played", and a candidate was asked four
    # questions about an announcement they never heard.
    spoken, accent = "", "indian"
    if item is not None:
        spoken = (item.reference_text
                  if app_sections.speaks_reference(section.task_type)
                  else item.prompt_text)
        accent = item.prompt_accent
    elif response.quiz_item_id:
        spoken, accent = await _heard_stimulus(session, response, section)

    if not spoken:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")

    allowed = section.prompt_plays_allowed
    if allowed <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "This item has no audio prompt")
    if response.prompt_plays >= allowed:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This prompt has already been played. Real tests do not replay either.",
        )

    response.prompt_plays += 1
    response.prompt_served_at = datetime.now(timezone.utc)
    await session.commit()

    # Real prompt audio where the host can synthesise it (see app.tts). Runs off
    # the event loop because it shells out. Returns None on a host without the
    # tools, and the runner falls back to the browser voice -- so the count
    # above is committed either way and one-shot holds regardless of audio.
    audio_url = await asyncio.to_thread(tts.data_uri, spoken, accent)

    return PromptResponse(
        text=spoken,
        accent=accent,
        audio_url=audio_url,
        plays_remaining=max(0, allowed - response.prompt_plays),
    )


async def _heard_stimulus(session, response, section) -> tuple[str, str]:
    """The words behind a select-mode listening item, and the accent to say them in.

    Both listening task types store their audio as a ListeningPassage:
    comprehension shares one passage across several questions, response
    selection has one line per question. The difference is how many questions
    point at the row, which is a property of the bank rather than of this
    endpoint.
    """
    from app.models.tenant import ListeningPassage, QuizItem

    if app_sections.skill_of(section.task_type) != "listening":
        # A reading question has nothing to play. Its passage is on the
        # screen, which is the task.
        return "", "indian"

    question = await session.get(QuizItem, response.quiz_item_id or "")
    if question is None or not question.passage_id:
        return "", "indian"
    passage = await session.get(ListeningPassage, question.passage_id)
    if passage is None:
        return "", "indian"
    return passage.transcript, passage.accent


@router.post("/{attempt_id}/responses/{response_id}/audio",
             status_code=status.HTTP_201_CREATED)
async def upload_response_audio(attempt_id: str, response_id: str,
                                principal: Principal, session: TenantSession,
                                background: BackgroundTasks,
                                file: UploadFile = File(...),
                                ended_by: str = Form("")) -> dict:
    """Ingest one recorded answer.

    ``ended_by`` is the client's statement of why the recording stopped
    (user_ended / auto_advance / window_expired / cancelled). It exists so
    the report never tells a candidate they "ran out of time" on an answer
    they deliberately ended: the acoustic signal alone cannot tell those
    apart. Unknown values are stored as "" — never guessed.

    Signal quality is measured here, once, on the way in — it is what lets the
    report tell a student their microphone cost them points only when that is
    actually true, and it also sets the retention clock from their own consent
    record rather than a global default.
    """
    attempt = await _own_attempt(session, principal, attempt_id)

    consent = await _recording_consent(session, principal.user_id)
    if consent is None or not consent.granted:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Recording consent has not been given")

    if attempt.status not in {"in_progress", "created"}:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "This attempt is no longer accepting answers")
    await _recording_still_welcome(session, attempt)

    response = await session.get(Response, response_id)
    if response is None or response.attempt_id != attempt_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")

    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty upload")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            "Recording is too large")

    try:
        wave = decode_wav(data)
    except AudioDecodeError as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from exc

    # Recorded verbatim when recognised; anything else is "" (unknown), and
    # unknown is never reported as a timeout.
    from app.reporting import END_REASONS
    response.ended_by = ended_by if ended_by in END_REASONS else ""

    if response.is_practice:
        # A warm-up is not evidence, so it is not kept.
        #
        # This is also how a practice item stays out of the score without any
        # exclusion logic: no ResponseAudio means `pending_responses` never
        # sees it, the pipeline never scores it, and no ScoreRecord exists to
        # be filtered out of a composite later. The alternative -- store it,
        # score it, then remember to ignore it in four places -- is exactly the
        # shape of bug this codebase keeps finding.
        #
        # The candidate still got what the item is for: they spoke, the meter
        # moved, and they know the microphone works.
        response.duration_ms = wave.duration_ms
        await session.commit()
        return {"stored": False, "practice": True,
                "duration_ms": wave.duration_ms,
                "quality": signal_quality(wave).verdict,
                "note": "This one was practice. It is not kept and not scored."}

    quality = signal_quality(wave)
    key = recording_key(principal.tenant_slug or "unknown", attempt_id, response_id, "wav")
    get_storage().put(key, data, "audio/wav")

    existing = (await session.execute(
        select(ResponseAudio).where(ResponseAudio.response_id == response_id)
    )).scalars().first()
    if existing is not None:
        # Re-uploading the same item would be a second take. The runner never
        # asks for one, and accepting it here would quietly undo one-shot.
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "An answer for this item has already been recorded")

    retention_days = consent.retention_days or settings.recording_retention_days
    session.add(ResponseAudio(
        response_id=response_id,
        storage_key=key,
        mime_type="audio/wav",
        bytes=len(data),
        sample_rate=wave.sample_rate,
        duration_ms=wave.duration_ms,
        peak_dbfs=quality.peak_dbfs,
        noise_floor_dbfs=quality.noise_floor_dbfs,
        clipped=quality.clipped,
        delete_after=datetime.now(timezone.utc) + timedelta(days=retention_days),
    ))
    response.duration_ms = wave.duration_ms
    await session.commit()

    # Scored now, not at submit: by the time the student finishes the next
    # item, this one already has a transcript and a score.
    background.add_task(_score_in_background, principal.tenant_slug or "",
                        principal.tenant_id, response_id)

    return {
        "stored": True,
        "duration_ms": wave.duration_ms,
        "quality": quality.verdict,
        "delete_after_days": retention_days,
    }


@router.post("/{attempt_id}/responses/{response_id}/answer",
             status_code=status.HTTP_201_CREATED)
async def submit_answer(attempt_id: str, response_id: str,
                        body: AnswerSubmission, principal: Principal,
                        session: TenantSession) -> dict:
    """Take a chosen or written answer, mark it, and store the evidence.

    The counterpart of the audio upload for the other two response modes. One
    endpoint rather than two, because the difference between choosing an
    option and typing a paragraph is what gets scored, not how it arrives.

    Marked here rather than at submit time so a candidate's answer is durable
    the moment they give it: an attempt abandoned halfway still holds
    everything answered up to that point, which is the same guarantee the
    audio path gives.
    """
    attempt = await _own_attempt(session, principal, attempt_id)
    await _within_deadline(session, attempt, body.composed_at)
    response = await session.get(Response, response_id)
    if response is None or response.attempt_id != attempt_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")

    section = await session.get(ProfileSection, response.section_id or "")
    if section is None:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "That item has no section")

    mode = app_sections.mode_of(section.task_type)
    if mode == "speak":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This item is answered by speaking. Upload the recording instead.")

    # One answer per item. Re-answering would let a candidate try options
    # until one scored, which the one-shot rule exists to prevent.
    already = (await session.execute(
        select(ScoreRecord).where(ScoreRecord.response_id == response_id)
    )).scalars().first()
    if already is not None:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "That item has already been answered")

    if mode == "select":
        scored = await _mark_selected(session, response, section, body)
    else:
        scored = await _mark_written(session, response, section, body)

    response.skipped = False
    await session.commit()
    return scored


def _sole_dimension(task_type: str, fallback: str) -> str:
    """The one dimension a router-marked task type produces.

    Read from ``DIMENSIONS_BY_TASK`` rather than written out here, because
    that table is what ``_unscored_reasons`` compares the produced dimensions
    against. A marking function writing "comprehension" while the table said
    "appropriacy" would score the answer and then report the dimension as
    unmeasured in the same response.
    """
    dims = DIMENSIONS_BY_TASK.get(task_type, frozenset())
    return next(iter(dims)) if len(dims) == 1 else fallback


async def _mark_selected(session, response, section, body) -> dict:
    """Mark a chosen answer against the key held on the server.

    Three task types arrive here and they are not measuring the same thing.
    Comprehension asks what a passage said. Response Selection asks which
    reply fits, where every wrong option is a correct English sentence.
    Vocabulary in Context asks which sense a word carries here, where every
    option is a real meaning of the word. One dimension for all three would
    have told a candidate their listening comprehension was weak when what
    they actually missed was register.
    """
    from app.models.tenant import QuizItem

    question = await session.get(QuizItem, response.quiz_item_id or "")
    if question is None:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "That item has no question behind it")

    correct = body.selected_index == question.correct_index
    # Right or wrong on the internal scale, so a section mean is the
    # proportion correct expressed the same way every other score is.
    score = SCALE_MAX if correct else SCALE_MIN

    session.add(ScoreRecord(
        attempt_id=response.attempt_id, response_id=response.id,
        dimension=_sole_dimension(section.task_type, "comprehension"),
        score=score,
        scale_min=SCALE_MIN, scale_max=SCALE_MAX, band=band_label(score),
        # An individual right-or-wrong is a coin-flip-shaped observation; the
        # section mean is the measurement. Saying so here keeps a single item
        # from being read as a verdict.
        confidence=0.35,
        provider_key="comprehension_key", provider_version="1.0.0",
    ))
    return {"answered": True, "correct": correct}


async def _mark_completion(session, response, text: str) -> dict:
    """One typed word against the set of words that genuinely fit.

    A set rather than a single string, because English usually allows more
    than one word in a slot and marking "although" wrong because the author
    wrote "though" teaches a student something false about their own English.

    Not the essay scorer, for the same reason dictation is not: a one-word
    answer has no coherence or lexical range to measure, and running it
    through five measures would produce four numbers about nothing.
    """
    from app.completion_bank import is_correct
    from app.models.tenant import FeatureRecord, QuizItem

    item = await session.get(QuizItem, response.quiz_item_id or "")
    if item is None:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "That item has no sentence behind it")

    accepted = set(item.options or [])
    correct = is_correct(text, accepted)
    score = SCALE_MAX if correct else SCALE_MIN

    session.add(FeatureRecord(
        response_id=response.id, transcript=text,
        metrics={"accepted": sorted(accepted), "correct": correct}))
    session.add(ScoreRecord(
        attempt_id=response.attempt_id, response_id=response.id,
        dimension=_sole_dimension("sentence_completion", "grammar"), score=score,
        scale_min=SCALE_MIN, scale_max=SCALE_MAX, band=band_label(score),
        # One gap is a thin observation; the section mean is the measurement.
        confidence=0.35,
        provider_key="completion_key", provider_version="1.0.0",
    ))
    return {"answered": True, "correct": correct}


async def _mark_dictation(session, response, text: str) -> dict:
    """Word accuracy against the sentence that was played.

    Not the essay scorer: dictation has exactly one right answer, and
    measuring its coherence or lexical range would be measuring the author's
    sentence rather than the candidate's listening.

    Ordered word comparison rather than a bag of words -- "the dog bit the
    man" and "the man bit the dog" contain the same words and are not the
    same answer. Case and terminal punctuation are ignored, because a
    dictation tests what was heard, not typing conventions.
    """
    import difflib
    import re

    from app.models.tenant import FeatureRecord, TaskItem

    item = await session.get(TaskItem, response.item_id or "")
    reference = (item.reference_text or item.prompt_text) if item else ""
    if not reference:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "That dictation item has no sentence behind it")

    def words(value: str) -> list[str]:
        return re.findall(r"[a-z0-9']+", value.lower())

    expected, given = words(reference), words(text)
    matcher = difflib.SequenceMatcher(a=expected, b=given, autojunk=False)
    matched = sum(block.size for block in matcher.get_matching_blocks())
    accuracy = matched / len(expected) if expected else 0.0
    score = round(SCALE_MIN + (SCALE_MAX - SCALE_MIN) * min(1.0, accuracy), 1)

    session.add(FeatureRecord(
        response_id=response.id, transcript=text,
        metrics={"words_expected": len(expected), "words_matched": matched,
                 "word_accuracy": round(accuracy, 3)}))
    session.add(ScoreRecord(
        attempt_id=response.attempt_id, response_id=response.id,
        dimension=_sole_dimension("dictation", "accuracy"), score=score,
        scale_min=SCALE_MIN, scale_max=SCALE_MAX, band=band_label(score),
        confidence=0.7,
        provider_key="dictation_alignment", provider_version="1.0.0",
    ))
    return {"answered": True, "word_accuracy": round(accuracy, 3),
            "words_matched": matched, "words_expected": len(expected)}


async def _mark_reconstruction(session, response, text: str) -> dict:
    """What came back from the passage, and whether it came back as English.

    Not the essay scorer. Coherence and lexical range would be scoring the
    passage's author, and the essay module's forty-word floor would refuse to
    score a short reconstruction -- which is a genuine result and not an
    absence of one.
    """
    from app import reconstruction as scorer
    from app.models.tenant import FeatureRecord, WritingPrompt

    prompt = await session.get(WritingPrompt, response.prompt_id or "")
    if prompt is None:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "That item has no passage behind it")

    source = prompt.scenario or prompt.prompt
    result = await scorer.score(text, idea_units=list(prompt.key_points or []),
                                source=source)

    session.add(FeatureRecord(
        response_id=response.id, transcript=text,
        metrics={"word_count": result.word_count,
                 "source_words": result.source_words,
                 # Recorded, never scored on. See app/reconstruction.py.
                 "verbatim_share": result.verbatim_share}))

    for measure in result.measures:
        if measure.confidence <= 0:
            continue
        session.add(ScoreRecord(
            attempt_id=response.attempt_id, response_id=response.id,
            dimension=_RECONSTRUCTION_DIMENSION.get(measure.name, "content"),
            score=measure.score, scale_min=SCALE_MIN, scale_max=SCALE_MAX,
            band=band_label(measure.score), confidence=measure.confidence,
            provider_key=f"reconstruction_{measure.name}",
            provider_version="0.1.0",
        ))
    return {"answered": True, "word_count": result.word_count,
            "too_short": result.too_short,
            "verbatim_share": result.verbatim_share}


# Mechanics rides with grammar, the same as it does for an essay: it is a
# different kind of mistake but not a dimension one module gets to invent.
_RECONSTRUCTION_DIMENSION = {
    "content_recall": "content",
    "grammatical_accuracy": "grammar",
    "mechanics": "grammar",
}


async def _mark_written(session, response, section, body) -> dict:
    """Score a written answer: dictation by accuracy, everything else by essay."""
    from app import writing as scorer
    from app.models.tenant import FeatureRecord, WritingPrompt

    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nothing was written")

    if section.task_type == "dictation":
        return await _mark_dictation(session, response, text)
    if section.task_type == "sentence_completion":
        return await _mark_completion(session, response, text)
    if section.task_type == "passage_reconstruction":
        return await _mark_reconstruction(session, response, text)

    prompt = await session.get(WritingPrompt, response.prompt_id or "")
    result = await scorer.score_essay(
        text,
        key_points=list(prompt.key_points or []) if prompt else [],
        min_words=int(prompt.min_words or 0) if prompt else 0)

    # The writing itself is evidence and is kept, the same as a recording:
    # a score with nothing behind it cannot be checked or appealed.
    session.add(FeatureRecord(response_id=response.id, transcript=text,
                              metrics={"word_count": result.word_count}))

    for measure in result.measures:
        if measure.confidence <= 0:
            continue
        session.add(ScoreRecord(
            attempt_id=response.attempt_id, response_id=response.id,
            dimension=_WRITING_DIMENSION.get(measure.name, "content"),
            score=measure.score, scale_min=SCALE_MIN, scale_max=SCALE_MAX,
            band=band_label(measure.score), confidence=measure.confidence,
            provider_key=f"writing_{measure.name}", provider_version="0.1.0",
        ))
    return {"answered": True, "word_count": result.word_count,
            "too_short": result.too_short}


# The writing scorer's own measure names, mapped onto the dimensions the rest
# of the report already speaks. `mechanics` has no equivalent and rides with
# grammar rather than inventing a dimension one module produces.
_WRITING_DIMENSION = {
    "task_response": "content",
    "coherence": "content",
    "lexical_range": "vocabulary",
    "grammatical_accuracy": "grammar",
    "mechanics": "grammar",
}


@router.post("/{attempt_id}/responses/{response_id}/skip",
             status_code=status.HTTP_200_OK)
async def skip_response(attempt_id: str, response_id: str, principal: Principal,
                        session: TenantSession) -> dict:
    """Mark an item unanswered — the timer ran out, or nothing was said."""
    await _own_attempt(session, principal, attempt_id)
    response = await session.get(Response, response_id)
    if response is None or response.attempt_id != attempt_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")
    response.skipped = True
    await session.commit()
    return {"skipped": True}


@router.post("/{attempt_id}/submit", response_model=AttemptResult)
async def submit(attempt_id: str, principal: Principal, session: TenantSession,
                 platform: PlatformSession,
                 background: BackgroundTasks) -> AttemptResult:
    """Close the attempt and compose its score.

    Most of the work is already done — each answer was scored as it arrived.
    This waits only for what is still in flight, and if the last response is a
    long one it hands back a "scoring" result for the page to poll rather than
    holding the request open behind a spinner.
    """
    attempt = await _own_attempt(session, principal, attempt_id)
    if attempt.status == "scored":
        return await _result(session, attempt)

    if attempt.submitted_at is None:
        attempt.submitted_at = datetime.now(timezone.utc)
        attempt.status = "scoring"
        await session.commit()

    started = datetime.now(timezone.utc)
    providers = Providers(platform)

    while True:
        pending = await pending_responses(session, attempt_id)
        if not pending:
            break
        elapsed = (datetime.now(timezone.utc) - started).total_seconds()
        if elapsed > SUBMIT_WAIT_SECONDS:
            # Score the stragglers here rather than trusting a background task
            # that may have died. Idempotent, so a race costs nothing.
            for response_id in pending:
                try:
                    await score_response(session, providers, principal.tenant_id,
                                         response_id)
                except Exception as exc:  # noqa: BLE001
                    log.warning("could not score %s at submit: %s", response_id, exc)
            break
        await asyncio.sleep(0.25)

    # Content for the two spoken-question types, added above the frozen
    # scoring path and before the overall is composed. See
    # app/spoken_content.py for why it cannot live in the pipeline.
    try:
        await spoken_content.score_pending(session, providers,
                                           principal.tenant_id, attempt_id)
    except Exception as exc:  # noqa: BLE001
        # A failure here costs one dimension, which `_unscored_reasons` will
        # then explain. It must not cost the student their whole report.
        log.warning("content scoring failed for attempt %s: %s", attempt_id, exc)

    outcome = await finalise_attempt(session, attempt_id)
    await _run_game_hook(session, platform, principal, attempt, outcome)
    attempt = (await session.execute(
        select(Attempt).where(Attempt.id == attempt_id)
    )).scalars().first() or attempt
    await _ensure_and_kick_narration(session, background,
                                     principal.tenant_slug or "", attempt)
    return await _result(session, attempt, scoring_ms=outcome.elapsed_ms,
                         biggest_lever_override=outcome.biggest_lever)


async def _run_game_hook(session, platform, principal, attempt, outcome) -> None:
    """Award XP, advance the quest, touch the streak — after scoring, never before.

    The reward follows a measured result rather than a button press: that is
    the difference between a game that rewards getting better and one that
    rewards doing more (ENG-22). A failure in here must not cost a student
    their report, so it is logged and swallowed.
    """
    try:
        config = await game.config_for(platform, principal.tenant_id)

        previous = (await session.execute(
            select(ScoreRecord.score)
            .join(Attempt, Attempt.id == ScoreRecord.attempt_id)
            .where(Attempt.user_id == principal.user_id,
                   Attempt.profile_id == attempt.profile_id,
                   Attempt.id != attempt.id,
                   ScoreRecord.dimension == "overall",
                   ScoreRecord.response_id.is_(None))
            .order_by(ScoreRecord.score.desc()).limit(1)
        )).scalars().first()

        sections = list((await session.execute(
            select(ProfileSection.task_type)
            .where(ProfileSection.profile_id == attempt.profile_id)
        )).scalars().all())

        profile = await session.get(SimulationProfile, attempt.profile_id)
        full_simulation = bool(profile and not profile.is_baseline
                               and len(sections) >= 3)

        await game.on_attempt_scored(
            session, config, principal.user_id, attempt.id,
            dimensions=outcome.dimensions,
            is_full_simulation=full_simulation,
            previous_best=previous,
            overall=outcome.overall,
            task_types=set(sections),
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("gamification hook failed for attempt %s: %s", attempt.id, exc)


# Dimensions that cannot exist without a transcript. Kept here rather than
# derived from the pipeline so the explanation survives even when the module
# that would have produced them could not be loaded at all.
_NEEDS_TRANSCRIPT = frozenset({"accuracy", "disfluency", "grammar", "content"})


def _speech_models_present() -> bool:
    """Can this server transcribe at all?

    The same check the health endpoint reports, asked at result time because
    that is where its absence is felt. Import failures are cached by Python
    after the first attempt, so this is cheap.
    """
    for name in ("faster_whisper", "torch"):
        try:
            __import__(name)
        except Exception:  # noqa: BLE001 - absent or broken, same conclusion
            return False
    return True


def _reporting_for(overall, dimensions, skill_out, notes, unscored, rows,
                   has_audio: bool = True, primary=None) -> dict:
    """The plain summary, the highlights, the plan and the evidence.

    Assembled here rather than in `app/reporting.py` so that module stays free
    of schema types and testable as pure functions -- the same split
    `sections.py` and `weighting.py` already use.
    """
    from app import reporting
    from app.schemas import HighlightOut, RecommendationOut

    skills = {s.skill: s.score for s in skill_out}
    report = reporting.build(overall, dimensions, skills, notes, unscored,
                             has_audio, primary)

    def highlight(h) -> HighlightOut:
        return HighlightOut(dimension=h.dimension, score=h.score,
                            delta=h.delta, means=h.means)

    return {
        "summary": report.summary,
        "strengths": [highlight(h) for h in report.strengths],
        "weaknesses": [highlight(h) for h in report.weaknesses],
        "recommendations": [
            RecommendationOut(dimension=r.dimension, current=r.current,
                              target=r.target,
                              predicted_gain=r.predicted_gain, advice=r.advice)
            for r in report.recommendations],
        "evidence": reporting.evidence_index(
            [r.model_dump() if hasattr(r, "model_dump") else dict(r)
             for r in rows]),
    }


def _unscored_reasons(rows, dimensions: dict[str, float]) -> dict[str, str]:
    """What this attempt should have measured but did not, and why.

    This was `dict(UNSCORED)`: a constant that is empty, because on a full
    install there is nothing the engine cannot reach. A deployment missing its
    speech models reported that same empty dict, so an attempt that measured
    *nothing* looked exactly like one that measured everything -- a blank
    score with no explanation, which reads as a broken product rather than an
    incomplete install.

    Computed from what the tasks in this attempt were supposed to produce
    against what actually came back, so it stays honest as the engine changes
    instead of needing a constant kept in step by hand.
    """
    reasons: dict[str, str] = dict(UNSCORED)

    answered = [r for r in rows if not r.skipped]
    if not answered:
        return reasons

    expected: set[str] = set()
    # Which of the missing measures were meant to come from speech. A written
    # or chosen answer has no recording, and telling a candidate that nothing
    # is wrong with a recording they never made explains nothing and points
    # them at the wrong thing.
    from_speech: set[str] = set()
    for row in answered:
        dims = DIMENSIONS_BY_TASK.get(row.task_type, frozenset())
        expected |= dims
        if app_sections.mode_of(row.task_type) == "speak":
            from_speech |= dims

    missing = sorted(expected - set(dimensions))
    if not missing:
        return reasons

    transcribes = _speech_models_present()
    for dimension in missing:
        if dimension in from_speech:
            if dimension in _NEEDS_TRANSCRIPT and not transcribes:
                reasons.setdefault(dimension, NO_TRANSCRIPT)
            else:
                reasons.setdefault(dimension, (
                    "This server did not produce this measure for any of your "
                    "answers. Nothing is wrong with your recording."))
        else:
            reasons.setdefault(dimension, (
                "None of your answers in this part gave enough to measure "
                "this. That is about the answers, not about your equipment."))
    return reasons


async def _persist_sections(session, attempt, sections, responses,
                            per_response, profile):
    """Score each section, store it once, and roll the sections up by skill.

    Idempotent: re-reading a result must not stack a second set of rows, and
    an attempt scored under an older scorer keeps the numbers the student was
    actually shown rather than being silently re-marked on read.
    """
    from app.models.tenant import SectionResult
    from app.schemas import SectionResultOut, SkillScoreOut

    async def _load():
        return list((await session.execute(
            select(SectionResult).where(SectionResult.attempt_id == attempt.id)
            .order_by(SectionResult.position)
        )).scalars().all())

    existing = await _load()

    if not existing and sections:
        # Grouped from the ORM rows rather than the serialised ones: only the
        # ORM Response carries section_id, and the response detail shown to a
        # student deliberately does not.
        by_section: dict[str, list[dict]] = {}
        for response in responses:
            by_section.setdefault(response.section_id or "", []).append(
                {"scores": per_response.get(response.id, {}),
                 "skipped": response.skipped})

        for section in sorted(sections.values(), key=lambda x: x.position):
            item = app_sections.score_section(
                section_id=section.id, position=section.position,
                title=section.title, task_type=section.task_type,
                responses=by_section.get(section.id, []),
                # A section's share of its own skill, read from the section.
                #
                # This used to look the section's *task type* up in
                # `profile.scoring_weights`, which is keyed by *dimension*.
                # The lookup missed every time, so every section rolled up at
                # 1.0 no matter what an admin configured -- and the schema,
                # the stored `SectionResult.weight` and the builder all read
                # as though weighting worked. `scoring_weights` is still the
                # right table for what it holds; it was simply never the
                # table this question should have been asked of.
                weight=float(section.weight or 0.0),
            )
            session.add(SectionResult(
                attempt_id=attempt.id, section_id=item.section_id,
                position=item.position, title=item.title,
                task_type=item.task_type, skill=item.skill,
                score=item.score, dimensions=item.dimensions,
                confidence=item.confidence, weight=item.weight,
                items_total=item.items_total, items_answered=item.items_answered,
                unscored_reason=item.unscored_reason,
                scorer_version=app_sections.SCORER_VERSION,
            ))
        await session.commit()
        existing = await _load()

    stored = [
        app_sections.SectionScore(
            section_id=r.section_id, position=r.position, title=r.title,
            task_type=r.task_type, skill=r.skill, score=r.score,
            dimensions=dict(r.dimensions or {}), confidence=r.confidence,
            weight=r.weight, items_total=r.items_total,
            items_answered=r.items_answered, unscored_reason=r.unscored_reason,
        )
        for r in existing
    ]

    return (
        [SectionResultOut(
            section_id=x.section_id, position=x.position, title=x.title,
            task_type=x.task_type, skill=x.skill, score=x.score,
            dimensions=x.dimensions, confidence=x.confidence,
            weight=x.weight,
            items_total=x.items_total, items_answered=x.items_answered,
            unscored_reason=x.unscored_reason,
        ) for x in stored],
        [SkillScoreOut(skill=v.skill, score=v.score,
                       section_count=v.section_count,
                       unscored_sections=v.unscored_sections, note=v.note)
         for v in app_sections.roll_up(stored).values()],
    )


def _retell_for(rows):
    """Story Retell as two axes, when the attempt contained one.

    Averaged across the retell responses only -- mixing in a Read Aloud score
    would make "Language" mean something different from what the label says.
    """
    from app.retell import breakdown
    from app.schemas import RetellAxisOut, RetellBreakdownOut

    retells = [r for r in rows if r.task_type == "story_retell" and not r.skipped]
    if not retells:
        return None

    pooled: dict[str, list[float]] = {}
    for row in retells:
        for dimension, value in (row.scores or {}).items():
            pooled.setdefault(dimension, []).append(value)
    averaged = {d: sum(v) / len(v) for d, v in pooled.items() if v}

    result = breakdown(averaged)
    return RetellBreakdownOut(
        content=RetellAxisOut(label=result.content.label,
                              score=result.content.score,
                              from_dimensions=result.content.from_dimensions,
                              note=result.content.note),
        language=RetellAxisOut(label=result.language.label,
                               score=result.language.score,
                               from_dimensions=result.language.from_dimensions,
                               note=result.language.note),
        parts_measured=result.parts_measured, note=result.note,
    )


def _weighted_for(profile, dimensions: dict[str, float]):
    """This assessment's own view of the same measurements, if it has one.

    Returns None for a profile that configured nothing, which is every
    practice profile -- there is no sense in which practice passes or fails
    somebody, and showing a pass mark it does not have would invent one.

    The engine composite is untouched and still the headline. This sits
    beside it.
    """
    from app.engine import calibration
    from app.schemas import ThresholdCheckOut, WeightedScoreOut

    if profile is None:
        return None
    configured = bool(profile.scoring_weights) or profile.pass_threshold is not None
    if not configured:
        return None

    result = weighting.apply(
        dimensions,
        profile_weights=dict(profile.scoring_weights or {}),
        pass_threshold=profile.pass_threshold,
        skill_thresholds=dict(profile.skill_thresholds or {}),
        min_dimensions=calibration.MIN_DIMENSIONS_FOR_OVERALL,
    )
    return WeightedScoreOut(
        score=result.score, weights=result.weights,
        using_engine_default=result.using_engine_default,
        unmeasured=result.unmeasured,
        thresholds=[ThresholdCheckOut(dimension=c.dimension, floor=c.floor,
                                      actual=c.actual, met=c.met)
                    for c in result.thresholds],
        passed=result.passed, why=result.why,
    )


@router.get("/{attempt_id}/export.csv")
async def export_csv(attempt_id: str, principal: Principal,
                     session: TenantSession) -> HttpResponse:
    """The whole result as a spreadsheet.

    CSV rather than a PDF because of what each is for. A PDF is a thing you
    send to somebody; a CSV is a thing you can check. A admin wanting to see
    whether a cohort's grammar moved needs rows, and a student disputing a
    score needs the numbers next to the evidence rather than a rendered page
    they cannot interrogate.

    One row per measurement, not one per attempt: a wide row with seven
    dimensions in seven columns stops working the moment an attempt produces
    six, and every attempt on a server with no speech models produces fewer.
    Long format survives that.

    Printing to PDF is the browser's job -- see the print stylesheet on the
    result page. Rendering one here would mean a new dependency and a second
    layout to keep in step with the screen.
    """
    import csv
    import io as _io

    attempt = await _own_attempt(session, principal, attempt_id)
    result = await _result(session, attempt)

    buffer = _io.StringIO()
    writer = csv.writer(buffer, lineterminator=chr(10))
    writer.writerow(["section", "item", "task_type", "measure", "value",
                     "confidence", "note"])

    writer.writerow(["", "", "", "overall",
                     "" if result.overall is None else result.overall,
                     "", result.band])
    for dimension, value in sorted(result.dimensions.items()):
        writer.writerow(["", "", "", dimension, value,
                         result.confidence.get(dimension, ""),
                         result.dimension_notes.get(dimension, "")])
    # Named, not omitted. An export that silently lacks a measure looks like a
    # candidate who scored nothing on it.
    for dimension, why in sorted(result.unscored.items()):
        writer.writerow(["", "", "", dimension, "not measured", "", why])

    for skill in result.skills:
        writer.writerow(["", "", "", f"skill:{skill.skill}",
                         "" if skill.score is None else skill.score, "",
                         skill.note])

    for section in result.sections:
        writer.writerow([section.title, "", section.task_type, "section score",
                         "" if section.score is None else section.score,
                         "" if section.confidence is None else section.confidence,
                         section.unscored_reason])

    by_id = {s.section_id: s.title for s in result.sections}
    for response in result.responses:
        for measure, value in sorted(response.scores.items()):
            writer.writerow([by_id.get(getattr(response, "section_id", ""), ""),
                             response.position, response.task_type, measure,
                             value, "", ""])

    filename = f"result-{attempt_id[:8]}.csv"
    return HttpResponse(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{attempt_id}/result", response_model=AttemptResult)
async def result(attempt_id: str, principal: Principal,
                 session: TenantSession,
                 background: BackgroundTasks) -> AttemptResult:
    """The report. Polled by the result page while an attempt is still scoring.

    The provider is NEVER called here. This endpoint only ensures the durable
    narration job exists on the scored transition and reads its current state;
    generation happens in a BackgroundTask and the sweeper, never inline, so a
    hundred polls make zero provider calls.
    """
    attempt = await _own_attempt(session, principal, attempt_id)

    # Background scoring may have finished after submit gave up waiting.
    if attempt.status == "scoring" and not await pending_responses(session, attempt_id):
        await finalise_attempt(session, attempt_id)
        attempt = (await session.execute(
            select(Attempt).where(Attempt.id == attempt_id)
        )).scalars().first() or attempt

    await _ensure_and_kick_narration(session, background,
                                     principal.tenant_slug or "", attempt)
    return await _result(session, attempt)


@router.get("/{attempt_id}/responses/{response_id}/audio")
async def play_response_audio(attempt_id: str, response_id: str,
                              principal: Principal,
                              session: TenantSession) -> HttpResponse:
    """Stream one recording back to the student who made it (DIAG-02).

    Only to them. There is no admin or admin route to this endpoint and
    there will not be one: staff see scores and mastery, never recordings. A
    recording past its retention date is gone, and says so plainly rather than
    404-ing as though it never existed.
    """
    await _own_attempt(session, principal, attempt_id)

    response = await session.get(Response, response_id)
    if response is None or response.attempt_id != attempt_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")

    audio = (await session.execute(
        select(ResponseAudio).where(ResponseAudio.response_id == response_id)
    )).scalars().first()
    if audio is None or audio.deleted_at is not None or not audio.storage_key:
        raise HTTPException(
            status.HTTP_410_GONE,
            "This recording passed its retention date and was deleted")

    try:
        data = get_storage().get(audio.storage_key)
    except (ValueError, OSError) as exc:
        raise HTTPException(status.HTTP_410_GONE,
                            "This recording is no longer available") from exc

    return HttpResponse(content=data, media_type=audio.mime_type,
                        headers={"Cache-Control": "private, max-age=300"})


def _prompt_text_for(section, item) -> str:
    """What the student actually saw or heard for this item."""
    if item is None:
        return ""
    task_type = section.task_type if section else ""
    if task_type in SPEAK_THE_REFERENCE:
        return item.reference_text or item.prompt_text
    return item.prompt_text or item.reference_text


def _pauses_between(segments: list[dict]) -> list[dict]:
    """Gaps between speech runs, as spans the report can draw.

    Leading and trailing silence are not pauses — a student who thought before
    starting has a latency figure, not a pause problem, and conflating the two
    would point them at the wrong fix.
    """
    out: list[dict] = []
    for a, b in zip(segments, segments[1:]):
        gap = b["start_ms"] - a["end_ms"]
        if gap > 0:
            out.append({"start_ms": a["end_ms"], "end_ms": b["start_ms"], "ms": gap})
    return out


async def _narration_out(session: TenantSession, attempt_id: str) -> NarrationOut | None:
    """Read the AI narration for an attempt. Read-only — never calls a provider.

    This is what the polled result endpoint exposes: whatever state the durable
    job is in right now. It maps content fields only when the job is ready, so
    a client can never mistake an in-flight job for a finished explanation.
    """
    from app.models.tenant import AttemptNarration

    row = (await session.execute(
        select(AttemptNarration).where(AttemptNarration.attempt_id == attempt_id)
    )).scalars().first()
    if row is None:
        return None
    ready = row.status == "ready"
    return NarrationOut(
        status=row.status,
        headline=row.headline if ready else "",
        summary=row.summary if ready else "",
        primary_focus=row.primary_focus if ready else "",
        practice_action=row.practice_action if ready else "",
        caveats=list(row.caveats or []) if ready else [],
        model_version=row.model_version if ready else "",
        generated_at=row.generated_at if ready else None,
    )


async def _narration_kick_task(slug: str, narration_id: str) -> None:
    """Fire-and-forget generation of one job. Failures are the job's problem,
    recorded on its row and retried by the sweeper — never the request's."""
    from app.narration.worker import kick
    try:
        await kick(slug, narration_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("narration kick failed id=%s: %s", narration_id, exc)


async def _ensure_and_kick_narration(session: TenantSession,
                                     background: BackgroundTasks,
                                     slug: str, attempt: Attempt) -> None:
    """On the scored transition, create the narration job once and kick it.

    Safe to call on every poll: ensure_row is idempotent, and the fast-path
    kick is scheduled only for a freshly created, still-unclaimed job. Never
    raises into the report path — a narration problem cannot break a result.
    """
    if attempt.status != "scored":
        return
    try:
        from app.narration import service
        row = await service.ensure_row(session, attempt)
    except Exception as exc:  # noqa: BLE001
        log.warning("narration ensure failed for %s: %s", attempt.id, exc)
        return
    if row is not None and row.status == "pending" and row.attempt_count == 0:
        background.add_task(_narration_kick_task, slug, row.id)


def _diagnosis_out(primary, available: dict, source_attempt: Attempt,
                   source_profile) -> "PrimaryDiagnosisOut":
    """The diagnosis as the API carries it, with the practice resolved for
    this tenant and the attempt that produced it named."""
    from app.schemas import PrimaryDiagnosisOut
    from app.reporting import _advice_for
    prow = available.get(primary.practice_code) if primary.practice_code else None
    return PrimaryDiagnosisOut(
        status=primary.status, headline=primary.headline,
        reason=primary.reason, evidence=primary.evidence,
        dimension=primary.dimension, label=primary.label,
        score=primary.score, responses=primary.responses,
        scale_max=primary.scale_max, confidence=primary.confidence,
        candidates=[{"dimension": c.dimension, "label": _label(c.dimension),
                     "score": round(c.score, 1), "responses": c.responses}
                    for c in primary.candidates],
        excluded=[{"dimension": d, "label": _label(d), "why": why}
                  for d, why in primary.excluded],
        practice_code=primary.practice_code if prow else "",
        practice_profile_id=prow.id if prow else "",
        practice_name=prow.name if prow else "",
        practice_minutes=prow.estimated_minutes if prow else 0,
        advice=_advice_for(primary.dimension) if primary.dimension else "",
        source_attempt_id=source_attempt.id,
        source_profile_id=source_profile.id if source_profile else "",
        source_profile_name=source_profile.name if source_profile else "")


def _label(dimension: str) -> str:
    from app.diagnosis import label
    return label(dimension)


async def _diagnosis_for(session: TenantSession, attempt: Attempt,
                         available_practice: set[str]):
    """An attempt's primary diagnosis, recomputed from its stored scores.

    Deterministic: the same scores through the same function give the same
    answer the result page gave, so a practice result can carry its
    prescribing assessment's diagnosis without storing a copy that could
    drift from it.
    """
    from app import diagnosis as app_diagnosis
    rows = list((await session.execute(
        select(ScoreRecord).where(ScoreRecord.attempt_id == attempt.id,
                                  ScoreRecord.is_shadow.is_(False))
    )).scalars().all())
    dims = {r.dimension: r.score for r in rows
            if r.response_id is None and r.dimension != "overall"}
    overall = next((r for r in rows
                    if r.response_id is None and r.dimension == "overall"), None)
    counts: dict[str, int] = {}
    for r in rows:
        if r.response_id is not None:
            counts[r.dimension] = counts.get(r.dimension, 0) + 1
    return app_diagnosis.diagnose(
        dims, scale_max=overall.scale_max if overall else 80.0,
        response_counts=counts, available_practice=available_practice)


async def _result(session: TenantSession, attempt: Attempt,
                  scoring_ms: int | None = None,
                  biggest_lever_override: dict | None = None) -> AttemptResult:
    from app.engine import calibration
    from app.engine.pipeline import (COVERAGE_NOTES, UNSCORED, WEIGHTS,
                                      biggest_lever)

    profile = await session.get(SimulationProfile, attempt.profile_id)

    scores = list((await session.execute(
        select(ScoreRecord).where(ScoreRecord.attempt_id == attempt.id,
                                  ScoreRecord.is_shadow.is_(False))
    )).scalars().all())

    attempt_level = {s.dimension: s for s in scores if s.response_id is None}
    overall_row = attempt_level.get("overall")
    dimensions = {d: s.score for d, s in attempt_level.items() if d != "overall"}
    confidence = {d: (s.confidence or 0.0) for d, s in attempt_level.items()}

    responses = list((await session.execute(
        select(Response).where(Response.attempt_id == attempt.id)
        .order_by(Response.position)
    )).scalars().all())

    features = {f.response_id: f for f in (await session.execute(
        select(FeatureRecord).where(
            FeatureRecord.response_id.in_([r.id for r in responses] or [""]))
    )).scalars().all()}

    sections = {s.id: s for s in (await session.execute(
        select(ProfileSection).where(ProfileSection.profile_id == attempt.profile_id)
    )).scalars().all()}

    items = {i.id: i for i in (await session.execute(
        select(TaskItem).where(TaskItem.id.in_([r.item_id for r in responses if r.item_id] or [""]))
    )).scalars().all()}

    per_response: dict[str, dict[str, float]] = {}
    for row in scores:
        if row.response_id:
            per_response.setdefault(row.response_id, {})[row.dimension] = row.score

    audio_rows = {
        a.response_id: a for a in (await session.execute(
            select(ResponseAudio).where(
                ResponseAudio.response_id.in_([r.id for r in responses] or [""]))
        )).scalars().all()
    }

    rows: list[ResponseMetrics] = []
    noisy_count = 0
    for r in responses:
        feature = features.get(r.id)
        metrics = feature.metrics if feature else {}
        quality = metrics.get("quality", "good")
        if quality != "good":
            noisy_count += 1
        section = sections.get(r.section_id or "")
        item = items.get(r.item_id or "")
        audio = audio_rows.get(r.id)
        rows.append(ResponseMetrics(
            response_id=r.id,
            position=r.position,
            task_type=section.task_type if section else "",
            # Safe to reveal now: the attempt is over and the score is fixed.
            # The same field choice as when it was served, so the report shows
            # the question that was asked rather than the answer that was wanted.
            prompt_text=_prompt_text_for(section, item),
            skipped=r.skipped,
            onset_ms=metrics.get("onset_ms"),
            speech_ms=metrics.get("speech_ms"),
            duration_ms=r.duration_ms,
            words_per_minute=metrics.get("words_per_minute"),
            articulation_rate=metrics.get("articulation_rate"),
            pause_count=metrics.get("pause_count"),
            longest_pause_ms=metrics.get("longest_pause_ms"),
            quality=quality,
            scores=per_response.get(r.id, {}),
            ended_mid_speech=bool(metrics.get("ended_mid_speech")),
            ended_by=r.ended_by or "",
            completeness=metrics.get("completeness"),
            transcript=feature.transcript if feature else "",
            words=[WordTimingOut(**w) for w in (feature.word_timings if feature else [])],
            pauses=_pauses_between(feature.speech_segments if feature else []),
            disfluencies=(feature.disfluencies if feature else []) or [],
            # The evidence behind the grammar and pronunciation numbers.
            #
            # Both have been stored on FeatureRecord since M2 and neither ever
            # left the server, so the report could say "your grammar was 44"
            # and show nothing it was counted from. A score with no evidence is
            # an assertion; a student who cannot see what was counted cannot
            # disagree with it, and being able to disagree is the difference
            # between a measurement and a verdict.
            grammar_errors=(feature.grammar_errors if feature else []) or [],
            word_errors=(feature.word_errors if feature else []) or [],
            word_clarity=(feature.phoneme_scores if feature else []) or [],
            accuracy=metrics.get("accuracy"),
            has_audio=bool(audio and audio.deleted_at is None and audio.storage_key),
        ))

    # Section results, stored and then reported.
    #
    # These used to be recomputed from the per-response rows on every read,
    # which is fine until the scorer changes -- and then a report a student
    # was already shown quietly becomes a different report. Writing them down
    # is what makes a result reproducible rather than merely recomputable, and
    # it is the join point the four-skill rollup needs.
    section_out, skill_out = await _persist_sections(
        session, attempt, sections, responses, per_response, profile)


    from app import reporting

    answered = [r for r in rows if not r.skipped]
    # "Ran out of time" is a claim about the candidate's behaviour, so it
    # needs both facts: speech ran to the end of the recording AND the window
    # actually expired. A candidate who pressed Stop mid-sentence is not a
    # timeout, and neither is a legacy row that cannot say why it ended.
    truncated = [r for r in answered
                 if reporting.ran_out_of_time(r.ended_mid_speech, r.ended_by)]
    environment_note = ""
    if answered and noisy_count >= max(1, len(answered) // 2):
        environment_note = (
            "Recording conditions affected several of your answers. That is the "
            "room and the microphone, not your English — a quieter spot will give "
            "you a truer reading."
        )

    if truncated:
        # Said before anything about clarity, because a student reading
        # "these words were unclear" about words they never got to say would
        # take away the wrong lesson entirely.
        timing_note = (
            f"{len(truncated)} of your answers ran out of time while you were "
            f"still speaking. The words you did not reach are counted as "
            f"missing, not as unclear — try starting sooner or saying less "
            f"before the main point."
        )
        parts = [timing_note] + ([environment_note] if environment_note else [])
        environment_note = "\n\n".join(parts)

    dimension_notes = {d: COVERAGE_NOTES.get(d, calibration.current().note_for(d))
                       for d in dimensions}

    indication = reporting.cefr(overall_row.score if overall_row else None)

    # -- the improvement loop ------------------------------------------------
    #
    # Before/after: the last *scored* sitting of this same assessment by this
    # student. The delta compares like with like or stays absent -- a missing
    # overall on either side means no number, never a pretended zero.
    from app import priorities as app_priorities
    from app.schemas import PreviousAttemptOut, ResultPriorityOut

    prior = (await session.execute(
        select(Attempt).where(Attempt.profile_id == attempt.profile_id,
                              Attempt.user_id == attempt.user_id,
                              Attempt.id != attempt.id,
                              Attempt.status == "scored")
        .order_by(Attempt.attempt_number.desc()).limit(1)
    )).scalars().first()
    previous_out = None
    if prior is not None:
        prior_overall_row = (await session.execute(
            select(ScoreRecord).where(ScoreRecord.attempt_id == prior.id,
                                      ScoreRecord.response_id.is_(None),
                                      ScoreRecord.dimension == "overall")
        )).scalars().first()
        prior_overall = prior_overall_row.score if prior_overall_row else None
        current_overall = overall_row.score if overall_row else None
        delta = (round(current_overall - prior_overall, 1)
                 if current_overall is not None and prior_overall is not None
                 else None)
        previous_out = PreviousAttemptOut(
            attempt_id=prior.id, attempt_number=prior.attempt_number,
            overall=prior_overall, delta=delta)

    # The single source of truth for "what should I work on first?".
    #
    # app/diagnosis.py applies the product rule once; the summary sentence,
    # the practice priorities, the practice result and the AI narration all
    # consume the object it returns. The frozen engine's ``biggest_lever``
    # is still computed (it is engine output and part of the scoring
    # snapshot) but it is no longer a diagnosis surface: nothing below
    # pins it, renders it as advice, or hands it to the narrator.
    from app import diagnosis as app_diagnosis
    lever = biggest_lever_override or biggest_lever(dimensions)
    counts: dict[str, int] = {}
    for row in scores:
        if row.response_id is not None:
            counts[row.dimension] = counts.get(row.dimension, 0) + 1
    scale_max = overall_row.scale_max if overall_row else 80.0

    # The practice profiles this tenant can actually start. A dimension
    # whose practice is missing here cannot become the primary, and no
    # button is ever drawn for a session that would 404.
    available = {p.code: p for p in (await session.execute(
        select(SimulationProfile).where(
            SimulationProfile.code.in_(list(app_priorities.PRACTICE_CODE.values())),
            SimulationProfile.status == "published"))).scalars().all()}

    is_practice = bool(profile and profile.style == "drill")
    primary = None
    diagnosis_out = None
    priority_out: list[ResultPriorityOut] = []
    if not is_practice:
        primary = app_diagnosis.diagnose(
            dimensions, scale_max=scale_max, response_counts=counts,
            available_practice=set(available))
        diagnosis_out = _diagnosis_out(primary, available, attempt, profile)
        ranked = app_priorities.priorities_for(
            dimensions, scale_max=scale_max, response_counts=counts,
            primary=primary)
        for x in ranked:
            prow = available.get(x.practice_code)
            priority_out.append(ResultPriorityOut(
                dimension=x.dimension, score=x.score, responses=x.responses,
                practice=x.practice, practice_code=x.practice_code,
                practice_profile_id=prow.id if prow else "",
                practice_name=prow.name if prow else "",
                practice_minutes=prow.estimated_minutes if prow else 0,
                verdict=x.verdict, evidence=x.evidence, advice=x.advice))

    # A finished practice reports on itself: the trained dimension, this
    # session's measurement, and the same dimension on the assessment that
    # prescribed it -- the before to this after, with the retake path. It
    # makes no diagnosis of its own; the diagnosis it carries is the
    # prescribing assessment's, recomputed from that attempt's stored
    # scores by the same function that produced it on that result page.
    practice_out = None
    if is_practice and profile.code.startswith("practice_"):
        from app.schemas import PracticeOutcomeOut
        trained = profile.code.removeprefix("practice_")

        # The assessment this practice belongs to. The stored source link is
        # the truth -- the practice was prescribed by an exact result, and
        # the comparison and the retake anchor to it. Only when no link
        # exists (an old attempt, or practice started some other way) does
        # the student's most recent scored assessment stand in, and then the
        # result says so rather than claiming it was the prescriber.
        source = None
        linked = False
        if attempt.source_attempt_id:
            candidate = await session.get(Attempt, attempt.source_attempt_id)
            if candidate is not None and candidate.status == "scored":
                source = (candidate,
                          await session.get(SimulationProfile,
                                            candidate.profile_id))
                linked = True
        if source is None:
            source = (await session.execute(
                select(Attempt, SimulationProfile)
                .join(SimulationProfile,
                      SimulationProfile.id == Attempt.profile_id)
                .where(Attempt.user_id == attempt.user_id,
                       Attempt.id != attempt.id,
                       Attempt.status == "scored",
                       SimulationProfile.style != "drill")
                .order_by(Attempt.scored_at.desc()).limit(1)
            )).first()

        assessment_score = None
        assessment_profile_id = ""
        assessment_profile_name = ""
        source_id = ""
        prescribed_status = ""
        prescribed_dimension = ""
        if source is not None:
            la_attempt, la_profile = source
            row = (await session.execute(
                select(ScoreRecord).where(
                    ScoreRecord.attempt_id == la_attempt.id,
                    ScoreRecord.response_id.is_(None),
                    ScoreRecord.dimension == trained)
            )).scalars().first()
            assessment_score = row.score if row else None
            assessment_profile_id = la_profile.id if la_profile else ""
            assessment_profile_name = la_profile.name if la_profile else ""
            source_id = la_attempt.id
            if linked:
                src_primary = await _diagnosis_for(session, la_attempt,
                                                   set(available))
                diagnosis_out = _diagnosis_out(src_primary, available,
                                               la_attempt, la_profile)
                prescribed_status = src_primary.status
                prescribed_dimension = src_primary.dimension

        this_score = dimensions.get(trained)
        change = (round(this_score - assessment_score, 1)
                  if this_score is not None and assessment_score is not None
                  else None)
        practice_out = PracticeOutcomeOut(
            dimension=trained,
            label=profile.name,
            practice_score=round(this_score, 1) if this_score is not None else None,
            assessment_score=(round(assessment_score, 1)
                              if assessment_score is not None else None),
            assessment_profile_id=assessment_profile_id,
            assessment_profile_name=assessment_profile_name,
            source_attempt_id=source_id,
            source_linked=linked,
            prescribed_status=prescribed_status,
            prescribed_dimension=prescribed_dimension,
            trained_primary=bool(prescribed_dimension)
            and prescribed_dimension == trained,
            change=change,
            practice_responses=int(counts.get(trained, 0)),
            verdict=app_priorities.practice_verdict(
                change, int(counts.get(trained, 0))))

    return AttemptResult(
        attempt_id=attempt.id,
        profile_id=attempt.profile_id,
        profile_name=profile.name if profile else "",
        profile_style=profile.style if profile else "",
        status=attempt.status,
        mode=attempt.mode,
        is_baseline=attempt.is_baseline,
        attempt_number=attempt.attempt_number,
        overall=overall_row.score if overall_row else None,
        band=overall_row.band if overall_row else "",
        dimensions=dimensions,
        confidence=confidence,
        unscored=_unscored_reasons(rows, dimensions),
        weighted=_weighted_for(profile, dimensions),
        retell=_retell_for(rows),
        sections=section_out,
        skills=skill_out,
        ip_address=getattr(attempt, "ip_address", ""),
        started_at=attempt.started_at,
        submitted_at=attempt.submitted_at,
        calibrated=calibration.current().any_calibrated,
        calibration_note=(calibration.OVERALL_UNCALIBRATED_NOTE
                          if not calibration.current().any_calibrated else ""),
        dimension_notes=dimension_notes,
        overall_basis=sorted(d for d in dimensions if d in WEIGHTS),
        cefr_level=indication.level if indication else "",
        cefr_descriptor=indication.descriptor if indication else "",
        cefr_caveat=indication.caveat if indication else "",
        biggest_lever=lever,
        primary_diagnosis=diagnosis_out,
        environment_note=environment_note,
        previous=previous_out,
        priorities=priority_out,
        practice=practice_out,
        # Presentation only. The composite is unchanged -- this phrases it for
        # the format the student chose, and returns None for anything that is
        # not a company round or that never got an overall at all.
        verdict=formats.verdict(profile.style if profile else "",
                                overall_row.score if overall_row else None),
        presentation=formats.presentation(
            profile.code if profile else "",
            overall_row.score if overall_row else None, dimensions,
            # Per-response scores, so a sub-score can be drawn from the tasks
            # its format actually counts rather than averaged over everything.
            [{"task_type": r.task_type, "scores": r.scores} for r in rows]),
        responses=rows,
        scored_at=attempt.scored_at,
        scoring_ms=scoring_ms,
        narration=await _narration_out(session, attempt.id),
        **_reporting_for(overall_row.score if overall_row else None,
                         dimensions, skill_out, dimension_notes,
                         _unscored_reasons(rows, dimensions), rows,
                         # An entirely reading-and-writing assessment produces
                         # no recording to reassure anybody about.
                         any(r.has_audio for r in rows),
                         primary=primary),
    )


# --------------------------------------------------------------------------
# Exam Reviews
# --------------------------------------------------------------------------

@router.post("/{attempt_id}/review", response_model=ReviewOut,
             status_code=status.HTTP_201_CREATED)
async def submit_review(attempt_id: str, body: ReviewRequest,
                        principal: Principal, session: TenantSession) -> ReviewOut:
    """Submit a review for an attempt. One review per student per attempt."""
    from app.db import control_db
    attempt = await _own_attempt(session, principal, attempt_id)
    db = control_db()

    existing = await db.exam_reviews.find_one({
        "attempt_id": attempt_id, "user_id": principal.user_id
    })
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "You have already reviewed this attempt.")

    import uuid
    review_id = str(uuid.uuid4())
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    doc = {
        "_id": review_id,
        "attempt_id": attempt_id,
        "user_id": principal.user_id,
        "tenant_id": principal.tenant_id or "",
        "profile_id": attempt.profile_id or "",
        "rating": body.rating,
        "difficulty": body.difficulty,
        "comment": body.comment,
        "created_at": now,
    }
    await db.exam_reviews.insert_one(doc)

    profile = await session.get(SimulationProfile, attempt.profile_id)
    return ReviewOut(
        id=review_id, attempt_id=attempt_id,
        user_id=principal.user_id,
        user_name=principal.full_name,
        user_email=principal.email,
        profile_name=profile.name if profile else "",
        rating=body.rating, difficulty=body.difficulty,
        comment=body.comment, created_at=now,
    )


@router.get("/{attempt_id}/review", response_model=ReviewOut | None)
async def get_my_review(attempt_id: str, principal: Principal,
                        session: TenantSession) -> ReviewOut | None:
    """Get the current user's review for an attempt, if any."""
    from app.db import control_db
    await _own_attempt(session, principal, attempt_id)
    db = control_db()
    doc = await db.exam_reviews.find_one({
        "attempt_id": attempt_id, "user_id": principal.user_id
    })
    if doc is None:
        return None
    profile = await session.get(SimulationProfile, doc.get("profile_id", ""))
    return ReviewOut(
        id=str(doc.get("_id", "")), attempt_id=attempt_id,
        user_id=principal.user_id,
        user_name=principal.full_name,
        user_email=principal.email,
        profile_name=profile.name if profile else "",
        rating=doc.get("rating", 0), difficulty=doc.get("difficulty", "just_right"),
        comment=doc.get("comment", ""), created_at=doc.get("created_at", ""),
    )


@router.get("/{attempt_id}/reviews", response_model=list[ReviewOut])
async def get_attempt_reviews(attempt_id: str, principal: Principal,
                              session: TenantSession) -> list[ReviewOut]:
    """All reviews for an attempt. Visible to admins and super admins."""
    from app.db import control_db
    db = control_db()
    raw = await db.exam_reviews.find({"attempt_id": attempt_id}).to_list()
    if not raw:
        return []
    user_ids = list({r.get("user_id", "") for r in raw if r.get("user_id")})
    profile_ids = list({r.get("profile_id", "") for r in raw if r.get("profile_id")})
    users = {}
    if user_ids:
        async for u in db.users.find({"_id": {"$in": user_ids}}):
            users[u["_id"]] = u
    profiles = {}
    if profile_ids:
        async for p in db.simulation_profiles.find({"_id": {"$in": profile_ids}}):
            profiles[p["_id"]] = p
    return [
        ReviewOut(
            id=str(r.get("_id", "")), attempt_id=attempt_id,
            user_id=r.get("user_id", ""),
            user_name=users.get(r.get("user_id", ""), {}).get("full_name", ""),
            user_email=users.get(r.get("user_id", ""), {}).get("email", ""),
            profile_name=profiles.get(r.get("profile_id", ""), {}).get("name", ""),
            rating=r.get("rating", 0), difficulty=r.get("difficulty", "just_right"),
            comment=r.get("comment", ""), created_at=r.get("created_at", ""),
        )
        for r in raw
    ]

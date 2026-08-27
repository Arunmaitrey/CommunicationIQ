"""Per-institution models — declared as Beanie Documents.

In the Mongo design every institution gets its OWN database (``tenant_<slug>``),
so these documents are bound to that database at request time (see
``app.db.ensure_tenant_models``). No document here names a tenant, because the
database *is* the boundary (TEN-12).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from beanie import Document, Indexed
from pydantic import Field

from app.models._common import StrId


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# People and consent
# --------------------------------------------------------------------------

class User(Document):
    """An institution user: tenant admin, trainer, or student."""

    id: StrId = Field(default_factory=_uuid)
    email: str = Field(unique=True, index=True)
    full_name: str
    password_hash: str
    role: str = "student"
    active: bool = True
    must_change_password: bool = False

    roll_number: str = ""
    branch: str = ""
    year_of_study: int | None = None
    l1_language: str = ""
    ui_language: str = "en"
    preferred_theme: str = ""

    last_login_at: datetime | None = None
    created_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "users"


class ConsentRecord(Document):
    """Verifiable consent, captured before the first recording (STU-02, DPDP)."""

    id: StrId = Field(default_factory=_uuid)
    user_id: str = Field(default="", index=True)
    scope: str = Field(default="", index=True)
    granted: bool = True
    notice_version: str = "1.0"
    notice_language: str = "en"
    retention_days: int = 30
    ip_address: str = ""
    at: datetime = Field(default_factory=_now)

    class Settings:
        name = "consent_records"


class Cohort(Document):
    """A batch: branch/year/section, with the placement window that drives the season."""

    id: StrId = Field(default_factory=_uuid)
    name: str
    branch: str = ""
    year_of_study: int | None = None
    section: str = ""
    trainer_id: str | None = Field(default=None, index=True)
    drive_start: datetime | None = None
    drive_end: datetime | None = None
    active: bool = True
    created_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "cohorts"


class CohortMember(Document):
    id: StrId = Field(default_factory=_uuid)
    cohort_id: str = Field(default="", index=True)
    user_id: str = Field(default="", index=True)
    joined_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "cohort_members"


# --------------------------------------------------------------------------
# Content: profiles, items
# --------------------------------------------------------------------------

class Invitation(Document):
    """A link that lets one external person sit one assessment, once."""

    id: StrId = Field(default_factory=_uuid)
    token: str = Field(unique=True, index=True)
    profile_id: str = Field(default="", index=True)
    invited_name: str = ""
    invited_email: str = ""
    reference: str = ""
    status: str = "pending"
    expires_at: datetime | None = None
    redeemed_at: datetime | None = None
    candidate_id: str | None = Field(default=None, index=True)
    attempt_id: str | None = None
    created_by: str | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "invitations"


class SimulationProfile(Document):
    """A configured test: which sections, in what order, with what timing (SIM-01)."""

    id: StrId = Field(default_factory=_uuid)
    code: str = Field(default="", index=True)
    name: str
    style: str = "diagnostic"
    company: str = ""
    description: str = ""
    version: int = 1
    status: str = "draft"
    estimated_minutes: int = 20
    score_scale: dict = Field(default_factory=dict)
    scoring_weights: dict = Field(default_factory=dict)
    pass_threshold: float | None = None
    skill_thresholds: dict = Field(default_factory=dict)
    target_role: str = ""
    department: str = ""
    practice_item: bool = False
    camera_check: bool = False
    difficulty_band: str = ""
    is_baseline: bool = False
    created_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "simulation_profiles"


class ProfileSection(Document):
    """One section of a profile — a task type plus its pacing rules."""

    id: StrId = Field(default_factory=_uuid)
    profile_id: str = Field(default="", index=True)
    position: int = 1
    title: str
    task_type: str = Field(default="", index=True)
    instructions: str = ""
    item_count: int = 5
    prep_seconds: int = 0
    response_seconds: int = 30
    prompt_plays_allowed: int = 1
    allow_replay: bool = False
    auto_advance: bool = True
    difficulty_target: float = 0.0
    weight: float = 1.0
    selection: dict = Field(default_factory=dict)

    class Settings:
        name = "profile_sections"


class TaskItem(Document):
    """One speaking item in the bank (CONTENT-01)."""

    id: StrId = Field(default_factory=_uuid)
    task_type: str = Field(default="", index=True)
    prompt_text: str = ""
    company: str = ""
    prompt_audio_key: str = ""
    prompt_accent: str = "indian"
    reference_text: str = ""
    rubric: dict = Field(default_factory=dict)
    word_count: int = 0
    difficulty: float = 0.0
    discrimination: float = 1.0
    calibrated: bool = False
    l1_group: str = ""
    skill_tags: list = Field(default_factory=list)
    topic: str = ""
    role: str = ""
    industry: str = ""
    language: str = ""
    source: str = "authored"
    version: int = 1
    status: str = "published"
    created_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "task_items"


class QuizItem(Document):
    """MCQ / fill-in-the-blank / error-ID item (QUIZ-01)."""

    id: StrId = Field(default_factory=_uuid)
    category: str = Field(default="", index=True)
    stem: str
    options: list = Field(default_factory=list)
    correct_index: int = 0
    explanation: str = ""
    company: str = ""
    clip_audio_key: str = ""
    passage_id: str = ""
    seconds_allowed: int = 30
    difficulty: float = 0.0
    discrimination: float = 1.0
    skill_tags: list = Field(default_factory=list)
    topic: str = ""
    version: int = 1
    status: str = "published"

    class Settings:
        name = "quiz_items"


class ListeningPassage(Document):
    """Something spoken, with comprehension questions written against it."""

    id: StrId = Field(default_factory=_uuid)
    title: str
    kind: str = "short_talk"
    transcript: str
    company: str = ""
    audio_key: str = ""
    accent: str = "indian"
    plays_allowed: int = 1
    approx_seconds: int = 45
    difficulty: float = 0.0
    status: str = "published"
    created_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "listening_passages"


class WritingPrompt(Document):
    """Something to write, and what a good answer has to contain."""

    id: StrId = Field(default_factory=_uuid)
    title: str
    kind: str = "email"
    prompt: str
    company: str = ""
    scenario: str = ""
    key_points: list = Field(default_factory=list)
    min_words: int = 120
    suggested_minutes: int = 20
    difficulty: float = 0.0
    status: str = "published"
    created_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "writing_prompts"


class WritingSubmissionRow(Document):
    """One piece of writing and what it scored."""

    id: StrId = Field(default_factory=_uuid)
    user_id: str = Field(default="", index=True)
    prompt_id: str = Field(default="", index=True)
    text: str = ""
    word_count: int = 0
    minutes_spent: int = 0
    overall: float | None = None
    measures: dict = Field(default_factory=dict)
    scorer_version: str = "0.1.0"
    submitted_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "writing_submissions"


class ReadingPassage(Document):
    """Something to read, with comprehension questions and a rate measure."""

    id: StrId = Field(default_factory=_uuid)
    title: str
    kind: str = "article"
    body: str
    company: str = ""
    word_count: int = 0
    difficulty: float = 0.0
    status: str = "published"
    created_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "reading_passages"


class ReadingAttempt(Document):
    """One student, one passage: how fast they read it and how much they took in."""

    id: StrId = Field(default_factory=_uuid)
    user_id: str = Field(default="", index=True)
    passage_id: str = Field(default="", index=True)
    read_ms: int = 0
    words_per_minute: int | None = None
    correct: int = 0
    total: int = 0
    score: float | None = None
    started_at: datetime = Field(default_factory=_now)
    completed_at: datetime | None = None

    class Settings:
        name = "reading_attempts"


class ListeningAttempt(Document):
    """One student, one passage, one sitting."""

    id: StrId = Field(default_factory=_uuid)
    user_id: str = Field(default="", index=True)
    passage_id: str = Field(default="", index=True)
    plays_used: int = 0
    correct: int = 0
    total: int = 0
    score: float | None = None
    started_at: datetime = Field(default_factory=_now)
    completed_at: datetime | None = None

    class Settings:
        name = "listening_attempts"


class Assignment(Document):
    """A profile assigned to a cohort with a deadline (TEN-06)."""

    id: StrId = Field(default_factory=_uuid)
    cohort_id: str = Field(default="", index=True)
    profile_id: str = Field(default="", index=True)
    assigned_by: str | None = Field(default=None, index=True)
    mandatory: bool = True
    opens_at: datetime | None = None
    due_at: datetime | None = None
    max_attempts: int = 3
    created_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "assignments"


# --------------------------------------------------------------------------
# Assessment: attempts, responses, audio, scores
# --------------------------------------------------------------------------

class Attempt(Document):
    """One sitting of one profile by one student."""

    id: StrId = Field(default_factory=_uuid)
    user_id: str = Field(default="", index=True)
    profile_id: str = Field(default="", index=True)
    assignment_id: str | None = Field(default=None, index=True)
    attempt_number: int = 1
    status: str = "created"
    mode: str = "practice"
    source_attempt_id: str | None = None
    is_baseline: bool = False
    env_check: dict = Field(default_factory=dict)
    device_info: dict = Field(default_factory=dict)
    ip_address: str = ""
    started_at: datetime | None = None
    submitted_at: datetime | None = None
    scored_at: datetime | None = None
    created_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "attempts"


class Response(Document):
    """One item's worth of a student's attempt."""

    id: StrId = Field(default_factory=_uuid)
    attempt_id: str = Field(default="", index=True)
    section_id: str | None = Field(default=None, index=True)
    item_id: str | None = Field(default=None, index=True)
    quiz_item_id: str | None = Field(default=None, index=True)
    prompt_id: str | None = Field(default=None, index=True)
    position: int = 1
    is_practice: bool = False
    prompt_plays: int = 0
    prompt_served_at: datetime | None = None
    selected_index: int | None = None
    is_correct: bool | None = None
    response_latency_ms: int | None = None
    duration_ms: int | None = None
    ended_by: str = ""
    skipped: bool = False
    created_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "responses"


class ResponseAudio(Document):
    """The recording. Holds a storage *key*, never a filesystem path."""

    id: StrId = Field(default_factory=_uuid)
    response_id: str = Field(unique=True, index=True)
    storage_key: str
    mime_type: str = "audio/webm"
    bytes: int = 0
    sample_rate: int = 48000
    duration_ms: int = 0
    peak_dbfs: float | None = None
    noise_floor_dbfs: float | None = None
    clipped: bool = False
    delete_after: datetime | None = Field(default=None, index=True)
    deleted_at: datetime | None = None
    created_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "response_audio"


class FeatureRecord(Document):
    """Raw engine output for one response — transcript, timings, acoustics."""

    id: StrId = Field(default_factory=_uuid)
    response_id: str = Field(default="", index=True)
    transcript: str = ""
    word_timings: list = Field(default_factory=list)
    speech_segments: list = Field(default_factory=list)
    metrics: dict = Field(default_factory=dict)
    phoneme_scores: list = Field(default_factory=list)
    word_errors: list = Field(default_factory=list)
    grammar_errors: list = Field(default_factory=list)
    disfluencies: list = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "feature_records"


class SectionResult(Document):
    """One section of one attempt, scored and stored."""

    id: StrId = Field(default_factory=_uuid)
    attempt_id: str = Field(default="", index=True)
    section_id: str = ""
    position: int = 0
    title: str = ""
    task_type: str = ""
    skill: str = "speaking"
    score: float | None = None
    dimensions: dict = Field(default_factory=dict)
    confidence: float | None = None
    weight: float = 1.0
    items_total: int = 0
    items_answered: int = 0
    unscored_reason: str = ""
    computed_at: datetime = Field(default_factory=_now)
    scorer_version: str = ""

    class Settings:
        name = "section_results"


class ScoreRecord(Document):
    """A score, and exactly what produced it."""

    id: StrId = Field(default_factory=_uuid)
    attempt_id: str = Field(default="", index=True)
    response_id: str | None = Field(default=None, index=True)
    dimension: str = Field(default="", index=True)
    score: float
    scale_min: float = 20
    scale_max: float = 80
    band: str = ""
    confidence: float | None = None
    provider_id: str = ""
    provider_key: str = ""
    provider_version: str = ""
    is_shadow: bool = False
    computed_ms: int = 0
    created_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "score_records"


# --------------------------------------------------------------------------
# Diagnosis and training
# --------------------------------------------------------------------------

class SkillMastery(Document):
    """Per-student, per-sub-skill mastery — the honest half of the progress UI."""

    id: StrId = Field(default_factory=_uuid)
    user_id: str = Field(default="", index=True)
    skill: str = Field(default="", index=True)
    mastery: float = 0.0
    confidence: float = 0.0
    observations: int = 0
    baseline: float | None = None
    last_change: float = 0.0
    plateau_since: datetime | None = None
    updated_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "skill_mastery"


class Drill(Document):
    """One run through the fail → why → similar items → challenge → re-test loop."""

    id: StrId = Field(default_factory=_uuid)
    user_id: str = Field(default="", index=True)
    target_skill: str = Field(default="", index=True)
    source: str = "auto"
    assigned_by: str | None = Field(default=None, index=True)
    origin_response_id: str | None = Field(default=None, index=True)
    item_ids: list = Field(default_factory=list)
    status: str = "pending"
    items_completed: int = 0
    mastery_before: float | None = None
    mastery_after: float | None = None
    created_at: datetime = Field(default_factory=_now)
    completed_at: datetime | None = None

    class Settings:
        name = "drills"


class MistakeBankEntry(Document):
    """A wrong answer on a spaced-repetition schedule (QUIZ-05)."""

    id: StrId = Field(default_factory=_uuid)
    user_id: str = Field(default="", index=True)
    quiz_item_id: str | None = Field(default=None, index=True)
    task_item_id: str | None = Field(default=None, index=True)
    skill: str = ""
    times_wrong: int = 1
    times_right_since: int = 0
    interval_days: int = 1
    due_at: datetime = Field(default_factory=_now, index=True)
    mastered: bool = False
    created_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "mistake_bank_entries"


# --------------------------------------------------------------------------
# Gamification
# --------------------------------------------------------------------------

class XPLedger(Document):
    """Append-only XP record (NFR-15)."""

    id: StrId = Field(default_factory=_uuid)
    user_id: str = Field(default="", index=True)
    activity: str = Field(default="", index=True)
    ref_type: str = ""
    ref_id: str = ""
    base_xp: int = 0
    difficulty_multiplier: float = 1.0
    weakness_multiplier: float = 1.0
    awarded_xp: int = 0
    cap_applied: str = ""
    target_skill: str = ""
    at: datetime = Field(default_factory=_now, index=True)

    class Settings:
        name = "xp_ledger"


class StreakState(Document):
    """Current streak and freeze inventory (GAM-04/05)."""

    id: StrId = Field(default_factory=_uuid)
    user_id: str = Field(unique=True, index=True)
    current_streak: int = 0
    best_streak: int = 0
    last_qualifying_day: date | None = None
    freezes_available: int = 2
    freezes_used_this_month: int = 0
    freeze_history: list = Field(default_factory=list)
    repairs_used_this_month: int = 0
    updated_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "streak_states"


class Quest(Document):
    """A daily or weekly objective built from the student's own weakest skill."""

    id: StrId = Field(default_factory=_uuid)
    user_id: str = Field(default="", index=True)
    kind: str = "daily"
    for_date: date = Field(default_factory=lambda: datetime.now(timezone.utc).date(), index=True)
    title: str
    description: str = ""
    target_skill: str = ""
    objective: dict = Field(default_factory=dict)
    progress: float = 0.0
    target: float = 1.0
    completed: bool = False
    completed_at: datetime | None = None
    bonus_xp: int = 0
    created_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "quests"


class SeasonPlan(Document):
    """The countdown to a real drive date, and the weekly plan derived from it."""

    id: StrId = Field(default_factory=_uuid)
    user_id: str = Field(default="", index=True)
    cohort_id: str | None = Field(default=None, index=True)
    drive_date: datetime | None = None
    starts_on: date
    ends_on: date
    weekly_themes: list = Field(default_factory=list)
    daily_minutes_target: int = 25
    replans: list = Field(default_factory=list)
    active: bool = True
    created_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "season_plans"


class Badge(Document):
    """Badge definition. Criteria are versioned so an earned badge stays meaningful."""

    id: StrId = Field(default_factory=_uuid)
    code: str = Field(unique=True, index=True)
    name: str
    description: str = ""
    category: str = "mastery"
    criteria: dict = Field(default_factory=dict)
    criteria_version: int = 1
    icon: str = "award"

    class Settings:
        name = "badges"


class EarnedBadge(Document):
    id: StrId = Field(default_factory=_uuid)
    user_id: str = Field(default="", index=True)
    badge_id: str = Field(default="", index=True)
    criteria_version: int = 1
    earned_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "earned_badges"


class LeagueMembership(Document):
    """Weekly league placement (GAM-11) — opt-in, pseudonymous."""

    id: StrId = Field(default_factory=_uuid)
    user_id: str = Field(default="", index=True)
    week_start: date = Field(default_factory=lambda: datetime.now(timezone.utc).date(), index=True)
    group_key: str = Field(default="", index=True)
    tier: str = "bronze"
    display_name: str = ""
    week_xp: int = 0
    opted_in: bool = False

    class Settings:
        name = "league_memberships"


# --------------------------------------------------------------------------
# Operations
# --------------------------------------------------------------------------

class EngagementEvent(Document):
    """Telemetry behind healthy-vs-hollow engagement analysis (PLAT-18)."""

    id: StrId = Field(default_factory=_uuid)
    user_id: str = Field(default="", index=True)
    event: str = Field(default="", index=True)
    payload: dict = Field(default_factory=dict)
    weakness_targeted: bool = False
    at: datetime = Field(default_factory=_now, index=True)

    class Settings:
        name = "engagement_events"


class NotificationLog(Document):
    """Sent notifications, with the cap accounting that NOTIF-05 requires."""

    id: StrId = Field(default_factory=_uuid)
    user_id: str = Field(default="", index=True)
    channel: str = "in_app"
    category: str = "engagement"
    template: str = ""
    subject: str = ""
    body: str = ""
    suppressed_reason: str = ""
    read_at: datetime | None = None
    sent_at: datetime = Field(default_factory=_now, index=True)

    class Settings:
        name = "notification_log"


class StudentFlag(Document):
    """Trainer's at-risk flag with a staff-visible note (TRN-03)."""

    id: StrId = Field(default_factory=_uuid)
    user_id: str = Field(default="", index=True)
    raised_by: str = Field(default="", index=True)
    reason: str = "at_risk"
    note: str = ""
    auto_suggested: bool = False
    resolved: bool = False
    resolved_at: datetime | None = None
    created_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "student_flags"


# --------------------------------------------------------------------------
# AI narration (explains the frozen result; never part of scoring)
# --------------------------------------------------------------------------

class AttemptNarration(Document):
    """The AI explanation of one finished attempt — and its own durable job."""

    id: StrId = Field(default_factory=_uuid)
    attempt_id: str = Field(unique=True, index=True)
    status: str = "pending"
    attempt_count: int = 0
    next_retry_at: datetime | None = Field(default=None, index=True)
    lease_until: datetime | None = Field(default=None, index=True)
    last_error_category: str = ""
    last_error_detail: str = ""
    prompt_version: str = ""
    model_version: str = ""
    provider_key: str = ""
    headline: str = ""
    summary: str = ""
    primary_focus: str = ""
    practice_action: str = ""
    caveats: list = Field(default_factory=list)
    provider_latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
    generated_at: datetime | None = None

    class Settings:
        name = "attempt_narrations"


TENANT_DOCUMENTS = [
    User, ConsentRecord, Cohort, CohortMember, Invitation, SimulationProfile,
    ProfileSection, TaskItem, QuizItem, ListeningPassage, WritingPrompt,
    WritingSubmissionRow, ReadingPassage, ReadingAttempt, ListeningAttempt,
    Assignment, Attempt, Response, ResponseAudio, FeatureRecord, SectionResult,
    ScoreRecord, SkillMastery, Drill, MistakeBankEntry, XPLedger, StreakState,
    Quest, SeasonPlan, Badge, EarnedBadge, LeagueMembership, EngagementEvent,
    NotificationLog, StudentFlag, AttemptNarration,
]

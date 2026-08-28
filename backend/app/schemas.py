"""API request/response shapes.

Field names stay snake_case; the frontend's api client is the single place
that maps them to camelCase, exactly as QSprint does it.
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import (BaseModel, EmailStr, Field, field_validator,
                      model_validator)


# --------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str = Field(min_length=1, max_length=120)


class SessionUser(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    scope: str
    tenant_id: str | None = None
    tenant_slug: str | None = None
    tenant_name: str | None = None
    # What the tenant wants their people to see. Carried on the session rather
    # than fetched separately: the shell needs it on first paint, and a second
    # round trip would mean the product logo showing first and being replaced,
    # which looks like a bug even though it is only a race.
    tenant_display_name: str | None = None
    tenant_logo_url: str | None = None
    tenant_primary_color: str | None = None
    must_change_password: bool = False
    preferred_theme: str = ""


class LoginResponse(BaseModel):
    token: str
    user: SessionUser


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


# --------------------------------------------------------------------------
# Shared
# --------------------------------------------------------------------------

class UserOut(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    active: bool
    roll_number: str = ""
    branch: str = ""
    year_of_study: int | None = None
    l1_language: str = ""
    created_at: datetime | None = None


class CohortOut(BaseModel):
    id: str
    name: str
    branch: str
    year_of_study: int | None
    section: str
    drive_start: datetime | None
    drive_end: datetime | None
    member_count: int = 0
    active: bool


class ProfileSectionOut(BaseModel):
    id: str
    position: int
    title: str
    task_type: str
    instructions: str
    item_count: int
    prep_seconds: int
    response_seconds: int
    prompt_plays_allowed: int
    allow_replay: bool
    weight: float = 1.0
    # Read back, not just stored. `scoring_weights` spent months being written
    # by nothing and returned by nothing, and looked like a working feature to
    # anybody reading the schema. A stored value that no serialiser returns
    # cannot be edited, reviewed, or even seen to be wrong.
    selection: dict = {}
    # The lettered section's time budget this sub-section sits under, from
    # the blueprint (0 where none is stated). Shown on the card.
    budget_seconds: int = 0


class SimulationProfileOut(BaseModel):
    id: str
    code: str
    name: str
    style: str
    # Which employer's round this imitates. Empty for everything else.
    company: str = ""
    description: str
    status: str
    estimated_minutes: int
    # How long a sitting usually takes, where the blueprint can say. The
    # pair is shown as "about X-Y minutes at a normal pace": `estimated` is
    # the computed ceiling of every timed window, not a cap on the sitting
    # (untimed sections have no clock), so it must never be shown as "up to".
    typical_minutes: int = 0
    # The whole-sitting hard stop (app/deadline.py): estimate plus grace.
    # Untimed sections have no clock of their own, but the sitting does.
    sitting_limit_minutes: int = 0
    is_baseline: bool
    # What a student is walking into, taken from the blueprint where one
    # exists. Shown before they start, because a round with no preparation
    # time is a nasty surprise to discover from a running clock.
    what_to_expect: list[str] = []
    # Parts of the real format this simulation does not contain, and
    # where to practise them instead. Empty where nothing is missing.
    not_included: str = ""
    # Which configuration of the real format this imitates, where that needs
    # saying. Empty where it does not.
    provenance: str = ""
    # How this assessment scores. Returned so an admin can see what they
    # configured -- storing it without reading it back is how `scoring_weights`
    # spent months looking like a feature.
    scoring_weights: dict[str, float] = {}
    pass_threshold: float | None = None
    skill_thresholds: dict[str, float] = {}
    target_role: str = ""
    department: str = ""
    difficulty_band: str = ""
    sections: list[ProfileSectionOut] = []


class AttemptOut(BaseModel):
    id: str
    profile_id: str
    profile_name: str = ""
    attempt_number: int
    status: str
    mode: str
    is_baseline: bool
    overall_score: float | None = None
    started_at: datetime | None
    submitted_at: datetime | None
    scored_at: datetime | None
    ip_address: str = ""


class MasteryOut(BaseModel):
    skill: str
    mastery: float
    baseline: float | None
    last_change: float
    observations: int


# --------------------------------------------------------------------------
# Student
# --------------------------------------------------------------------------

class QuestOut(BaseModel):
    id: str
    kind: str
    title: str
    description: str
    target_skill: str
    progress: float
    target: float
    completed: bool
    bonus_xp: int
    for_date: date


class StreakOut(BaseModel):
    current_streak: int = 0
    best_streak: int = 0
    freezes_available: int = 0
    last_qualifying_day: date | None = None


class StudentHome(BaseModel):
    user: UserOut
    consent_given: bool
    baseline_done: bool
    total_xp: int
    level: int
    # Effort and mastery are reported separately and never mixed (GAM-03/23).
    gap_percent: float | None = None
    streak: StreakOut
    quest: QuestOut | None = None
    days_to_drive: int | None = None
    assigned_profiles: list[SimulationProfileOut] = []
    recent_attempts: list[AttemptOut] = []
    mastery: list[MasteryOut] = []


class ConsentRequest(BaseModel):
    scopes: list[str]
    notice_version: str = "1.0"
    notice_language: str = "en"


# --------------------------------------------------------------------------
# Trainer / tenant admin
# --------------------------------------------------------------------------

class CohortReadiness(BaseModel):
    cohort_id: str
    cohort_name: str
    total: int
    assessed: int
    placement_ready: int
    needs_training: int
    high_risk: int
    not_started: int
    average_overall: float | None = None
    days_to_drive: int | None = None


class StudentSummary(BaseModel):
    user: UserOut
    attempts: int
    last_attempt_at: datetime | None
    overall_score: float | None
    readiness: str
    days_since_activity: int | None
    flagged: bool = False


class TenantOverview(BaseModel):
    tenant_name: str
    tenant_slug: str
    seats_used: int
    seat_limit: int
    students: int
    cohorts: int
    attempts_total: int
    consent_pending: int


# --------------------------------------------------------------------------
# Platform
# --------------------------------------------------------------------------


class TenantBranding(BaseModel):
    """How a tenant wants to be seen by its own people.

    ``logo_url`` may be an absolute URL the customer hosts, or a relative
    ``/api/v1/platform/assets/...`` path for a file uploaded here. The client
    does not need to care which.
    """

    display_name: str = ""
    logo_url: str = ""
    primary_color: str = ""
    default_theme: str = ""
    support_email: str = ""


class TenantContact(BaseModel):
    """One named human. Kept as a list so a customer can have several."""

    role: str = Field(default="primary", max_length=40)
    name: str = Field(default="", max_length=120)
    email: str = Field(default="", max_length=200)
    phone: str = Field(default="", max_length=40)


class TenantProfile(BaseModel):
    """Everything about a customer that is paperwork rather than plumbing.

    All optional. A tenant can be created with a name and an admin and
    nothing else -- the rest gets filled in as sales learns it, which is the
    order it actually arrives in.
    """

    # Where they are.
    address_line1: str = Field(default="", max_length=200)
    address_line2: str = Field(default="", max_length=200)
    city: str = Field(default="", max_length=80)
    state: str = Field(default="", max_length=80)
    postal_code: str = Field(default="", max_length=20)
    country: str = Field(default="India", max_length=80)

    # How to reach them.
    website: str = Field(default="", max_length=200)
    phone: str = Field(default="", max_length=40)
    contacts: list[TenantContact] = []

    # What they are.
    affiliated_to: str = Field(default="", max_length=200)
    established_year: int | None = Field(default=None, ge=1800, le=2200)
    student_strength: int | None = Field(default=None, ge=0, le=10_000_000)
    # Courses, streams or departments -- free text, because the taxonomy
    # differs by institution and forcing ours on them loses information.
    courses: list[str] = []
    # Placement season, accreditation, anything else worth recording.
    accreditation: str = Field(default="", max_length=120)
    notes: str = Field(default="", max_length=2000)

    # Billing paperwork. India-specific and genuinely needed on an invoice.
    # (gst_number and billing_email removed — plans/subscriptions/billing removed)
    # Kept as comment for context; actual fields deleted.


class TenantOut(BaseModel):
    id: str
    name: str
    slug: str
    domain: str = ""
    tenant_type: str = "engineering_college"
    tenant_type_label: str = ""
    status: str
    seat_limit: int
    seats_used: int = 0
    region: str
    branding: TenantBranding = TenantBranding()
    profile: TenantProfile = TenantProfile()
    created_at: datetime
    temp_password: str = ""
    admin_email: str = ""


class ProviderOut(BaseModel):
    id: str
    capability: str
    provider_key: str
    name: str
    tier: int
    version: str
    entrypoint: str
    active: bool
    # Populated from the applicable ProviderConfig row.
    role: str = ""          # primary | fallback | shadow | unassigned
    mode: str = ""          # live | shadow | canary
    calls_24h: int = 0
    error_rate: float = 0.0
    p50_latency_ms: int = 0


class CapabilityOut(BaseModel):
    capability: str
    contract_version: str
    configured: bool
    mode: str = ""
    primary: str = ""
    fallback: str = ""
    shadow: str = ""
    timeout_ms: int = 0
    providers: list[ProviderOut] = []


class AuditOut(BaseModel):
    id: str
    actor_type: str
    actor_label: str
    tenant_id: str | None
    action: str
    entity: str
    entity_id: str
    at: datetime


class GamificationConfigOut(BaseModel):
    tenant_id: str | None
    xp_table: dict
    difficulty_multipliers: dict
    weakness_multiplier: float
    free_freezes_per_month: int
    quiz_xp_cap_percent: int
    leagues_enabled: bool
    max_engagement_notifications_per_day: int


class PlatformOverview(BaseModel):
    tenants_total: int
    tenants_active: int
    seats_sold: int
    providers_registered: int
    capabilities_configured: int
    capabilities_total: int
    audit_events_7d: int


# --------------------------------------------------------------------------
# Attempt lifecycle (M1)
# --------------------------------------------------------------------------

class StartAttemptRequest(BaseModel):
    profile_id: str
    # practice never counts against the plan allowance or the readiness view
    mode: str = "practice"
    # When starting a practice session from a result page: the assessment
    # attempt that prescribed it, so the loop stays anchored to it.
    source_attempt_id: str | None = None





class RunnerItem(BaseModel):
    """One item as the runner needs it — and no more than that.

    Read Aloud carries its text because the student is meant to see it.
    Repeat Sentence does not: the text arrives only when the prompt is played,
    and only once.
    """

    response_id: str
    position: int
    section_id: str
    section_title: str
    task_type: str
    instructions: str
    prep_seconds: int
    response_seconds: int
    prompt_plays_allowed: int
    prompt_text: str = ""
    has_prompt_audio: bool = False
    # The budget of the lettered section this item's sub-section belongs to,
    # in seconds (0 = none). The runner shows one clock per lettered section
    # and passes over the rest of the section when it runs out; it never
    # cuts into an item in progress. From the blueprint, not the row.
    section_budget_seconds: int = 0
    # Section behaviour, as data (app.formats.section_behaviour). All false
    # for an admin-authored profile, which is the engine's original flow.
    fixed_window: bool = False
    allow_skip: bool = False
    skip_prep: bool = False
    ack_gate: str = ""
    continuous_numbering: bool = False
    # Show this item's section instruction on the question screen itself
    # (Cognizant reference: a task line on every numbered question).
    show_instruction: bool = False
    # The server already holds this item's answer (a recording, a typed or
    # chosen answer, or a deliberate skip). The runner resumes at the first
    # item where this is false -- a reload used to restart at item 1 and
    # make the candidate redo everything (hardware UAT, D7).
    answered: bool = False
    # Which passage this item belongs to, for grouping a listening event. Empty
    # for everything that is not a grouped listening question. The runner plays
    # the audio once for the first item carrying a given ref and not again for
    # the others, so a four-passage / twelve-question section is heard four
    # times, not twelve. Opaque id only -- never the passage words.
    passage_ref: str = ""

    # -- how this item is answered -----------------------------------------
    #
    # speak | select | write. The runner dispatches on this, which is what
    # lets one attempt contain a speaking section and a listening section
    # without a second engine behind it.
    response_mode: str = "speak"
    skill: str = "speaking"

    # `select`: the passage to read or hear first, then the question.
    # Withheld for a listening item until the audio has played, the same rule
    # Repeat Sentence follows.
    stimulus_text: str = ""
    stimulus_title: str = ""
    # How long the stimulus stays on screen before it is taken away. Zero
    # means it stays. Only Passage Reconstruction sets it, and only because
    # losing the passage is the measurement rather than a UI flourish.
    stimulus_seconds: int = 0
    question: str = ""
    options: list[str] = []
    # The correct answer is deliberately absent. It arrives with the result.

    # `write`: what to write and what a competent answer must cover. The cue
    # words the scorer looks for are stripped -- handing them over would let a
    # candidate paste them in and score full marks on task response.
    scenario: str = ""
    key_points: list[str] = []
    min_words: int = 0


class RunnerPayload(BaseModel):
    attempt_id: str
    profile_id: str
    profile_name: str
    # Which test this is imitating. The runner used to know only the profile
    # name, so every format looked like the same generic screen once you were
    # inside it -- the whole point of practising a specific format is that it
    # should feel like that format while you sit it.
    style: str = "diagnostic"
    company: str = ""
    status: str
    mode: str
    is_baseline: bool
    items: list[RunnerItem]

    # -- the whole-sitting clock -------------------------------------------
    #
    # Null until the attempt has started: the clock starts when the
    # candidate is ready, not when they opened the page and went to find
    # headphones.
    #
    # `server_now` is sent alongside deliberately. A browser clock can be
    # wrong by minutes or stopped by a sleeping laptop, and a countdown that
    # trusted it would expire an attempt early or run past the end. The client
    # takes the difference once and counts down against its own monotonic
    # timer from there.
    deadline_at: datetime | None = None
    server_now: datetime | None = None
    seconds_remaining: int | None = None


class PromptResponse(BaseModel):
    """The prompt, served once. ``plays_remaining`` is the server's count."""

    text: str
    accent: str = "indian"
    audio_url: str | None = None
    plays_remaining: int


class WordTimingOut(BaseModel):
    word: str
    start_ms: int
    end_ms: int
    confidence: float = 1.0


class ResponseMetrics(BaseModel):
    response_id: str
    position: int
    task_type: str
    prompt_text: str = ""
    skipped: bool = False
    onset_ms: int | None = None
    speech_ms: int | None = None
    duration_ms: int | None = None
    words_per_minute: float | None = None
    articulation_rate: float | None = None
    pause_count: int | None = None
    longest_pause_ms: int | None = None
    quality: str = "good"
    scores: dict[str, float] = {}
    # The recording ended while speech was still going — the timer cut them
    # off. Distinguished from unclear speech because the fix is different.
    ended_mid_speech: bool = False
    # Why the recording stopped, as the client reported it: user_ended |
    # auto_advance | window_expired | cancelled | "" (unknown). Only
    # window_expired may be described as running out of time.
    ended_by: str = ""

    # Annotated listen-back (DIAG-02). Present only once a transcript exists —
    # at Tier 0 these stay empty rather than being faked from the reference.
    transcript: str = ""
    words: list[WordTimingOut] = []
    pauses: list[dict] = []
    disfluencies: list[dict] = []
    # What was measured against the item's reference text: a missed word, an
    # added one, a swap, or -- for Sentence Build -- the right words in the
    # wrong order. Empty for anything with no reference to compare against.
    word_errors: list[dict] = []
    # How clearly each word came out: [{word, score, posterior, start_ms}].
    # A different question from the one above, and it used to be served under
    # that one's name, which made every listen-back chip read "undefined".
    word_clarity: list[dict] = []
    # The rule matches behind a grammar score. Stored since M2, never sent
    # until the evidence panel needed it.
    grammar_errors: list[dict] = []
    accuracy: float | None = None
    # How much of what was asked for arrived, 0-1. None where the item never
    # said what a complete answer looks like -- which is not the same as zero,
    # and the evidence panel says so rather than drawing an empty bar.
    completeness: float | None = None
    has_audio: bool = False


# --------------------------------------------------------------------------
# Profile builder (tenant admin)
# --------------------------------------------------------------------------

# Every task type a section may use. The non-speaking ones were the missing
# half: a template could only ever be assembled from speaking modules, which
# is why no assessment has ever contained a Listening, Reading or Writing
# section even though all three work as practice.
#
# app.sections.SKILL_OF_TASK is the authority on what each one *is*; this set
# is only about what an admin is allowed to put in a template.
TASK_TYPES = {
    # Speaking.
    "read_aloud", "repeat_sentence", "short_answer", "sentence_build",
    "story_retell", "open_response",
    # Hear a gapped/flawed sentence, say the whole correct sentence aloud.
    "spoken_completion", "spoken_correction",
    # Spoken answers to something heard: what was understood, said out loud.
    "conversation_question", "passage_question",
    # Listening and reading: answered by choosing, not by speaking.
    "listening_comprehension", "reading_comprehension",
    # Which reply fits. Not comprehension -- every wrong option is correct
    # English, and what is measured is whether it lands.
    "response_selection",
    # What a word means in the sentence it is in, not in a dictionary.
    "vocabulary_in_context",
    # Heard once and typed back. Listening measured through writing.
    "dictation",
    # One word typed into a gap: recall rather than recognition.
    "sentence_completion",
    # A sentence and four rewrites: change the voice (active/passive), chosen.
    "voice_change",
    # Read a short passage, lose it, write it back.
    "passage_reconstruction", "email_writing",
    # Timed typing: speed and accuracy on a given text.
    "typing",
    # Read word lists aloud (Cognizant Q11-15): isolated words, word-clarity scoring.
    "read_words",
    # Kept for profiles authored before the names above existed.
    "mcq", "audio_comprehension",
}

PROFILE_STYLES = {"versant_style", "svar_style", "speechx_style",
                  # Not an imitation of anybody's test. Ours, four skills,
                  # workplace material, an hour long.
                  "professional",
                  "company_round", "diagnostic", "drill"}


class SectionSelection(BaseModel):
    """How a section narrows its bank and draws from it (Phase 6).

    Every field optional, and an empty object is the historical behaviour:
    every published item of the section's task type, sampled at random. That
    matters more than it sounds -- a filter that quietly narrowed an
    unconfigured pool would change the results of every existing assessment.
    """

    difficulty_min: float | None = Field(default=None, ge=-3, le=3)
    difficulty_max: float | None = Field(default=None, ge=-3, le=3)
    topics: list[str] = []
    roles: list[str] = []
    industries: list[str] = []
    languages: list[str] = []
    # A floor on how many eligible items must exist, not a cap on how many are
    # considered. A bank the size of the section serves the same test on every
    # retake, and the retake then measures memory.
    min_pool: int = Field(default=0, ge=0, le=500)
    # {"easy"|"medium"|"hard": share}. Shares are relative, so {"hard": 2,
    # "easy": 1} means two thirds hard.
    mix: dict[str, float] = {}

    @model_validator(mode="after")
    def usable(self):
        from app import selection

        if (self.difficulty_min is not None and self.difficulty_max is not None
                and self.difficulty_min > self.difficulty_max):
            raise ValueError("difficulty_min is above difficulty_max, so no "
                             "item can satisfy both")
        unknown = [i for i in self.industries if not selection.known_industry(i)]
        if unknown:
            raise ValueError(
                f"unknown industry {unknown}; known values are "
                f"{', '.join(selection.INDUSTRIES)}")
        bad_bands = [b for b in self.mix if b not in selection.BANDS]
        if bad_bands:
            raise ValueError(
                f"unknown difficulty band {bad_bands}; use "
                f"{', '.join(selection.BANDS)}")
        if self.mix and all(v <= 0 for v in self.mix.values()):
            raise ValueError("a difficulty mix needs at least one share above "
                             "zero")
        return self


class ProfileSectionRequest(BaseModel):
    """One section as the builder submits it. Position comes from the order."""

    title: str = Field(min_length=1, max_length=120)
    task_type: str
    selection: SectionSelection = SectionSelection()
    instructions: str = ""
    item_count: int = Field(default=5, ge=1, le=30)
    prep_seconds: int = Field(default=0, ge=0, le=300)
    # Zero means untimed, which is only meaningful for a written or
    # multiple-choice section -- see the validator below. Five seconds is the
    # floor for anything spoken.
    response_seconds: int = Field(default=30, ge=0, le=600)
    prompt_plays_allowed: int = Field(default=0, ge=0, le=3)
    allow_replay: bool = False
    # This section's share of its skill. Relative, not a percentage: two
    # speaking sections at 1.0 and 3.0 split their skill one part to three.
    #
    # Bounded rather than open. Zero is allowed and means "run it but do not
    # count it", which is a real thing an admin wants for a warm-up. Ten is
    # the ceiling because past that the other sections have stopped mattering
    # and what the admin actually wants is to remove them.
    weight: float = Field(default=1.0, ge=0.0, le=10.0)

    @field_validator("task_type")
    @classmethod
    def known_task_type(cls, v: str) -> str:
        if v not in TASK_TYPES:
            raise ValueError(f"unknown task type {v!r}")
        return v

    @model_validator(mode="after")
    def timing_suits_the_mode(self):
        """A spoken answer needs a clock; a written or chosen one may not.

        `response_seconds` was floored at five for every section, which is
        right for speaking -- five seconds is already too short to say
        anything -- and wrong for a reading comprehension question, where
        untimed is a legitimate and common choice. The floor now depends on
        how the section is answered rather than applying one rule to three
        different kinds of task.
        """
        from app.sections import mode_of

        if mode_of(self.task_type) == "speak" and self.response_seconds < 5:
            raise ValueError(
                f"A spoken section needs at least 5 seconds to answer in; "
                f"{self.task_type} was given {self.response_seconds}.")
        return self

    @model_validator(mode="after")
    def filters_suit_the_bank(self):
        """A filter the section's own bank cannot honour is refused here.

        Only ``TaskItem`` carries topic, role, industry and language. A
        listening section filtered by industry would match nothing and serve
        an empty section, and the admin would have no idea why. Refusing at
        build time is the only place this is cheap.
        """
        from app import selection
        from app.sections import source_of

        kind, _key = source_of(self.task_type)
        asked = selection.from_dict(self.selection.model_dump())
        unsupported = asked.unsupported_for(kind)
        if unsupported:
            raise ValueError(
                f"{self.task_type} draws on the {kind} bank, which carries no "
                f"{', '.join(unsupported)}. Remove "
                f"{'those filters' if len(unsupported) > 1 else 'that filter'} "
                f"or choose a task type whose items are classified.")
        return self


class ProfileStatusRequest(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def known_status(cls, v: str) -> str:
        if v not in {"draft", "published", "retired"}:
            raise ValueError(f"unknown status {v!r}")
        return v


class ProfileRequest(BaseModel):
    """Create or replace a profile. Sections are sent whole, never patched.

    Sending the section list entire is deliberate: reordering, removing and
    editing in one request removes the window where a profile is half-updated
    and a student could start it.
    """

    name: str = Field(min_length=1, max_length=160)
    style: str = "company_round"
    company: str = Field(default="", max_length=80)
    description: str = ""
    estimated_minutes: int = Field(default=15, ge=1, le=180)
    sections: list[ProfileSectionRequest] = []

    # -- how this assessment is scored -------------------------------------
    #
    # `scoring_weights` was a column nothing could write. An admin could not
    # say that a customer-support round cares more about intelligibility than
    # about grammatical range, which is the main thing a company round is for.
    #
    # Empty means "use the engine's own weights", which is what every existing
    # profile does and what practice should keep doing.
    scoring_weights: dict[str, float] = {}
    # Overall, on the internal 20-80 scale. None means this assessment does
    # not pass or fail anybody -- right for practice, wrong for a hiring round.
    pass_threshold: float | None = Field(default=None, ge=20, le=80)
    # {dimension: floor}. Failing any floor fails the assessment even when the
    # weighted overall clears the bar.
    skill_thresholds: dict[str, float] = {}

    # -- who it is for. Classification only; nothing scores differently. ----
    target_role: str = Field(default="", max_length=80)
    department: str = Field(default="", max_length=80)
    # CEFR label for the content, never a claim about the candidate.
    difficulty_band: str = Field(default="", max_length=10)

    @field_validator("scoring_weights")
    @classmethod
    def usable_weights(cls, v: dict) -> dict:
        from app.weighting import weights_are_valid
        ok, why = weights_are_valid(v)
        if not ok:
            raise ValueError(why)
        return v

    @field_validator("skill_thresholds")
    @classmethod
    def usable_thresholds(cls, v: dict) -> dict:
        from app.weighting import ENGINE_WEIGHTS
        for dimension, floor in (v or {}).items():
            if dimension not in ENGINE_WEIGHTS:
                raise ValueError(
                    f"Not a measured dimension: {dimension}. "
                    f"Available: {', '.join(sorted(ENGINE_WEIGHTS))}.")
            if not 20 <= float(floor) <= 80:
                raise ValueError(
                    f"A floor is on the same 20-80 scale as the scores. "
                    f"{dimension} was given {floor}.")
        return v

    @field_validator("difficulty_band")
    @classmethod
    def known_band(cls, v: str) -> str:
        allowed = {"", "A1", "A2", "B1", "B2", "C1", "C2"}
        if v.upper() not in allowed:
            raise ValueError(f"CEFR band must be one of {sorted(allowed - {''})}")
        return v.upper()

    @field_validator("style")
    @classmethod
    def known_style(cls, v: str) -> str:
        if v not in PROFILE_STYLES:
            raise ValueError(f"unknown style {v!r}")
        return v


class NarrationOut(BaseModel):
    """The AI explanation, and its job state, for the result page.

    status is always present; the content fields are populated only when
    status is "ready". The frontend shows a "being prepared" card for
    pending/processing, a "couldn't generate" note for failed, and the real
    explanation for ready — it never renders deterministic text as if the AI
    wrote it.
    """
    # pending | processing | retry_pending | ready | failed
    status: str
    headline: str = ""
    summary: str = ""
    primary_focus: str = ""
    practice_action: str = ""
    caveats: list[str] = []
    # Provenance, so a screenshot of AI text is always identifiable as such.
    model_version: str = ""
    generated_at: datetime | None = None


class HighlightOut(BaseModel):
    dimension: str
    score: float
    # Distance from this student's own average, signed. Compared against
    # themselves rather than a cohort: this product has no population norms,
    # and "better than your own average" needs none.
    delta: float
    means: str = ""


class RecommendationOut(BaseModel):
    dimension: str
    current: float
    target: float
    # What the overall would become if this matched their own best. Computed
    # from the weights, never chosen because it reads well.
    predicted_gain: float
    advice: str


class ResultPriorityOut(BaseModel):
    """One thing to practise next, in the student's language."""
    dimension: str
    score: float
    responses: int
    # Legacy surface hint; the profile below is what the button starts.
    practice: str
    # The targeted practice session for this weakness: a real, runnable
    # profile (app/formats.PRACTICE_BLUEPRINTS), resolved for this tenant.
    practice_code: str = ""
    practice_profile_id: str = ""
    practice_name: str = ""
    practice_minutes: int = 0
    # "needs_most" | "needs_work" -- the verdict leads, the number supports.
    # Only the primary diagnosis's dimension is ever "needs_most".
    verdict: str = "needs_work"
    evidence: str
    # What to do about it this week.
    advice: str = ""


class PrimaryDiagnosisOut(BaseModel):
    """The one authoritative answer to "what should I work on first?"

    Built by app/diagnosis.py from measured evidence and consumed by every
    surface that names a weakness: the summary sentence, the result card,
    the first practice button, the practice result and the AI narration.
    None of them may choose differently; tests hold them to it.

    status: identified | tied | level | insufficient | none. Only
    "identified" carries a dimension and a practice to start. The rest are
    honest "nothing clearly stands out yet" outcomes, with the reason.
    """
    status: str
    headline: str
    reason: str
    evidence: str = ""
    dimension: str = ""
    label: str = ""
    score: float | None = None
    responses: int = 0
    scale_max: float = 80.0
    confidence: str = ""
    # The tied group (status "tied") or the eligible set, weakest first.
    candidates: list[dict] = []
    # Lower-scoring dimensions that could not be the primary, with why.
    excluded: list[dict] = []
    # The targeted practice for the primary, resolved for this tenant.
    # Empty unless status is "identified" -- there is never a button for a
    # diagnosis that was not made.
    practice_code: str = ""
    practice_profile_id: str = ""
    practice_name: str = ""
    practice_minutes: int = 0
    advice: str = ""
    # The scored attempt whose measurements produced this diagnosis. On an
    # assessment result it is that attempt; on a practice result it is the
    # assessment that prescribed the practice.
    source_attempt_id: str = ""
    source_profile_id: str = ""
    source_profile_name: str = ""


class PracticeOutcomeOut(BaseModel):
    """What a finished practice session says about itself.

    Practice improvement and assessment improvement are different claims
    (different items, different length); this reports the practice honestly
    and points back at the assessment for the proof.
    """
    dimension: str
    label: str
    practice_score: float | None = None
    # The same dimension on the student's most recent scored *assessment*
    # (never another practice) -- the before to this practice's after.
    assessment_score: float | None = None
    assessment_profile_id: str = ""
    assessment_profile_name: str = ""
    # The exact assessment attempt this comparison is against.
    source_attempt_id: str = ""
    # True when the practice was started from that assessment's result page
    # (the link is stored at start). False means no link exists and the
    # comparison is against the student's most recent assessment -- which
    # is then said plainly, never presented as "the one that prescribed it".
    source_linked: bool = False
    # What the prescribing assessment's primary diagnosis was: the dimension
    # it identified ("" when it identified none) and whether this practice
    # trained that dimension or one of the secondary priorities.
    prescribed_status: str = ""
    prescribed_dimension: str = ""
    trained_primary: bool = False
    change: float | None = None
    # How many practice answers measured the trained skill this session.
    practice_responses: int = 0
    # higher | level | lower | insufficient. A product rule, not statistics:
    # small movements between different items are reported as "level", and a
    # thin measurement refuses to produce a verdict at all.
    verdict: str = "insufficient"


class PreviousAttemptOut(BaseModel):
    """The last scored sitting of this same assessment, for before/after."""
    attempt_id: str
    attempt_number: int
    overall: float | None = None
    # current minus previous, on the internal scale. None when either side
    # has no overall -- an absent number, never a pretended zero.
    delta: float | None = None


class AttemptResult(BaseModel):
    attempt_id: str
    # Which assessment this was -- what "take this test again" starts.
    profile_id: str = ""
    profile_name: str
    # The format family, so the result page can say whose names the
    # sub-scores borrow ("not an SVAR result") without guessing from the name.
    profile_style: str = ""
    status: str
    mode: str
    is_baseline: bool
    attempt_number: int
    overall: float | None
    band: str = ""
    scale_min: float = 20
    scale_max: float = 80
    dimensions: dict[str, float] = {}
    confidence: dict[str, float] = {}
    # Dimension → why it is not scored yet. Shown, not hidden.
    unscored: dict[str, str] = {}
    # Present only where the profile configured its own weights or a pass
    # mark. Absent for practice, which should not pass or fail anybody.
    weighted: WeightedScoreOut | None = None
    # Present only when the attempt contained a Story Retell section.
    retell: RetellBreakdownOut | None = None
    # Stored section results, and the four-skill rollup built from them.
    sections: list[SectionResultOut] = []
    skills: list[SkillScoreOut] = []
    ip_address: str = ""
    started_at: datetime | None = None
    submitted_at: datetime | None = None
    # The frozen engine's weakest-composite-dimension figure. Retained as
    # engine output (SCORING_PATH); NOT a diagnosis surface -- the page does
    # not render it, and narration is not given it. See primary_diagnosis.
    biggest_lever: dict | None = None
    # The single source of truth for "what should I work on first?".
    primary_diagnosis: PrimaryDiagnosisOut | None = None
    environment_note: str = ""
    # Company rounds report an outcome rather than a scale, because "would I
    # have got through" is the only thing the student is about to find out.
    # None for every other style, and always carries its own hedge — see
    # app/formats.py. Never present without an overall behind it.
    verdict: dict | None = None
    # Vendor-style simulations restate the composite on the scale that
    # format publishes, using that format's sub-score names. Estimated,
    # never concordance-validated, and labelled so wherever shown.
    presentation: dict | None = None

    # The improvement loop. `previous` is the last scored sitting of this
    # same assessment (before/after); `priorities` are at most three things
    # to practise next, each pointing at a surface that actually runs.
    previous: PreviousAttemptOut | None = None
    priorities: list[ResultPriorityOut] = []
    # Present only on a practice (drill-style) attempt: what was practised
    # and how it compares with the last real assessment.
    practice: PracticeOutcomeOut | None = None

    # Whether any of this has been checked against human listeners. False
    # everywhere until a validation study produces a fit that clears the
    # gates — the report leads with this rather than burying it.
    calibrated: bool = False
    calibration_note: str = ""
    # What each measure does and does not cover, in the student's words.
    dimension_notes: dict[str, str] = {}
    # Which dimensions the overall was composed from. Two attempts built on
    # different bases are not comparable, and this is what makes that visible.
    overall_basis: list[str] = []
    # Where this score sits on the CEFR ladder, with the caveat attached to
    # the payload rather than left to each client to remember. A band shipped
    # without its own disclaimer becomes a certificate the moment somebody
    # screenshots it.
    cefr_level: str = ""
    cefr_descriptor: str = ""
    cefr_caveat: str = ""
    responses: list[ResponseMetrics] = []
    scored_at: datetime | None = None
    scoring_ms: int | None = None
    # The AI explanation of this result. None only when narration is disabled
    # or the student has not consented — never a hidden dependency of the
    # score, which is complete with or without this field.
    narration: NarrationOut | None = None

    # -- reporting (Phase 8) ----------------------------------------------
    #
    # All derived from measurements already above, above the frozen scoring
    # path. Nothing here can move a number.
    #
    # A plain sentence before any chart -- the Phase 0 rule. A student
    # opening their result meets language, not a radar plot.
    summary: str = ""
    # What they are ahead on, not only what they are behind on. The report
    # gave one weakness and nothing else, which teaches a student that
    # practising produces criticism.
    strengths: list[HighlightOut] = []
    weaknesses: list[HighlightOut] = []
    # A set, ordered by computed gain, rather than a single lever. Two or
    # three ranked actions is a plan; one is an instruction.
    recommendations: list[RecommendationOut] = []
    # Dimension -> the responses that produced it, with the stored
    # measurements behind each. Absent for a dimension nothing produced.
    evidence: dict[str, list[dict]] = {}


# --------------------------------------------------------------------------
# Tenant administration (M3)
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# External candidates (Phase 9)
# --------------------------------------------------------------------------

class InvitationRequest(BaseModel):
    profile_id: str
    invited_name: str = Field(default="", max_length=120)
    invited_email: str = Field(default="", max_length=200)
    # The employer's own reference: a requisition number, a role title.
    reference: str = Field(default="", max_length=120)
    # An invitation that works forever is a credential nobody remembers
    # issuing.
    valid_days: int | None = Field(default=None, ge=1, le=90)


class InvitationOut(BaseModel):
    id: str
    # Returned to the admin who issued it, so they can send the link. Never
    # returned to anybody else, and never listed publicly.
    token: str
    profile_id: str
    profile_name: str = ""
    invited_name: str = ""
    invited_email: str = ""
    reference: str = ""
    status: str
    expires_at: datetime | None = None
    redeemed_at: datetime | None = None
    attempt_id: str | None = None
    created_at: datetime | None = None


class InvitePreview(BaseModel):
    """What a candidate sees before deciding to start. Consumes nothing."""

    ok: bool
    # Set when ok is false: unknown | expired | used | withdrawn. Named rather
    # than collapsed into one "invalid", because each has a different next
    # step for the person holding the link.
    reason: str = ""
    message: str = ""
    tenant_name: str = ""
    profile_name: str = ""
    description: str = ""
    estimated_minutes: int = 0
    camera_check: bool = False
    practice_item: bool = False
    invited_name: str = ""


class RedeemRequest(BaseModel):
    """The only things asked of a candidate.

    Name, because a result has to belong to somebody. Email, optionally,
    because that is how they get sent it. There is deliberately no field here
    for date of birth, gender, address or anything else an employer might be
    tempted to collect through a testing tool.
    """

    full_name: str = Field(min_length=1, max_length=120)
    email: str = Field(default="", max_length=200)


class CandidateResume(BaseModel):
    """Where an invited candidate left off.

    Exists because a candidate who refreshed had nowhere to go. The invitation
    is single-use by design and the page recomputed its refusal purely from
    the invitation row, so a reload after claiming showed "this link has
    already been used -- somebody else has your link" to the person who had
    used it thirty seconds earlier. They still held a valid session and every
    route refused them.
    """

    # Empty when the caller has no invitation -- an enrolled student, say.
    profile_id: str = ""
    profile_name: str = ""
    # What the resumed screen has to say truthfully. The first version of the
    # resume path let the page invent a preview to render, and it rendered
    # "About 0 minutes, in one sitting" with no institution named -- fabricated
    # values on the last screen before somebody agrees to be recorded.
    profile_description: str = ""
    estimated_minutes: int = 0
    tenant_name: str = ""
    # Null until they start. The page sends them straight back to it.
    attempt_id: str | None = None
    attempt_status: str = ""
    consent_given: bool = False


class CandidateSession(BaseModel):
    token: str
    candidate_id: str
    full_name: str
    profile_id: str
    tenant_name: str = ""


class ImportProblemOut(BaseModel):
    line: int
    column: str
    message: str


class ImportPreview(BaseModel):
    ok: bool
    total: int
    creating: int
    updating: int
    seats_after: int
    seat_limit: int
    over_seat_limit: bool
    problems: list[ImportProblemOut] = []
    sample: list[dict] = []


class ImportRequest(BaseModel):
    # Pasted or uploaded CSV text. Kept as text rather than a file part so the
    # same endpoint serves a paste box and an upload.
    csv_text: str
    create_missing_cohorts: bool = True


class ImportResult(BaseModel):
    created: int
    updated: int
    cohorts_created: list[str] = []
    # Only for accounts created in this run, and only once.
    temporary_passwords: dict[str, str] = {}


class CreateUserRequest(BaseModel):
    email: EmailStr
    full_name: str
    role: str = "student"
    roll_number: str = ""
    branch: str = ""
    year_of_study: int | None = None
    l1_language: str = ""
    cohort_id: str | None = None


class UpdateUserRequest(BaseModel):
    full_name: str | None = None
    active: bool | None = None
    role: str | None = None
    branch: str | None = None
    l1_language: str | None = None


class CohortRequest(BaseModel):
    name: str
    branch: str = ""
    year_of_study: int | None = None
    section: str = ""
    drive_start: datetime | None = None
    drive_end: datetime | None = None


class CohortMembersRequest(BaseModel):
    add: list[str] = []
    remove: list[str] = []


class AssignmentRequest(BaseModel):
    cohort_id: str
    profile_id: str
    mandatory: bool = True
    opens_at: datetime | None = None
    due_at: datetime | None = None
    max_attempts: int = 3


class AssignmentOut(BaseModel):
    id: str
    cohort_id: str
    cohort_name: str
    profile_id: str
    profile_name: str
    mandatory: bool
    opens_at: datetime | None
    due_at: datetime | None
    max_attempts: int
    completed: int = 0
    total: int = 0


class SeatUsage(BaseModel):
    used: int
    limit: int
    students: int
    admins: int
    remaining: int


# --------------------------------------------------------------------------
# Gamification (M4)
# --------------------------------------------------------------------------

class BadgeOut(BaseModel):
    code: str
    name: str
    description: str
    category: str
    earned_at: datetime | None = None


class LedgerEntry(BaseModel):
    activity: str
    base_xp: int
    difficulty_multiplier: float
    weakness_multiplier: float
    awarded_xp: int
    # Set when a cap reduced the award. Shown, not hidden — a student who
    # earned less than the arithmetic suggests is owed the reason.
    cap_applied: str = ""
    target_skill: str = ""
    at: datetime


class SeasonWeek(BaseModel):
    week: int
    theme: str
    target_skill: str
    minutes_target: int


class SeasonOut(BaseModel):
    starts_on: date
    ends_on: date
    drive_date: datetime | None
    days_remaining: int | None
    # False means we are showing a rolling default, not a date anyone set.
    is_real_drive_date: bool
    daily_minutes_target: int
    weeks: list[SeasonWeek] = []
    replans: int = 0


class AnswerSubmission(BaseModel):
    """A chosen or written answer. One shape for both non-speaking modes."""
    # select
    selected_index: int | None = None
    # write
    text: str = ""
    # When the candidate set the answer down, as opposed to when this request
    # reached us. The two differ whenever a delivery failed and the browser
    # retried from its queue, and the difference is what lets a late arrival
    # be told apart from a late answer. Absent on a first attempt, where the
    # two are the same moment anyway.
    composed_at: datetime | None = None


class SectionResultOut(BaseModel):
    section_id: str
    position: int
    title: str
    task_type: str
    # speaking | listening | reading | writing
    skill: str
    score: float | None = None
    dimensions: dict[str, float] = {}
    # How much of the section actually scored. A section where one of six
    # responses produced anything is not a firm reading.
    confidence: float | None = None
    # What this section counted for within its skill. Returned because a
    # weighted number nobody can see the weights behind is not explainable:
    # a candidate who did badly on a warm-up and well on the real section
    # deserves to see why the skill score followed the second one.
    weight: float = 1.0
    items_total: int = 0
    items_answered: int = 0
    unscored_reason: str = ""


class SkillScoreOut(BaseModel):
    """One of the four skills, rolled up from its sections.

    A skill with no section in this assessment is absent from the list
    entirely, never present with a zero.
    """
    skill: str
    score: float | None = None
    section_count: int = 0
    unscored_sections: list[str] = []
    note: str = ""


class RetellAxisOut(BaseModel):
    label: str
    score: float | None = None
    from_dimensions: list[str] = []
    note: str = ""


class RetellBreakdownOut(BaseModel):
    """Two axes, never averaged. See app/retell.py for why."""
    content: RetellAxisOut
    language: RetellAxisOut
    parts_measured: dict[str, bool] = {}
    note: str = ""


class ThresholdCheckOut(BaseModel):
    dimension: str
    floor: float
    actual: float | None = None
    # None when the dimension was never measured. Not a failure.
    met: bool | None = None


class WeightedScoreOut(BaseModel):
    """What this assessment's own weights make of the same measurements.

    Shown *beside* the engine composite, never instead of it. Replacing it
    would make every assessment incomparable with every other; omitting this
    would make a configured weight set a lie.
    """
    score: float | None = None
    weights: dict[str, float] = {}
    using_engine_default: bool = True
    # Dimensions the profile weighted that this attempt never produced.
    unmeasured: list[str] = []
    thresholds: list[ThresholdCheckOut] = []
    passed: bool | None = None
    why: str = ""





class WritingPromptOut(BaseModel):
    id: str
    title: str
    kind: str
    scenario: str
    prompt: str
    min_words: int
    suggested_minutes: int
    # Shown deliberately: this is practice, and knowing what a competent
    # answer must cover teaches more than guessing at it.
    key_points: list[str] = []
    best_score: float | None = None


class WritingSubmission(BaseModel):
    text: str
    minutes_spent: int = 0


class WritingMeasureOut(BaseModel):
    name: str
    score: float
    confidence: float
    # What was counted, so the number can be disagreed with.
    basis: str
    detail: dict = {}


class WritingResult(BaseModel):
    submission_id: str
    title: str
    word_count: int
    overall: float | None = None
    too_short: bool = False
    notes: list[str] = []
    measures: list[WritingMeasureOut] = []
    text: str = ""
    xp_awarded: int = 0
    day_counted_now: bool = False
    streak_current: int = 0


class ReadingPassageOut(BaseModel):
    id: str
    title: str
    kind: str
    word_count: int
    question_count: int
    best_score: float | None = None
    # body is absent on purpose: it is the thing being timed.


class ReadingStart(BaseModel):
    attempt_id: str
    passage_id: str
    title: str
    kind: str
    body: str
    word_count: int
    question_count: int


class ReadingQuestionOut(BaseModel):
    id: str
    stem: str
    options: list[str]


class ReadingAnswer(BaseModel):
    item_id: str
    selected_index: int | None = None


class ReadingSubmission(BaseModel):
    answers: list[ReadingAnswer] = []
    # Milliseconds the passage was on screen, timed by the client.
    read_ms: int = 0


class ReadingResultItem(BaseModel):
    item_id: str
    stem: str
    options: list[str]
    selected_index: int | None
    correct_index: int
    is_correct: bool
    explanation: str


class ReadingResult(BaseModel):
    attempt_id: str
    title: str
    correct: int
    total: int
    score: float
    band: str
    # Reported beside comprehension and never blended into it.
    words_per_minute: int | None = None
    word_count: int = 0
    rate_note: str = ""
    body: str = ""
    items: list[ReadingResultItem] = []
    xp_awarded: int = 0
    day_counted_now: bool = False
    streak_current: int = 0


class ListeningPassageOut(BaseModel):
    id: str
    title: str
    kind: str
    approx_seconds: int
    plays_allowed: int
    question_count: int
    best_score: float | None = None
    # False means the browser will speak it. Surfaced so the UI can say so.
    has_recording: bool = False


class ListeningStart(BaseModel):
    attempt_id: str
    passage_id: str
    title: str
    kind: str
    # The words to be spoken. Sent because there is no recording yet; see the
    # disclosure on the start endpoint.
    transcript: str
    accent: str
    plays_allowed: int
    question_count: int
    audio_key: str = ""


class ListeningQuestionOut(BaseModel):
    id: str
    stem: str
    options: list[str]
    # correct_index is deliberately absent until the attempt is submitted.


class ListeningAnswer(BaseModel):
    item_id: str
    selected_index: int | None = None


class ListeningSubmission(BaseModel):
    answers: list[ListeningAnswer] = []
    plays_used: int = 1


class ListeningResultItem(BaseModel):
    item_id: str
    stem: str
    options: list[str]
    selected_index: int | None
    correct_index: int
    is_correct: bool
    explanation: str


class ListeningResult(BaseModel):
    attempt_id: str
    title: str
    correct: int
    total: int
    score: float
    band: str
    # Released only after submission: before that it is the answer sheet.
    transcript: str
    items: list[ListeningResultItem] = []
    xp_awarded: int = 0
    day_counted_now: bool = False
    streak_current: int = 0


class SkillModuleOut(BaseModel):
    """One of the four language skills, with what this build can really do.

    `status` is computed from the content in the database rather than stored,
    so a module cannot claim to be finished because someone forgot to change
    a flag.
    """
    key: str
    label: str
    status: str          # live | partial | planned
    summary: str
    measures: list[str] = []
    item_count: int = 0
    href: str = ""
    gap: str = ""
    mastery: float | None = None
    mastery_basis: str = ""


class SkillsOverview(BaseModel):
    modules: list[SkillModuleOut]
    # Said once, at the top, instead of implied by four separate cards.
    headline: str


class GameState(BaseModel):
    level: int
    total_xp: int
    xp_into_level: int
    xp_per_level: int
    gap_percent: float | None
    gap_at_baseline: float | None
    streak: StreakOut
    quest: QuestOut
    badges: list[BadgeOut] = []
    season: SeasonOut


# --------------------------------------------------------------------------
# Practice: quiz, drills, mistake bank (M5)
# --------------------------------------------------------------------------

class QuizItemOut(BaseModel):
    id: str
    category: str
    stem: str
    options: list[str]
    seconds_allowed: int
    # True when this item is resurfacing from the mistake bank.
    is_review: bool = False
    # The correct answer is deliberately absent. It arrives with the result.


class QuizAnswer(BaseModel):
    item_id: str
    selected_index: int | None = None
    seconds_taken: float | None = None


class QuizSubmission(BaseModel):
    answers: list[QuizAnswer]
    session_id: str = ""


class QuizResultItem(BaseModel):
    item_id: str
    stem: str
    options: list[str]
    selected_index: int | None
    correct_index: int
    is_correct: bool
    explanation: str
    category: str


class QuizResult(BaseModel):
    total: int
    correct: int
    accuracy: float
    xp_awarded: int
    xp_capped: bool = False
    cap_note: str = ""
    quest_progress: float = 0
    quest_target: float = 0
    quest_completed: bool = False
    items: list[QuizResultItem] = []


class MistakeOut(BaseModel):
    id: str
    skill: str
    stem: str
    category: str
    times_wrong: int
    times_right_since: int
    interval_days: int
    due_at: datetime
    due_now: bool


class DrillOut(BaseModel):
    id: str
    target_skill: str
    status: str
    item_count: int
    items_completed: int
    mastery_before: float | None
    mastery_after: float | None
    created_at: datetime
    # Evidence from the student's own last recording, not a generic tip.
    why: str = ""


class DrillCompletion(DrillOut):
    """A finished drill, with what finishing it actually earned.

    Completing a drill used to return the drill row and nothing else, so the
    one action the daily quest is built around produced no visible reward at
    all -- the XP, the quest progress and the streak all moved on the server
    and the student saw a table refresh. Sending the consequences back with
    the action is what makes the loop legible.
    """
    xp_awarded: int = 0
    quest_progress: float = 0.0
    quest_target: float = 0.0
    quest_completed: bool = False
    # The streak *after* this drill, and whether this is the action that
    # counted the day -- the difference between "you have a 5-day streak" and
    # "you just made it 5".
    streak_current: int = 0
    day_counted_now: bool = False
    # Milestones crossed by this action, so the celebration is specific.
    milestones: list[int] = []


# --------------------------------------------------------------------------
# Platform writes (M6)
# --------------------------------------------------------------------------

class ProviderRegisterRequest(BaseModel):
    """Register an implementation of a capability.

    Adding a provider is a row, not a deploy (ENG-17) — but the entrypoint has
    to name something importable, so the endpoint checks before storing.
    """

    capability: str
    provider_key: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=120)
    tier: int = Field(default=0, ge=0, le=2)
    version: str = Field(default="0.1.0", max_length=30)
    entrypoint: str = Field(min_length=1, max_length=200)
    active: bool = True
    # Describes the shape of this provider's own configuration; stored as
    # ``config_schema`` on the registry row.
    config: dict | None = None


class ProviderUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    tier: int | None = Field(default=None, ge=0, le=2)
    version: str | None = Field(default=None, max_length=30)
    entrypoint: str | None = Field(default=None, min_length=1, max_length=200)
    active: bool | None = None
    config: dict | None = None


class CapabilityConfigRequest(BaseModel):
    primary_provider_id: str
    fallback_provider_id: str | None = None
    shadow_provider_id: str | None = None
    mode: str = "live"
    canary_percent: int = 0
    timeout_ms: int = 8000
    # Null means the global default; a value scopes the change to one tenant.
    tenant_id: str | None = None


class TenantCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str
    domain: str = ""
    tenant_type: str = "engineering_college"
    seat_limit: int = Field(default=100, ge=1, le=1_000_000)
    status: str = "trial"
    admin_email: EmailStr
    admin_name: str
    branding: TenantBranding | None = None
    profile: TenantProfile | None = None
    region: str = ""


class TenantUpdateRequest(BaseModel):
    """Every field optional; only what is sent is changed.

    ``name`` and ``tenant_type`` are editable, ``slug`` is not: it is part of
    the schema name and of every stored recording key, so renaming it would
    strand both.
    """

    name: str | None = Field(default=None, min_length=1, max_length=200)
    tenant_type: str | None = None
    status: str | None = None
    seat_limit: int | None = Field(default=None, ge=1, le=1_000_000)
    region: str | None = None
    branding: TenantBranding | None = None
    profile: TenantProfile | None = None
    season_start: datetime | None = None
    season_end: datetime | None = None


class TenantTypeOut(BaseModel):
    key: str
    label: str



class LogoByUrlRequest(BaseModel):
    url: str = Field(min_length=1, max_length=500)


class GamificationConfigRequest(BaseModel):
    tenant_id: str | None = None
    xp_table: dict | None = None
    difficulty_multipliers: dict | None = None
    weakness_multiplier: float = 1.5
    free_freezes_per_month: int = 2
    quiz_xp_cap_percent: int = 40
    leagues_enabled: bool = True
    max_engagement_notifications_per_day: int = 1


# --------------------------------------------------------------------------
# Exam Reviews
# --------------------------------------------------------------------------

class ReviewRequest(BaseModel):
    rating: int = Field(ge=1, le=5)
    difficulty: str = Field(default="just_right")
    comment: str = Field(default="", max_length=2000)


class ReviewOut(BaseModel):
    id: str
    attempt_id: str
    user_id: str
    user_name: str = ""
    user_email: str = ""
    profile_name: str = ""
    rating: int
    difficulty: str
    comment: str
    created_at: datetime | None = None

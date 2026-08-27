"use client";
// =============================================================================
// CommunicationIQ API client — the only file that knows the backend exists.
// Screens import typed functions from here and never construct a URL, so the
// day the API moves or a field is renamed there is exactly one file to change.
// =============================================================================

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8010/api/v1";

const TOKEN_KEY = "commiq.token";

export function getToken(): string | null {
  return typeof window === "undefined" ? null : localStorage.getItem(TOKEN_KEY);
}
export function setToken(t: string | null) {
  if (typeof window === "undefined") return;
  if (t === null) localStorage.removeItem(TOKEN_KEY);
  else localStorage.setItem(TOKEN_KEY, t);
}
export function isSignedIn(): boolean {
  return getToken() !== null;
}

export class ApiError extends Error {
  constructor(public status: number, public detail: string) {
    super(detail);
  }
}

/** Drop the dead session and return to sign-in, once.
 *
 *  Latched because a dashboard fires several requests at a time and every one
 *  of them will 401 together; without this they race to navigate.
 *
 *  `forToken` is the token the failing request was actually sent with. A 401
 *  from a request issued *before* the user signed in would otherwise land
 *  afterwards and wipe the session that replaced it — sign in, get bounced
 *  straight back to the login page, with nothing in the console but a 401 for
 *  a token that was already dead.
 */
let expiring = false;
export function sessionExpired(forToken?: string | null) {
  if (typeof window === "undefined") return;
  if (forToken !== undefined && forToken !== getToken()) return;
  if (expiring) return;
  if (window.location.pathname === "/login") return;
  expiring = true;
  setToken(null);
  const back = window.location.pathname + window.location.search;
  window.location.replace(`/login?expired=1&next=${encodeURIComponent(back)}`);
}

/** Called on a successful sign-in so a later genuine expiry can redirect again. */
export function resetSessionExpiry() {
  expiring = false;
}

/** Multipart POST.
 *
 *  Separate from `request` because that helper sets Content-Type: application
 *  /json unconditionally. On a FormData body that is actively wrong — the
 *  browser has to set the header itself so it can include the multipart
 *  boundary, and overriding it makes the server see a body it cannot parse.
 */
const DEFAULT_TIMEOUT_MS = 12_000;

function withTimeout<T>(promise: Promise<T>, ms = DEFAULT_TIMEOUT_MS): Promise<T> {
  if (typeof window === "undefined") return promise;
  let timer: ReturnType<typeof setTimeout>;
  const timeout = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new ApiError(504, "Request timed out")), ms);
  });
  return Promise.race([promise.finally(() => clearTimeout(timer)), timeout]);
}

async function upload<T>(path: string, form: FormData): Promise<T> {
  const token = getToken();
  const controller = typeof window !== "undefined" ? new AbortController() : null;
  const id = setTimeout(() => controller?.abort(), DEFAULT_TIMEOUT_MS);
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      body: form,
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      signal: controller?.signal,
    });
    if (res.status === 401) {
      if (!path.includes("/auth/login")) {
        sessionExpired(token);
      }
      throw new ApiError(401, "Incorrect email or password");
    }
    if (!res.ok) {
      let detail = res.statusText;
      try {
        detail = (await res.json())?.detail ?? detail;
      } catch {
        /* a non-JSON error body is still an error */
      }
      throw new ApiError(res.status, detail);
    }
    return res.json() as Promise<T>;
  } finally {
    clearTimeout(id);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const controller = typeof window !== "undefined" ? new AbortController() : null;
  const id = setTimeout(() => controller?.abort(), DEFAULT_TIMEOUT_MS);
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      ...init,
      signal: controller?.signal,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(init.headers ?? {}),
      },
    });

    if (res.status === 401) {
      if (!path.includes("/auth/login")) {
        sessionExpired(token);
      }
      throw new ApiError(401, "Incorrect email or password");
    }
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const body = await res.json();
        detail = body?.detail ?? detail;
      } catch {
        /* a non-JSON error body is still an error; the status carries it */
      }
      throw new ApiError(res.status, typeof detail === "string" ? detail : "Request failed");
    }
    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  } finally {
    clearTimeout(id);
  }
}

const get = <T,>(path: string) => request<T>(path);
const post = <T,>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

// --------------------------------------------------------------------------
// Types — mirroring app/schemas.py
// --------------------------------------------------------------------------

/** The three roles in the simplified system. */
export type Role = "student" | "tenant_admin" | "super_admin";

/** Turn a stored asset path into something an <img> can actually load.
 *
 *  Uploaded logos are stored as `/api/v1/platform/assets/...`, which is
 *  correct relative to the API — but the app is served from a different
 *  origin and port, so a browser resolves it against the frontend and gets a
 *  404. A logo the customer hosts is already absolute and is left alone.
 */
export function assetUrl(path?: string | null): string {
  if (!path) return "";
  if (/^https?:\/\//i.test(path)) return path;
  const origin = API_BASE.replace(/\/api\/v1\/?$/, "");
  return `${origin}${path.startsWith("/") ? "" : "/"}${path}`;
}

export interface SessionUser {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  scope: "platform" | "tenant";
  tenant_id: string | null;
  tenant_slug: string | null;
  tenant_name: string | null;
  /** Tenant branding, carried on the session so the shell has it on first
   *  paint. Null where the tenant has set none — the product mark is used. */
  tenant_display_name: string | null;
  tenant_logo_url: string | null;
  tenant_primary_color: string | null;
  must_change_password: boolean;
  ui_language: string;
  preferred_theme: string;
  roll_number?: string;
  branch?: string;
  year_of_study?: number | null;
  l1_language?: string;
}

export interface ProfileSection {
  id: string; position: number; title: string; task_type: string;
  instructions: string; item_count: number; prep_seconds: number;
  response_seconds: number; prompt_plays_allowed: number; allow_replay: boolean;
  /** This section's share of its skill, relative to the other sections
   *  carrying the same skill. 1 everywhere is an even split. */
  weight: number;
  selection: SectionSelection;
  /** The lettered section's time budget this sub-section sits under, in
   *  seconds; 0 where the format states none. */
  budget_seconds: number;
}

export interface SimulationProfile {
  id: string; code: string; name: string; style: string; description: string;
  /** Which employer's round this imitates. Empty for everything else. */
  company: string;
  status: string; estimated_minutes: number; is_baseline: boolean;
  /** Usual sitting length; `estimated_minutes` is the ceiling of the timed
   *  windows, not a cap on the sitting. Shown together as a range. */
  typical_minutes: number;
  /** The whole-sitting hard stop, server-enforced (estimate plus grace). */
  sitting_limit_minutes: number;
  scoring_weights: Record<string, number>;
  pass_threshold: number | null;
  skill_thresholds: Record<string, number>;
  target_role: string;
  department: string;
  difficulty_band: string;
  /** Surprises worth knowing before the clock starts. May be empty. */
  what_to_expect: string[];
  /** Parts of the real format this simulation omits. May be empty. */
  not_included: string;
  /** Which configuration of the real format this imitates. May be empty. */
  provenance: string;
  sections: ProfileSection[];
}

/** What a company round says at the end, in place of a scale.
 *
 *  `estimated` is always true today and the note always present: no employer
 *  outcome has ever been compared against this. Render both. */
export interface Verdict {
  label: string; detail: string; estimated: boolean; note: string;
}

/** The composite restated on a format's own scale.
 *
 *  `estimated` is always true: no concordance study has been run against the
 *  test being imitated, so this is an orientation figure and not a predicted
 *  vendor score. Render the note alongside it. */
export interface FormatSubScore {
  label: string;
  score: number | null;
  band: string;
  /** What this sub-score is about, in the student's terms. */
  means: string;
  /** Which task types actually fed it — the report shows its working. */
  from_tasks: string[];
  /** Which internal measures stood in for it. */
  from: string[];
  responses: number;
}

export interface FormatPresentation {
  /** null where no number under this format's name would be honest —
   *  we have no data relating our range to theirs. Show the band instead. */
  score: number | null;
  band: string;
  scale_min: number | null;
  scale_max: number | null;
  subscores: FormatSubScore[];
  /** Sub-scores this attempt could not support, and why. */
  missing: Record<string, string>;
  estimated: boolean;
  note: string;
  subscore_note: string;
  /** Where the sub-score structure came from and how far to trust it. */
  structure_note: string;
  weights_published: boolean;
}

/** How a section narrows its bank and draws from it.
 *
 *  Every field optional; an empty object is the historical behaviour, which is
 *  every published item of the task type sampled at random. */
export interface SectionSelection {
  difficulty_min?: number | null;
  difficulty_max?: number | null;
  topics?: string[];
  roles?: string[];
  industries?: string[];
  languages?: string[];
  /** A floor on how many eligible items must exist — retake variety, not a cap. */
  min_pool?: number;
  /** {easy|medium|hard: share}. Relative, so {hard: 2, easy: 1} is two thirds hard. */
  mix?: Record<string, number>;
}

export interface ProfileSectionInput {
  title: string; task_type: string; instructions: string; item_count: number;
  prep_seconds: number; response_seconds: number;
  prompt_plays_allowed: number; allow_replay: boolean;
  weight?: number;
  selection?: SectionSelection;
}

export interface ProfileInput {
  name: string; style: string; company: string; description: string;
  estimated_minutes: number; sections: ProfileSectionInput[];

  /* Everything below was configurable on the server and absent from this
     type, so the editor round-tripped a profile without them and the PUT
     wiped each one back to its default. A hiring round edited through the UI
     silently lost its pass mark. */
  scoring_weights?: Record<string, number>;
  pass_threshold?: number | null;
  skill_thresholds?: Record<string, number>;
  target_role?: string;
  department?: string;
  difficulty_band?: string;
}

export interface Attempt {
  id: string; profile_id: string; profile_name: string; attempt_number: number;
  status: string; mode: string; is_baseline: boolean; overall_score: number | null;
  started_at: string | null; submitted_at: string | null; scored_at: string | null;
}

export interface Mastery {
  skill: string; mastery: number; baseline: number | null;
  last_change: number; observations: number;
}

export interface Quest {
  id: string; kind: string; title: string; description: string;
  target_skill: string; progress: number; target: number;
  completed: boolean; bonus_xp: number; for_date: string;
}

export interface Streak {
  current_streak: number; best_streak: number;
  freezes_available: number; last_qualifying_day: string | null;
}

export interface StudentHome {
  user: UserRow;
  consent_given: boolean;
  baseline_done: boolean;
  total_xp: number;
  level: number;
  gap_percent: number | null;
  streak: Streak;
  quest: Quest | null;
  days_to_drive: number | null;
  assigned_profiles: SimulationProfile[];
  recent_attempts: Attempt[];
  mastery: Mastery[];
}

export interface UserRow {
  id: string; email: string; full_name: string; role: string; active: boolean;
  roll_number: string; branch: string; year_of_study: number | null;
  l1_language: string; created_at: string;
}

export interface Cohort {
  id: string; name: string; branch: string; year_of_study: number | null;
  section: string; trainer_id: string | null; trainer_name: string;
  drive_start: string | null; drive_end: string | null;
  member_count: number; active: boolean;
}

export interface CohortReadiness {
  cohort_id: string; cohort_name: string; total: number; assessed: number;
  placement_ready: number; needs_training: number; high_risk: number;
  not_started: number; average_overall: number | null; days_to_drive: number | null;
}

export interface StudentSummary {
  user: UserRow; attempts: number; last_attempt_at: string | null;
  overall_score: number | null; readiness: string;
  days_since_activity: number | null; flagged: boolean;
}

export interface TenantOverview {
  tenant_name: string; tenant_slug: string;
  seats_used: number; seat_limit: number; students: number;
  cohorts: number; attempts_total: number; consent_pending: number;
}

export interface SeasonRow {
  cohort_id: string; cohort_name: string; drive_start: string | null;
  drive_end: string | null; days_to_drive: number | null; season_source: string;
}

export interface PlatformOverview {
  tenants_total: number; tenants_active: number; seats_sold: number;
  providers_registered: number; capabilities_configured: number;
  capabilities_total: number; audit_events_7d: number;
}

export interface TenantBranding {
  display_name: string; logo_url: string; primary_color: string;
  default_theme: string; support_email: string;
}

export interface TenantContact {
  role: string; name: string; email: string; phone: string;
}

/** Paperwork rather than plumbing — all optional, filled in as sales learns it. */
export interface TenantProfile {
  address_line1: string; address_line2: string; city: string; state: string;
  postal_code: string; country: string;
  website: string; phone: string; contacts: TenantContact[];
  affiliated_to: string; established_year: number | null;
  student_strength: number | null; courses: string[];
  accreditation: string; notes: string;
  gst_number: string; billing_email: string;
}

export const EMPTY_TENANT_PROFILE: TenantProfile = {
  address_line1: "", address_line2: "", city: "", state: "",
  postal_code: "", country: "India",
  website: "", phone: "", contacts: [],
  affiliated_to: "", established_year: null,
  student_strength: null, courses: [],
  accreditation: "", notes: "",
  gst_number: "", billing_email: "",
};

export interface TenantRow {
  id: string; name: string; slug: string; domain: string;
  tenant_type: string; tenant_type_label: string;
  status: string;
  seat_limit: number; seats_used: number; region: string;
  branding: TenantBranding;
  profile: TenantProfile;
  created_at: string;
}

export interface TenantType { key: string; label: string }


export interface ProviderRow {
  id: string; capability: string; provider_key: string; name: string;
  tier: number; version: string; entrypoint: string; active: boolean;
  role: string; mode: string; calls_24h: number; error_rate: number;
  p50_latency_ms: number;
}

export interface CapabilityRow {
  capability: string; contract_version: string; configured: boolean;
  mode: string; primary: string; fallback: string; shadow: string;
  timeout_ms: number; providers: ProviderRow[];
}

export interface AuditRow {
  id: string; actor_type: string; actor_label: string; tenant_id: string | null;
  action: string; entity: string; entity_id: string; at: string;
}

export interface GamificationConfig {
  tenant_id: string | null;
  xp_table: Record<string, number>;
  difficulty_multipliers: Record<string, number>;
  weakness_multiplier: number;
  free_freezes_per_month: number;
  quiz_xp_cap_percent: number;
  leagues_enabled: boolean;
  max_engagement_notifications_per_day: number;
}

// --------------------------------------------------------------------------
// Endpoints
// --------------------------------------------------------------------------

export const api = {
  login: (email: string, password: string) =>
    post<{ token: string; user: SessionUser }>("/auth/login", { email, password }),
  me: () => get<SessionUser>("/auth/me"),
  savePreferences: (prefs: Record<string, unknown>) =>
    post<{ ok: boolean }>("/auth/preferences", prefs),

  studentHome: () => get<StudentHome>("/student/home"),
  studentProfiles: () => get<SimulationProfile[]>("/student/profiles"),
  studentAttempts: () => get<Attempt[]>("/student/attempts"),
  giveConsent: (scopes: string[]) => post<unknown>("/student/consent", { scopes }),

  trainerCohorts: () => get<Cohort[]>("/trainer/cohorts"),
  cohortReadiness: (id: string) => get<CohortReadiness>(`/trainer/cohorts/${id}/readiness`),
  cohortStudents: (id: string) => get<StudentSummary[]>(`/trainer/cohorts/${id}/students`),
  studentMastery: (id: string) => get<Mastery[]>(`/trainer/students/${id}/mastery`),

  tenantOverview: () => get<TenantOverview>("/tenant/overview"),
  tenantUsers: (role?: string) => get<UserRow[]>(`/tenant/users${role ? `?role=${role}` : ""}`),
  tenantCohorts: () => get<Cohort[]>("/tenant/cohorts"),
  /** The assessment library. Retired ones are left out unless asked for --
   *  they accumulate forever, because retiring is how an assessment leaves
   *  circulation and deleting one would orphan the results that name it. */
  /** The report for the sitting an invitation produced.
   *
   *  The employer who commissioned the assessment could not see its result:
   *  the candidate's own report is scoped to the person who sat it, and every
   *  trainer route is cohort-scoped, which a candidate is not in. */
  invitationResult: (invitationId: string) =>
    get<AttemptResult>(`/tenant/invitations/${invitationId}/result`),

  /** Everything one of your students has sat, newest first.
   *
   *  Named for the cohort rather than the student, because `studentAttempts`
   *  above is a different question: that one is "what have *I* sat", asked by
   *  the student themselves. */
  cohortStudentAttempts: (userId: string) =>
    get<Attempt[]>(`/trainer/students/${userId}/attempts`),

  /** One student's report, for the trainer coaching them. Cohort-scoped:
   *  the attempt is authorised through its owner, not through its id. */
  studentResult: (attemptId: string) =>
    get<AttemptResult>(`/trainer/attempts/${attemptId}/result`),

  tenantProfiles: (includeRetired = false) =>
    get<SimulationProfile[]>(
      `/tenant/profiles${includeRetired ? "?include_retired=true" : ""}`),
  tenantInvitations: () => get<InvitationRow[]>("/tenant/invitations"),
  createInvitation: (body: {
    profile_id: string; invited_name?: string; invited_email?: string;
    reference?: string; valid_days?: number | null;
  }) => post<InvitationRow>("/tenant/invitations", body),
  withdrawInvitation: (id: string) =>
    post<InvitationRow>(`/tenant/invitations/${id}/withdraw`, {}),
  createProfile: (body: ProfileInput) =>
    post<SimulationProfile>("/tenant/profiles", body),
  cloneProfile: (id: string) =>
    post<SimulationProfile>(`/tenant/profiles/${id}/clone`, {}),
  replaceProfile: (id: string, body: ProfileInput) =>
    put<SimulationProfile>(`/tenant/profiles/${id}`, body),
  setProfileStatus: (id: string, status: string) =>
    post<SimulationProfile>(`/tenant/profiles/${id}/status`, { status }),
  tenantSeason: () => get<SeasonRow[]>("/tenant/season"),

  platformOverview: () => get<PlatformOverview>("/platform/overview"),
  platformTenants: () => get<TenantRow[]>("/platform/tenants"),
  platformQuestions: (tenantId: string) =>
    get<{ tenants: Record<string, Record<string, number>>[] }>(`/platform/questions?tenant_id=${tenantId}`),
  platformQuestionItems: (tenantId: string, category: string, page = 1, pageSize = 10) =>
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    get<{items: Record<string, any>[]; total: number; page: number; page_size: number; total_pages: number}>(
      `/platform/questions/items?tenant_id=${tenantId}&category=${category}&page=${page}&page_size=${pageSize}`),
  platformDeleteQuestion: async (collection: string, itemId: string, tenantId: string): Promise<void> => {
    const token = getToken();
    const res = await fetch(`${API_BASE}/platform/questions/${collection}/${itemId}?tenant_id=${tenantId}`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    });
    if (!res.ok) throw new ApiError(res.status, "Delete failed");
  },
  platformCreateQuestion: (category: string, tenantId: string, body: Record<string, unknown>) =>
    post<{ id?: string; passage_id?: string; prompt_id?: string; questions?: number }>(
      `/platform/questions/${category}?tenant_id=${tenantId}`, body),
  platformTenantUsers: (tenantId: string) => get<UserRow[]>(`/platform/tenants/${tenantId}/users`),
  platformStudentAttempts: (userId: string, tenantId: string) =>
    get<Attempt[]>(`/platform/students/${userId}/attempts?tenant_id=${tenantId}`),
  tenantTypes: () => get<TenantType[]>("/platform/tenant-types"),

  platformCapabilities: () => get<CapabilityRow[]>("/platform/capabilities"),
  platformAudit: () => get<AuditRow[]>("/platform/audit"),
  platformGamification: () => get<GamificationConfig>("/platform/gamification"),
  narrationSettings: () => get<NarrationSettings>("/platform/narration/settings"),
};

/** A stored secret, never returned whole. */
export interface MaskedSecret { set: boolean; last4: string }

export interface NarrationSettings {
  narration_enabled: boolean;
  narration_provider: string;
  narration_model: string;
  anthropic_api_key: MaskedSecret;
  anthropic_base_url: string;
  nvidia_base_url: string;
  nvidia_model: string;
  nvidia_api_key: MaskedSecret;
  oss_base_url: string;
  oss_model: string;
  oss_api_key: MaskedSecret;
  oss_temperature: number;
  overridden: string[];
  providers: string[];
}

// --------------------------------------------------------------------------
// Attempt lifecycle (M1)
// --------------------------------------------------------------------------

export interface RunnerItem {
  response_id: string;
  position: number;
  section_id: string;
  section_title: string;
  task_type: string;
  instructions: string;
  prep_seconds: number;
  response_seconds: number;
  prompt_plays_allowed: number;
  prompt_text: string;
  has_prompt_audio: boolean;
  /**
   * Which passage this listening question belongs to. The runner plays the
   * audio once for the first item carrying a ref and not again for the rest,
   * so a 4-passage / 12-question section is heard 4 times. Empty when the item
   * is not a grouped listening question. Opaque id — never the passage words.
   */
  passage_ref: string;
  /** Budget of the lettered section this item belongs to (seconds; 0 = none).
   *  One clock per lettered section; when it runs out the rest of that
   *  section is passed over, never an item in progress. */
  section_budget_seconds: number;
  /** The server already holds this item's answer; the runner resumes past it. */
  answered: boolean;
  /** Section behaviour as configuration (app.formats.section_behaviour). */
  fixed_window: boolean;
  allow_skip: boolean;
  skip_prep: boolean;
  ack_gate: "" | "section" | "clip";
  continuous_numbering: boolean;
  /** Show this item's section instruction on the question screen itself. */
  show_instruction: boolean;
  /** speak | select | write — what the runner renders for this item. */
  response_mode: string;
  skill: string;
  /** select: the passage. Empty for listening — you are meant to hear it. */
  stimulus_text: string;
  stimulus_title: string;
  /**
   * How long the stimulus stays on screen before it is taken away. Zero means
   * it stays. Only Passage Reconstruction sets it: losing the passage is the
   * measurement, not a flourish.
   */
  stimulus_seconds: number;
  question: string;
  options: string[];
  /** write: the task and what a competent answer covers. */
  scenario: string;
  key_points: string[];
  min_words: number;
}

export interface RunnerPayload {
  attempt_id: string;
  profile_id: string;
  profile_name: string;
  /** When the whole sitting must be over, ISO. Null until it has started. */
  deadline_at: string | null;
  /**
   *  What the server thinks the time is, sent alongside the deadline.
   *
   *  A countdown run off the device clock expires an attempt early on a
   *  laptop whose time is wrong. Take the difference once, then count against
   *  a local timer.
   */
  server_now: string | null;
  seconds_remaining: number | null;
  /** Which test this imitates — drives the runner's chrome. */
  style: string;
  /** The setup check's measured room noise (dBFS), or null. The speech
   *  gates sit NOISE_MARGIN_DB above it (lib/speech.ts). */
  noise_dbfs: number | null;
  /** The room's 90th-percentile level from the setup check, or null. This
   *  is what the speech floor is set above (lib/speech.ts). */
  noise_ceiling_dbfs: number | null;
  company: string;
  status: string;
  mode: string;
  is_baseline: boolean;
  env_check_done: boolean;
  items: RunnerItem[];
}

export interface PromptPayload {
  text: string;
  accent: string;
  audio_url: string | null;
  plays_remaining: number;
}

export interface WordTiming {
  word: string;
  start_ms: number;
  end_ms: number;
  confidence: number;
}

export interface PauseSpan {
  start_ms: number;
  end_ms: number;
  ms: number;
}

export interface DisfluencyEvent {
  type: string;
  text: string;
  start_ms: number;
  end_ms: number;
}

export interface ResponseMetrics {
  response_id: string;
  position: number;
  task_type: string;
  prompt_text: string;
  skipped: boolean;
  onset_ms: number | null;
  speech_ms: number | null;
  duration_ms: number | null;
  words_per_minute: number | null;
  articulation_rate: number | null;
  pause_count: number | null;
  longest_pause_ms: number | null;
  quality: string;
  scores: Record<string, number>;
  transcript: string;
  words: WordTiming[];
  pauses: PauseSpan[];
  disfluencies: DisfluencyEvent[];
  /** What was measured against the item's reference text. */
  word_errors: { expected: string; heard: string; kind: string; start_ms?: number }[];
  /** How clearly each word came out. A different measurement, and it used to
   *  arrive under `word_errors` -- which is why every chip in the listen-back
   *  panel rendered "undefined" -> "undefined". */
  word_clarity: { word: string; score: number; posterior?: number;
                  start_ms?: number; end_ms?: number }[];
  accuracy: number | null;
  /** How much of what was asked for arrived, 0-1. Null where the item never
   *  said what a complete answer looks like. */
  completeness: number | null;
  has_audio: boolean;
}

export interface BiggestLever {
  dimension: string;
  current: number;
  target: number;
  predicted_gain: number;
}

export interface Highlight {
  dimension: string;
  score: number;
  /** Distance from this student's own average, signed. No cohort norms
   *  exist, and "ahead of your own average" needs none. */
  delta: number;
  means: string;
}

export interface Recommendation {
  dimension: string;
  current: number;
  target: number;
  /** What the overall would become if this matched their own best. */
  predicted_gain: number;
  advice: string;
}

export interface EvidenceRow {
  response_id: string;
  position: number;
  task_type: string;
  score: number;
  transcript?: string;
  words_per_minute?: number;
  articulation_rate?: number;
  onset_ms?: number;
  pauses?: { start_ms: number; end_ms: number; ms: number }[];
  disfluencies?: Record<string, unknown>[];
  word_errors?: Record<string, unknown>[];
  grammar_errors?: Record<string, unknown>[];
}

/** One section's contribution, as the server scored it.
 *
 *  Returned by the result endpoint since M7 and, until now, declared by
 *  nothing and rendered by nothing -- so the four-skill rollup this feeds was
 *  computed on every attempt and shown to nobody.
 */
export interface SectionResult {
  section_id: string;
  position: number;
  title: string;
  task_type: string;
  /** speaking | listening | reading | writing */
  skill: string;
  score: number | null;
  dimensions: Record<string, number>;
  /** How much of the section actually scored. */
  confidence: number | null;
  /** What it counted for within its skill. Relative, not a percentage. */
  weight: number;
  items_total: number;
  items_answered: number;
  /** Why it produced nothing, where it produced nothing. */
  unscored_reason: string;
}

export interface SkillScore {
  skill: string;
  score: number | null;
  section_count: number;
  /** Named, so a gap in the rollup is visible rather than absorbed. */
  unscored_sections: string[];
  note: string;
}

/** One thing to practise next, ready to act on. */
export interface ResultPriority {
  dimension: string;
  score: number;
  responses: number;
  practice: string;
  /** The targeted practice session this starts — a real profile. */
  practice_code: string;
  practice_profile_id: string;
  practice_name: string;
  practice_minutes: number;
  /** needs_most | needs_work — the verdict leads, the number supports.
   *  Only the primary diagnosis's dimension is ever needs_most. */
  verdict: string;
  evidence: string;
  /** What to do about it this week. */
  advice: string;
}

/** The one authoritative answer to "what should I work on first?".
 *
 *  Built once on the server (app/diagnosis.py) from measured evidence and
 *  consumed by every surface that names a weakness. The page never derives
 *  its own: it renders this. */
export interface PrimaryDiagnosis {
  /** identified | tied | level | insufficient | none */
  status: string;
  headline: string;
  reason: string;
  evidence: string;
  dimension: string;
  label: string;
  score: number | null;
  responses: number;
  scale_max: number;
  confidence: string;
  candidates: { dimension: string; label: string; score: number; responses: number }[];
  excluded: { dimension: string; label: string; why: string }[];
  /** Empty unless status is "identified". */
  practice_code: string;
  practice_profile_id: string;
  practice_name: string;
  practice_minutes: number;
  advice: string;
  /** The scored attempt whose measurements produced this diagnosis. */
  source_attempt_id: string;
  source_profile_id: string;
  source_profile_name: string;
}

/** What a finished practice session says about itself. */
export interface PracticeOutcome {
  dimension: string;
  label: string;
  practice_score: number | null;
  assessment_score: number | null;
  assessment_profile_id: string;
  assessment_profile_name: string;
  source_attempt_id: string;
  /** True when the practice was started from that assessment's result. */
  source_linked: boolean;
  /** The prescribing assessment's diagnosis, and whether this practice
   *  trained its primary dimension or a secondary priority. */
  prescribed_status: string;
  prescribed_dimension: string;
  trained_primary: boolean;
  change: number | null;
  practice_responses: number;
  /** higher | level | lower | insufficient — what one session can claim. */
  verdict: string;
}

/** The last scored sitting of the same assessment, for before/after. */
export interface PreviousAttempt {
  attempt_id: string;
  attempt_number: number;
  overall: number | null;
  delta: number | null;
}

export interface AttemptResult {
  attempt_id: string;
  profile_id: string;
  profile_name: string;
  /** Format family (e.g. svar_style), so the page can say whose names the
   *  sub-scores borrow: "Our estimate — not an SVAR result". */
  profile_style: string;
  status: string;
  mode: string;
  is_baseline: boolean;
  attempt_number: number;
  overall: number | null;
  band: string;
  scale_min: number;
  scale_max: number;
  dimensions: Record<string, number>;
  confidence: Record<string, number>;
  unscored: Record<string, string>;
  /** Engine output, retained in the payload; not a diagnosis surface. */
  biggest_lever: BiggestLever | null;
  /** The single source of truth for "what should I work on first?". */
  primary_diagnosis: PrimaryDiagnosis | null;
  environment_note: string;

  /* Reporting (Phase 8). All derived from measurements already in this
     payload, above the frozen scoring path. */

  /** A plain sentence before any chart. The Phase 0 rule. */
  summary: string;
  /** What they are ahead on. The report used to give only a weakness. */
  strengths: Highlight[];
  weaknesses: Highlight[];
  /** Ordered by computed gain. A plan, not a single instruction. */
  recommendations: Recommendation[];
  /** Dimension → the responses that produced it, with what they produced. */
  evidence: Record<string, EvidenceRow[]>;
  /** Company rounds only; null everywhere else. */
  verdict: Verdict | null;
  /** Vendor-style simulations only; null everywhere else. */
  presentation: FormatPresentation | null;
  calibrated: boolean;
  calibration_note: string;
  dimension_notes: Record<string, string>;
  overall_basis: string[];
  /** Where this sits on the CEFR ladder. Empty where nothing was scored --
   *  an attempt that failed has demonstrated nothing, not A1. */
  cefr_level: string;
  cefr_descriptor: string;
  /** Ships with the level, so a band can never appear without it. */
  cefr_caveat: string;
  /** Per section, in the order they were sat. */
  sections: SectionResult[];
  /** The four-skill rollup, weighted by each section's share. */
  skills: SkillScore[];
  responses: ResponseMetrics[];
  scored_at: string | null;
  scoring_ms: number | null;
  narration: Narration | null;
  previous: PreviousAttempt | null;
  priorities: ResultPriority[];
  practice: PracticeOutcome | null;
}

/** The AI explanation and its job state. Content is populated only when
 *  status is "ready"; otherwise the card shows a being-prepared or
 *  couldn't-generate note — never deterministic text dressed up as AI. */
export interface Narration {
  status: "pending" | "processing" | "retry_pending" | "ready" | "failed";
  headline: string;
  summary: string;
  primary_focus: string;
  practice_action: string;
  caveats: string[];
  model_version: string;
  generated_at: string | null;
}

export interface EnvCheckPayload {
  mic_ok: boolean;
  playback_ok?: boolean;
  headphones?: boolean;
  noise_dbfs?: number | null;
  /** The room's 90th-percentile level; the speech floor sits above it. */
  noise_ceiling_dbfs?: number | null;
  input_peak_dbfs?: number | null;
  device_label?: string;
  user_agent?: string;
  diagnostics?: Record<string, string | number | boolean>;
}

const ATTEMPTS = "/student/attempts";

/** What a candidate sees before deciding to start. Consumes nothing. */
export interface InvitePreview {
  ok: boolean;
  /** unknown | expired | used | withdrawn — each has a different next step
   *  for the person holding the link, which is why it is not one "invalid". */
  reason: string;
  message: string;
  tenant_name: string;
  profile_name: string;
  description: string;
  estimated_minutes: number;
  camera_check: boolean;
  practice_item: boolean;
  invited_name: string;
}

export interface CandidateSession {
  token: string;
  candidate_id: string;
  full_name: string;
  profile_id: string;
  tenant_name: string;
}

export interface InvitationRow {
  id: string; token: string; profile_id: string; profile_name: string;
  invited_name: string; invited_email: string; reference: string;
  status: string; expires_at: string | null; redeemed_at: string | null;
  attempt_id: string | null; created_at: string | null;
}

/** No session anywhere in here. A candidate arrives holding a token. */
export const inviteApi = {
  preview: (token: string) =>
    get<InvitePreview>(`/invite/${encodeURIComponent(token)}`),
  claim: (token: string, fullName: string, email: string) =>
    post<CandidateSession>(`/invite/${encodeURIComponent(token)}/claim`,
                           { full_name: fullName, email }),
};

/** Where an invited candidate left off. See `attemptApi.resume`. */
export interface CandidateResume {
  profile_id: string;
  profile_name: string;
  profile_description: string;
  estimated_minutes: number;
  tenant_name: string;
  attempt_id: string | null;
  attempt_status: string;
  consent_given: boolean;
}

export const attemptApi = {
  /** Unauthenticated: describes the server, not the person asking. */
  capability: () => get<Capability>("/meta/capability"),

  /** Where this candidate left off, or null if they are not one.
   *
   *  A candidate's invitation link works once, so it cannot tell them
   *  anything a second time. Without this, a reload after claiming showed
   *  them "somebody else has your link" and no way forward.
   *
   *  Deliberately does not go through `request`. The invite page asks this
   *  question *speculatively* -- most callers are first-time visitors with no
   *  session at all -- and `request` treats any 401 as an expired session,
   *  clears storage and sends the browser to /login. Asking "am I already
   *  somebody?" must be allowed to answer "no" without throwing the visitor
   *  off the page they were invited to. The first version of this shipped
   *  through `request` and bounced every new candidate straight to a login
   *  screen they have no account for. */
  resume: async (): Promise<CandidateResume | null> => {
    const token = getToken();
    if (!token) return null;
    try {
      const res = await fetch(`${API_BASE}${ATTEMPTS}/resume`,
                              { headers: { Authorization: `Bearer ${token}` } });
      if (!res.ok) return null;
      return (await res.json()) as CandidateResume;
    } catch {
      return null;
    }
  },

  /** Where the spreadsheet lives. A plain link, so the browser downloads it
   *  with the session it already has rather than us building a blob. */
  exportCsvUrl: (attemptId: string) =>
    `${API_BASE}${ATTEMPTS}/${attemptId}/export.csv`,

  start: (profileId: string, mode: "practice" | "official" | "stress" = "practice",
          sourceAttemptId?: string) =>
    post<RunnerPayload>(ATTEMPTS, { profile_id: profileId, mode,
                                    source_attempt_id: sourceAttemptId ?? null }),

  runner: (attemptId: string) => get<RunnerPayload>(`${ATTEMPTS}/${attemptId}/runner`),


  envCheck: (attemptId: string, body: EnvCheckPayload) =>
    post<{ ok: boolean; warning: string }>(`${ATTEMPTS}/${attemptId}/env-check`, body),

  /** Ask for a prompt. The server counts this — asking twice is a 409. */
  prompt: (attemptId: string, responseId: string) =>
    post<PromptPayload>(`${ATTEMPTS}/${attemptId}/responses/${responseId}/prompt`),

  skip: (attemptId: string, responseId: string) =>
    post<{ skipped: boolean }>(`${ATTEMPTS}/${attemptId}/responses/${responseId}/skip`),

  submit: (attemptId: string) => post<AttemptResult>(`${ATTEMPTS}/${attemptId}/submit`),

  result: (attemptId: string) => get<AttemptResult>(`${ATTEMPTS}/${attemptId}/result`),

  /** URL for the HTML report — opens in a new tab where it can be printed as PDF. */
  reportUrl: (attemptId: string) => `${API_BASE}/report/${attemptId}`,

  /** Fetch a recording as a blob URL.
   *
   *  An <audio src> cannot carry an Authorization header, and this endpoint
   *  will not accept a token in the query string — a recording URL that works
   *  when pasted is a recording URL that leaks. So the bytes are fetched with
   *  the header and handed to the player as an object URL, which the caller
   *  revokes when it unmounts.
   */
  async audioBlobUrl(attemptId: string, responseId: string): Promise<string> {
    const token = getToken();
    const res = await fetch(
      `${API_BASE}${ATTEMPTS}/${attemptId}/responses/${responseId}/audio`,
      { headers: token ? { Authorization: `Bearer ${token}` } : undefined },
    );
    if (res.status === 401) {
      sessionExpired(token);
      throw new ApiError(401, "Session expired");
    }
    if (res.status === 410) {
      throw new ApiError(410, "This recording passed its retention date and was deleted");
    }
    if (!res.ok) throw new ApiError(res.status, "Could not load the recording");
    return URL.createObjectURL(await res.blob());
  },

  /** Multipart, so it bypasses the JSON request helper. */
  /** Upload, and hand back the raw status instead of throwing.
   *
   *  `deliver` in lib/upload.ts decides what a status means -- notably that
   *  409 is a success, because the server refuses a second upload for a
   *  response it already holds. A wrapper that threw on 409 would make that
   *  decision impossible to express, and the retry after a lost response
   *  would lose a real answer.
   *
   *  A network failure still throws, which is exactly the distinction
   *  `deliver` needs: a thrown error never reached anything that could judge
   *  it, so it is always worth another go.
   */
  /** Submit a chosen or written answer, handing back the raw status.
   *
   *  The counterpart of `uploadAudioStatus`, and it exists for the same
   *  reason: `deliver` decides what a status means, notably that 409 is
   *  success. The server refuses a second answer for a response it has
   *  already marked, so that refusal proves the first one landed.
   */
  async answerStatus(attemptId: string, responseId: string,
                     body: Blob): Promise<number> {
    const token = getToken();
    const res = await fetch(
      `${API_BASE}${ATTEMPTS}/${attemptId}/responses/${responseId}/answer`,
      {
        method: "POST",
        body: await body.text(),
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      },
    );
    return res.status;
  },

  async uploadAudioStatus(attemptId: string, responseId: string,
                          wav: Blob, endedBy = ""): Promise<number> {
    const form = new FormData();
    form.append("file", wav, "answer.wav");
    // Why the recording stopped (user_ended | auto_advance | window_expired
    // | cancelled). The report may only say "ran out of time" for
    // window_expired, so this must travel with the audio itself.
    if (endedBy) form.append("ended_by", endedBy);
    const token = getToken();
    const res = await fetch(
      `${API_BASE}${ATTEMPTS}/${attemptId}/responses/${responseId}/audio`,
      {
        method: "POST",
        body: form,
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      },
    );
    return res.status;
  },

  async uploadAudio(attemptId: string, responseId: string, wav: Blob,
                    endedBy = "") {
    const form = new FormData();
    form.append("file", wav, "answer.wav");
    if (endedBy) form.append("ended_by", endedBy);
    const token = getToken();
    const res = await fetch(
      `${API_BASE}${ATTEMPTS}/${attemptId}/responses/${responseId}/audio`,
      {
        method: "POST",
        body: form,
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      },
    );
    if (res.status === 401) {
      sessionExpired(token);
      throw new ApiError(401, "Session expired");
    }
    if (!res.ok) {
      let detail = res.statusText;
      try {
        detail = (await res.json())?.detail ?? detail;
      } catch {
        /* the status is the message */
      }
      throw new ApiError(res.status, typeof detail === "string" ? detail : "Upload failed");
    }
    return (await res.json()) as {
      stored: boolean; duration_ms: number; quality: string; delete_after_days: number;
    };
  },
};

// --------------------------------------------------------------------------
// Institution administration, trainer ops, game and practice (M3-M6)
// --------------------------------------------------------------------------

export interface SeatUsage {
  used: number; limit: number; students: number; trainers: number;
  admins: number; remaining: number;
}

export interface ImportPreview {
  ok: boolean; total: number; creating: number; updating: number;
  seats_after: number; seat_limit: number; over_seat_limit: boolean;
  problems: { line: number; column: string; message: string }[];
  sample: Record<string, string>[];
}

export interface ImportResult {
  created: number; updated: number; cohorts_created: string[];
  temporary_passwords: Record<string, string>;
}

export interface Assignment {
  id: string; cohort_id: string; cohort_name: string; profile_id: string;
  profile_name: string; mandatory: boolean; opens_at: string | null;
  due_at: string | null; max_attempts: number; completed: number; total: number;
}

export interface Flag {
  id: string; user_id: string; student_name: string; reason: string;
  note: string; auto_suggested: boolean; resolved: boolean;
  raised_by_name: string; created_at: string;
}

export interface MomentumRow {
  user_id: string; full_name: string; cohort_name: string;
  days_since_activity: number | null; attempts: number; current_streak: number;
  days_to_drive: number | null; overall_score: number | null;
  suggest_flag: boolean; suggestion: string; flagged: boolean;
}

export interface BadgeRow {
  code: string; name: string; description: string; category: string;
  earned_at: string | null;
}

export interface SeasonWeek {
  week: number; theme: string; target_skill: string; minutes_target: number;
}

export interface Season {
  starts_on: string; ends_on: string; drive_date: string | null;
  days_remaining: number | null; is_real_drive_date: boolean;
  daily_minutes_target: number; weeks: SeasonWeek[]; replans: number;
}

export interface GameState {
  level: number; total_xp: number; xp_into_level: number; xp_per_level: number;
  gap_percent: number | null; gap_at_baseline: number | null;
  streak: Streak; quest: Quest; badges: BadgeRow[]; season: Season;
}

export interface LedgerEntry {
  activity: string; base_xp: number; difficulty_multiplier: number;
  weakness_multiplier: number; awarded_xp: number; cap_applied: string;
  target_skill: string; at: string;
}

export interface QuizItem {
  id: string; category: string; stem: string; options: string[];
  seconds_allowed: number; is_review: boolean;
}

export interface QuizResultItem {
  item_id: string; stem: string; options: string[]; selected_index: number | null;
  correct_index: number; is_correct: boolean; explanation: string; category: string;
}

export interface QuizResult {
  total: number; correct: number; accuracy: number; xp_awarded: number;
  xp_capped: boolean; cap_note: string; quest_progress: number;
  quest_target: number; quest_completed: boolean; items: QuizResultItem[];
}

export interface Mistake {
  id: string; skill: string; stem: string; category: string;
  times_wrong: number; times_right_since: number; interval_days: number;
  due_at: string; due_now: boolean;
}



/** What this deployment can measure. See /meta/capability on the server. */
export interface Capability {
  tier: number;
  full_scoring: boolean;
  measures: string[];
  /** Empty on a full install; a plain-English warning otherwise. */
  note: string;
}

/** One of the four language skills. See app/skills.py on the server. */
export interface SkillModule {
  key: string;
  label: string;
  /** live | partial | planned — computed from real content, never stored. */
  status: string;
  summary: string;
  measures: string[];
  item_count: number;
  href: string;
  /** Present only when something is missing, and says what. */
  gap: string;
  mastery: number | null;
  /** Where an indirect mastery number came from. */
  mastery_basis: string;
}

export interface SkillsOverview {
  modules: SkillModule[];
  headline: string;
}





// -- Writing ---------------------------------------------------------------

export interface WritingPromptRow {
  id: string; title: string; kind: string;
  scenario: string; prompt: string;
  min_words: number; suggested_minutes: number;
  key_points: string[]; best_score: number | null;
}

export interface WritingMeasure {
  name: string; score: number; confidence: number;
  /** What was counted, so the number can be argued with. */
  basis: string; detail: Record<string, unknown>;
}

export interface WritingResult {
  submission_id: string; title: string; word_count: number;
  overall: number | null; too_short: boolean; notes: string[];
  measures: WritingMeasure[]; text: string;
  xp_awarded: number; day_counted_now: boolean; streak_current: number;
}

export const writingApi = {
  prompts: () => get<WritingPromptRow[]>("/student/writing/prompts"),
  submit: (id: string, body: { text: string; minutes_spent: number }) =>
    post<WritingResult>(`/student/writing/prompts/${id}/submit`, body),
  submissions: () => get<WritingResult[]>("/student/writing/submissions"),
};

// -- Reading ---------------------------------------------------------------

export interface ReadingPassageRow {
  id: string; title: string; kind: string;
  word_count: number; question_count: number; best_score: number | null;
}

export interface ReadingStart {
  attempt_id: string; passage_id: string; title: string; kind: string;
  body: string; word_count: number; question_count: number;
}

export interface ReadingQuestion { id: string; stem: string; options: string[]; }

export interface ReadingResultItem {
  item_id: string; stem: string; options: string[];
  selected_index: number | null; correct_index: number;
  is_correct: boolean; explanation: string;
}

export interface ReadingResult {
  attempt_id: string; title: string;
  correct: number; total: number; score: number; band: string;
  /** Reported beside comprehension, never blended into it. */
  words_per_minute: number | null; word_count: number; rate_note: string;
  body: string;
  items: ReadingResultItem[];
  xp_awarded: number; day_counted_now: boolean; streak_current: number;
}

export const readingApi = {
  passages: () => get<ReadingPassageRow[]>("/student/reading/passages"),
  start: (id: string) => post<ReadingStart>(`/student/reading/passages/${id}/start`),
  questions: (attemptId: string) =>
    get<ReadingQuestion[]>(`/student/reading/attempts/${attemptId}/questions`),
  submit: (attemptId: string,
           body: { answers: { item_id: string; selected_index: number | null }[];
                   read_ms: number }) =>
    post<ReadingResult>(`/student/reading/attempts/${attemptId}/submit`, body),
};

// -- Listening -------------------------------------------------------------

export interface ListeningPassageRow {
  id: string; title: string; kind: string;
  approx_seconds: number; plays_allowed: number;
  question_count: number; best_score: number | null;
  /** False means the browser speaks it. The UI says so. */
  has_recording: boolean;
}

export interface ListeningStart {
  attempt_id: string; passage_id: string; title: string; kind: string;
  transcript: string; accent: string; plays_allowed: number;
  question_count: number; audio_key: string;
}

export interface ListeningQuestion {
  id: string; stem: string; options: string[];
}

export interface ListeningResultItem {
  item_id: string; stem: string; options: string[];
  selected_index: number | null; correct_index: number;
  is_correct: boolean; explanation: string;
}

export interface ListeningResult {
  attempt_id: string; title: string;
  correct: number; total: number; score: number; band: string;
  transcript: string;
  items: ListeningResultItem[];
  xp_awarded: number; day_counted_now: boolean; streak_current: number;
}

export const listeningApi = {
  passages: () => get<ListeningPassageRow[]>("/student/listening/passages"),
  start: (id: string) =>
    post<ListeningStart>(`/student/listening/passages/${id}/start`),
  questions: (attemptId: string) =>
    get<ListeningQuestion[]>(`/student/listening/attempts/${attemptId}/questions`),
  submit: (attemptId: string,
           body: { answers: { item_id: string; selected_index: number | null }[];
                   plays_used: number }) =>
    post<ListeningResult>(`/student/listening/attempts/${attemptId}/submit`, body),
};


const del = <T,>(path: string) => request<T>(path, { method: "DELETE" });
const patch = <T,>(path: string, body: unknown) =>
  request<T>(path, { method: "PATCH", body: JSON.stringify(body) });
const put = <T,>(path: string, body: unknown) =>
  request<T>(path, { method: "PUT", body: JSON.stringify(body) });

export const adminApi = {
  seats: () => get<SeatUsage>("/tenant/seats"),
  previewImport: (csvText: string) =>
    post<ImportPreview>("/tenant/users/import/preview", { csv_text: csvText }),
  commitImport: (csvText: string) =>
    post<ImportResult>("/tenant/users/import", { csv_text: csvText }),
  createUser: (body: Record<string, unknown>) => post<UserRow>("/tenant/users", body),
  updateUser: (id: string, body: Record<string, unknown>) =>
    patch<UserRow>(`/tenant/users/${id}`, body),
  resetPassword: (id: string) =>
    post<{ email: string; temporary_password: string }>(`/tenant/users/${id}/reset-password`),
  createCohort: (body: Record<string, unknown>) => post<Cohort>("/tenant/cohorts", body),
  updateCohort: (id: string, body: Record<string, unknown>) =>
    patch<Cohort>(`/tenant/cohorts/${id}`, body),
  assignments: () => get<Assignment[]>("/tenant/assignments"),
  createAssignment: (body: Record<string, unknown>) =>
    post<Assignment>("/tenant/assignments", body),
  deleteAssignment: (id: string) => del<{ deleted: boolean }>(`/tenant/assignments/${id}`),
};


export const gameApi = {
  state: () => get<GameState>("/student/game"),
  ledger: () => get<LedgerEntry[]>("/student/game/ledger"),
  badges: () => get<BadgeRow[]>("/student/game/badges"),
};

export const practiceApi = {
  nextQuiz: (count = 10) => get<QuizItem[]>(`/student/quiz/next?count=${count}`),
  submitQuiz: (answers: { item_id: string; selected_index: number | null }[]) =>
    post<QuizResult>("/student/quiz/submit", { answers }),
  mistakes: () => get<Mistake[]>("/student/mistakes"),
  skills: () => get<SkillsOverview>("/student/skills"),

};


export const operatorApi = {
  /** null = leave unchanged, "" = clear back to the environment default. */
  updateNarrationSettings: (body: Record<string, unknown>) =>
    put<NarrationSettings>("/platform/narration/settings", body),
  configureCapability: (capability: string, body: Record<string, unknown>) =>
    put<{ applied: boolean }>(`/platform/capabilities/${capability}`, body),
  setProviderActive: (id: string, active: boolean) =>
    post<{ active: boolean }>(`/platform/providers/${id}/active?active=${active}`),
  createTenant: (body: Record<string, unknown>) => post<TenantRow>("/platform/tenants", body),
  updateTenant: (id: string, body: Record<string, unknown>) =>
    patch<TenantRow>(`/platform/tenants/${id}`, body),

  setTenantLogoUrl: (id: string, url: string) =>
    post<TenantRow>(`/platform/tenants/${id}/logo-url`, { url }),
  uploadTenantLogo: async (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return upload<TenantRow>(`/platform/tenants/${id}/logo`, form);
  },
  /** One institution's student reports as a ZIP of CSVs.
   *
   *  Fetched rather than linked: the endpoint wants the bearer header, which
   *  a plain <a href> cannot carry. The caller gets a Blob to save. */
  exportTenantReports: async (id: string): Promise<Blob> => {
    const token = getToken();
    const res = await fetch(`${API_BASE}/platform/tenants/${id}/export.zip`,
      { headers: token ? { Authorization: `Bearer ${token}` } : undefined });
    if (res.status === 401) {
      sessionExpired(token);
      throw new ApiError(401, "Session expired");
    }
    if (!res.ok) {
      let detail = res.statusText;
      try {
        detail = (await res.json())?.detail ?? detail;
      } catch {
        /* a non-JSON error body is still an error */
      }
      throw new ApiError(res.status, detail);
    }
    return res.blob();
  },
  registerProvider: (body: Record<string, unknown>) =>
    post<ProviderRow>("/platform/providers", body),
  updateProvider: (id: string, body: Record<string, unknown>) =>
    patch<ProviderRow>(`/platform/providers/${id}`, body),

updateGamification: (body: Record<string, unknown>) =>
    put<GamificationConfig>("/platform/gamification", body),


};

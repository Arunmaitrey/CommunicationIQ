"use client";
import { useState } from "react";
import { Copy, Plus, Trash2 } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { Badge, ErrorNote, PageHeader, Section, Skeleton } from "@/components/ui";
import {
  api, ApiError,
  type ProfileInput, type ProfileSectionInput, type SectionSelection,
  type SimulationProfile,
} from "@/lib/api";
import { useData } from "@/lib/useData";

export default function TenantProfilesPage() {
  return (
    <RequireAuth roles={["tenant_admin"]}>
      <Profiles />
    </RequireAuth>
  );
}

const STYLE_LABEL: Record<string, string> = {
  diagnostic: "Diagnostic",
  versant_style: "Versant-style",
  svar_style: "SVAR-style",
  speechx_style: "SpeechX-style",
  company_round: "Company round",
  drill: "Drill",
};

/** Every task type the runner serves, grouped by the skill it measures.
 *
 *  This listed the six speaking types, which is what every task type was when
 *  it was written — so an admin could not build a Listening, Reading or
 *  Writing section through the builder even after the runner could serve one.
 *  Grouped rather than flat because the group is the useful thing: an admin
 *  building a four-skill round needs to see which skills they have covered. */
const TASK_GROUPS: { skill: string; types: [string, string][] }[] = [
  {
    skill: "Speaking",
    types: [
      ["read_aloud", "Read Aloud"],
      ["repeat_sentence", "Repeat Sentence"],
      ["short_answer", "Short Answer"],
      ["sentence_build", "Sentence Build"],
      ["story_retell", "Story Retell"],
      ["open_response", "Open Response"],
      ["conversation_question", "Conversation Question"],
      ["passage_question", "Passage Question"],
    ],
  },
  {
    skill: "Listening",
    types: [
      ["listening_comprehension", "Listening Comprehension"],
      ["response_selection", "Choose the Reply"],
      ["dictation", "Dictation"],
    ],
  },
  {
    skill: "Reading",
    types: [
      ["reading_comprehension", "Reading Comprehension"],
      ["vocabulary_in_context", "Word in Context"],
    ],
  },
  {
    skill: "Writing",
    types: [
      ["email_writing", "Email Writing"],
      ["sentence_completion", "Sentence Completion"],
      ["passage_reconstruction", "Passage Reconstruction"],
    ],
  },
];

/** Only Speaking items carry topic, role, industry and language, so only a
 *  speaking section can be filtered on them. The server refuses the rest at
 *  build time; the editor hides the controls so it never comes up. */
const CLASSIFIED_TASK_TYPES = new Set(
  TASK_GROUPS[0].types.map(([value]) => value),
);

const INDUSTRIES = ["bpo", "it", "banking", "healthcare", "retail"] as const;
const BANDS = ["easy", "medium", "hard"] as const;

const BLANK_SECTION: ProfileSectionInput = {
  title: "", task_type: "read_aloud", instructions: "", item_count: 4,
  prep_seconds: 0, response_seconds: 30, prompt_plays_allowed: 0,
  allow_replay: false, weight: 1, selection: {},
};

function blankProfile(): ProfileInput {
  return {
    name: "", style: "company_round", company: "", description: "",
    estimated_minutes: 12, sections: [{ ...BLANK_SECTION }],
    scoring_weights: {}, pass_threshold: null, skill_thresholds: {},
    target_role: "", department: "", difficulty_band: "",
  };
}

/** A profile as the editor holds it — every field, not the visible ones.
 *
 *  This carried six. The PUT replaces a profile wholesale, so the five it did
 *  not carry were reset to their defaults on every save: opening a hiring
 *  round to change one word removed its pass mark, its per-dimension floors
 *  and its classification, and the screen looked identical afterwards. */
function toInput(p: SimulationProfile): ProfileInput {
  return {
    name: p.name, style: p.style, company: p.company,
    description: p.description, estimated_minutes: p.estimated_minutes,
    scoring_weights: { ...(p.scoring_weights ?? {}) },
    pass_threshold: p.pass_threshold ?? null,
    skill_thresholds: { ...(p.skill_thresholds ?? {}) },
    target_role: p.target_role ?? "",
    department: p.department ?? "",
    difficulty_band: p.difficulty_band ?? "",
    sections: p.sections.map((s) => ({
      title: s.title, task_type: s.task_type, instructions: s.instructions,
      item_count: s.item_count, prep_seconds: s.prep_seconds,
      response_seconds: s.response_seconds,
      prompt_plays_allowed: s.prompt_plays_allowed, allow_replay: s.allow_replay,
      weight: s.weight ?? 1,
      selection: { ...(s.selection ?? {}) },
    })),
  };
}

/** What a section's weight means, said in the admin's terms.
 *
 *  Relative, not a percentage, and the difference matters: an admin who reads
 *  "3" as "30%" will set four sections to 25 and wonder why nothing changed.
 *  So the hint talks about parts, and names the two ends.
 */
function weightHint(weight: number): string {
  if (weight === 0) {
    return "Runs and is shown, but does not count towards the skill score. "
      + "Right for a warm-up.";
  }
  if (weight === 1) return "An even share of its skill, alongside the others.";
  return `${weight} parts, against 1 part for a section left at 1.`;
}

function Profiles() {
  // Retired assessments are off by default and fetched only when asked for.
  // They accumulate permanently -- retiring is how one leaves circulation,
  // and deleting would orphan the results that name it -- so a library that
  // showed them all was 1466 cards and a 1.25 MB response on the demo estate
  // alone. Hidden, not lost: the toggle says how to see them.
  const [showRetired, setShowRetired] = useState(false);
  const { data, loading, error, reload } =
    useData(() => api.tenantProfiles(showRetired), [showRetired]);
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState<ProfileInput | null>(null);
  const [busy, setBusy] = useState("");
  const [problem, setProblem] = useState("");

  async function run(what: string, fn: () => Promise<unknown>) {
    setBusy(what);
    setProblem("");
    try {
      await fn();
      reload();
      setEditing(null);
      setDraft(null);
    } catch (err) {
      setProblem(err instanceof ApiError ? err.detail : "That did not work");
    } finally {
      setBusy("");
    }
  }

  return (
    <>
      <PageHeader
        title="Assessment library"
        sub="Everything a student can be given: the four standard templates, the company rounds, and anything your team has built. Templates imitate the format, timing and pressure of the real assessments — never their items."
      />

      {problem && <div className="mb-4"><ErrorNote message={problem} /></div>}

      <div className="mb-4 flex items-center justify-between gap-3">
        <p className="text-[11px] text-muted leading-relaxed max-w-2xl">
          The seeded company rounds are a starting point. Clone one and edit the
          copy to match the round your recruiters actually run — a profile that
          students have already attempted is locked, because changing the
          questions under a scored attempt would make that score meaningless.
        </p>
        <div className="flex items-center gap-2 shrink-0">
          <button className="btn btn-ghost btn-sm ds-focus"
                  onClick={() => setShowRetired(!showRetired)}
                  title="Retired assessments stay for the results that name them.">
            {showRetired ? "Hide retired" : "Show retired"}
          </button>
          <button
            className="btn btn-primary btn-sm ds-focus"
            onClick={() => { setEditing("new"); setDraft(blankProfile()); }}
          >
            <Plus size={14} /> New profile
          </button>
        </div>
      </div>

      {editing === "new" && draft && (
        <Section title="New profile">
          <Editor
            draft={draft} onChange={setDraft} busy={busy === "create"}
            onCancel={() => { setEditing(null); setDraft(null); }}
            onSave={() => void run("create", () => api.createProfile(draft))}
          />
        </Section>
      )}

      {loading ? <Skeleton rows={4} /> : error ? <ErrorNote message={error} /> : (
        <div className="space-y-6">
          {shelves(data ?? []).map(([shelf, blurb, rows]) => (
            <div key={shelf}>
              <h2 className="text-sm font-bold mb-1">{shelf}</h2>
              <p className="text-[11px] text-muted leading-relaxed mb-2 max-w-2xl">
                {blurb}
              </p>
              <div className="space-y-3">
          {rows.map((p) => (
            <Section
              key={p.id}
              title={p.name}
              action={
                <div className="flex items-center gap-2">
                  <span className="text-[11px] text-muted">
                    {STYLE_LABEL[p.style] ?? p.style}
                  </span>
                  {p.company && <Badge tone="var(--primary)">{p.company}</Badge>}
                  {p.is_baseline && <Badge tone="var(--accent)">Baseline</Badge>}
                  {p.status === "published"
                    ? <Badge tone="var(--rag-green)">Published</Badge>
                    : <Badge tone="var(--muted)">{p.status}</Badge>}
                </div>
              }
            >
              <p className="text-xs text-muted leading-relaxed mb-2">{p.description}</p>
              <div className="text-[11px] text-muted mb-3">
                {p.sections.length} sections · about {p.estimated_minutes} minutes
                {p.sections.length > 0 && (
                  <> · {p.sections.map((s) => s.title).join(" → ")}</>
                )}
              </div>

              {p.sections.length === 0 && p.status !== "published" && (
                <p className="text-[11px] mb-3" style={{ color: "var(--rag-amber)" }}>
                  No sections. This cannot be published until it has at least one —
                  a student would start it and be handed nothing to answer.
                </p>
              )}

              <div className="flex flex-wrap gap-2">
                <button className="btn btn-ghost btn-sm ds-focus"
                        disabled={busy !== ""}
                        onClick={() => void run("clone", () => api.cloneProfile(p.id))}>
                  <Copy size={13} /> Clone
                </button>
                <button className="btn btn-ghost btn-sm ds-focus"
                        disabled={busy !== ""}
                        onClick={() => { setEditing(p.id); setDraft(toInput(p)); }}>
                  Edit
                </button>
                {p.status !== "published" && (
                  <button className="btn btn-primary btn-sm ds-focus"
                          disabled={busy !== "" || p.sections.length === 0}
                          title={p.sections.length === 0 ? "Add a section first" : ""}
                          onClick={() => void run("status",
                            () => api.setProfileStatus(p.id, "published"))}>
                    Publish
                  </button>
                )}
                {p.status === "published" && (
                  <button className="btn btn-ghost btn-sm ds-focus"
                          disabled={busy !== ""}
                          onClick={() => void run("status",
                            () => api.setProfileStatus(p.id, "retired"))}>
                    Retire
                  </button>
                )}
              </div>

              {editing === p.id && draft && (
                <div className="mt-4 pt-4" style={{ borderTop: "1px solid var(--border)" }}>
                  <Editor
                    draft={draft} onChange={setDraft} busy={busy === "save"}
                    onCancel={() => { setEditing(null); setDraft(null); }}
                    onSave={() => void run("save", () => api.replaceProfile(p.id, draft))}
                  />
                </div>
              )}
            </Section>
          ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}

/** The library, in the order somebody choosing an assessment thinks in.
 *
 *  Reuses the profile rows that already exist rather than introducing a
 *  second concept -- a "template" here is a seeded profile whose code matches
 *  a blueprint, which is exactly what it is in the database. Inventing an
 *  Assessment entity beside SimulationProfile would have meant two things to
 *  keep in step and two places to publish from. */
const TEMPLATE_CODES = new Set([
  "svar_full_simulation",
  "versant_style_speaking_listening",
  "versant_style_four_skills",
  "professional_english",
]);

function shelves(rows: SimulationProfile[]): [string, string, SimulationProfile[]][] {
  const templates = rows.filter((p) => TEMPLATE_CODES.has(p.code));
  const rounds = rows.filter((p) => p.style === "company_round"
                                    && !TEMPLATE_CODES.has(p.code));
  const rest = rows.filter((p) => !templates.includes(p) && !rounds.includes(p));

  const out: [string, string, SimulationProfile[]][] = [];
  if (templates.length) {
    out.push(["Standard templates",
      "The four full-length assessments. Clone one to change it — editing the original would change a test students may already have sat.",
      templates]);
  }
  if (rounds.length) {
    out.push(["Company rounds",
      "Shaped like the communication round each employer actually runs. Shorter, and scored as an outcome rather than a scale.",
      rounds]);
  }
  if (rest.length) {
    out.push(["Everything else",
      "The diagnostic, drills, and assessments your team has built.",
      rest]);
  }
  return out;
}

function Editor({ draft, onChange, onSave, onCancel, busy }: {
  draft: ProfileInput;
  onChange: (d: ProfileInput) => void;
  onSave: () => void;
  onCancel: () => void;
  busy: boolean;
}) {
  const set = (patch: Partial<ProfileInput>) => onChange({ ...draft, ...patch });

  const setSection = (i: number, patch: Partial<ProfileSectionInput>) =>
    set({ sections: draft.sections.map((s, n) => (n === i ? { ...s, ...patch } : s)) });

  return (
    <div className="space-y-3">
      <div className="grid md:grid-cols-2 gap-3">
        <Field label="Name">
          <input className="ds-input w-full" value={draft.name}
                 onChange={(e) => set({ name: e.target.value })}
                 placeholder="e.g. Deloitte-style Communication Round" />
        </Field>
        <Field label="Style">
          <select className="ds-input w-full" value={draft.style}
                  onChange={(e) => set({ style: e.target.value })}>
            {Object.entries(STYLE_LABEL).map(([v, l]) => (
              <option key={v} value={v}>{l}</option>
            ))}
          </select>
        </Field>
        {draft.style === "company_round" && (
          <Field label="Company"
                 hint="Used to describe the round only. Implies no affiliation.">
            <input className="ds-input w-full" value={draft.company}
                   onChange={(e) => set({ company: e.target.value })}
                   placeholder="e.g. Deloitte" />
          </Field>
        )}
        <Field label="Estimated minutes">
          <input className="ds-input w-full" type="number" min={1} max={180}
                 value={draft.estimated_minutes}
                 onChange={(e) => set({ estimated_minutes: Number(e.target.value) })} />
        </Field>
      </div>

      <Field label="Description">
        <textarea className="ds-input w-full" rows={2} value={draft.description}
                  onChange={(e) => set({ description: e.target.value })}
                  placeholder="What this round is and what it is testing." />
      </Field>

      {/* Who it is for, and what counts as a pass. Configurable on the server
          since Phase 3 and absent from this screen until now — so the only way
          to set a pass mark was the API, and opening the profile here removed
          it again. */}
      <div className="grid md:grid-cols-3 gap-3">
        <Field label="Target role"
               hint="Classification only. Nothing scores differently.">
          <input className="ds-input w-full" value={draft.target_role ?? ""}
                 onChange={(e) => set({ target_role: e.target.value })}
                 placeholder="e.g. customer support" />
        </Field>
        <Field label="Department">
          <input className="ds-input w-full" value={draft.department ?? ""}
                 onChange={(e) => set({ department: e.target.value })}
                 placeholder="e.g. operations" />
        </Field>
        <Field label="Content level"
               hint="A CEFR label for the material, never a claim about the candidate.">
          <input className="ds-input w-full" value={draft.difficulty_band ?? ""}
                 onChange={(e) => set({ difficulty_band: e.target.value })}
                 placeholder="e.g. B2" />
        </Field>
      </div>

      <Field label="Pass mark"
             hint="On the internal 20–80 scale. Leave empty for practice: an assessment with no pass mark does not pass or fail anybody, which is the right answer for most of them.">
        <input className="ds-input w-full md:w-40" type="number" min={20} max={80}
               value={draft.pass_threshold ?? ""}
               onChange={(e) => set({
                 pass_threshold: e.target.value === "" ? null : Number(e.target.value),
               })} />
      </Field>

      <div>
        <div className="flex items-center justify-between mb-2">
          <span className="text-[11px] font-bold uppercase tracking-wider text-muted">
            Sections — in order
          </span>
          <button className="btn btn-ghost btn-sm ds-focus"
                  onClick={() => set({ sections: [...draft.sections, { ...BLANK_SECTION }] })}>
            <Plus size={13} /> Add section
          </button>
        </div>

        <div className="space-y-2">
          {draft.sections.map((s, i) => (
            <div key={i} className="ds-inset p-3">
              <div className="flex items-center justify-between gap-2 mb-2">
                <span className="text-[11px] font-bold text-muted">Section {i + 1}</span>
                <button className="btn btn-ghost btn-sm ds-focus"
                        onClick={() => set({
                          sections: draft.sections.filter((_, n) => n !== i),
                        })}>
                  <Trash2 size={12} />
                </button>
              </div>
              <div className="grid md:grid-cols-3 gap-2">
                <Field label="Title">
                  <input className="ds-input w-full" value={s.title}
                         onChange={(e) => setSection(i, { title: e.target.value })}
                         placeholder="e.g. Just A Minute" />
                </Field>
                <Field label="Task type">
                  <select className="ds-input w-full" value={s.task_type}
                          onChange={(e) => setSection(i, {
                            task_type: e.target.value,
                            // A filter the new bank cannot honour would be
                            // refused on save. Clearing it here means the
                            // admin finds out by the control disappearing
                            // rather than by a validation error.
                            selection: CLASSIFIED_TASK_TYPES.has(e.target.value)
                              ? s.selection
                              : dropClassification(s.selection),
                          })}>
                    {TASK_GROUPS.map((group) => (
                      <optgroup key={group.skill} label={group.skill}>
                        {group.types.map(([v, l]) => (
                          <option key={v} value={v}>{l}</option>
                        ))}
                      </optgroup>
                    ))}
                  </select>
                </Field>
                <Field label="Items">
                  <input className="ds-input w-full" type="number" min={1} max={30}
                         value={s.item_count}
                         onChange={(e) => setSection(i, { item_count: Number(e.target.value) })} />
                </Field>
                <Field label="Prep seconds">
                  <input className="ds-input w-full" type="number" min={0} max={300}
                         value={s.prep_seconds}
                         onChange={(e) => setSection(i, { prep_seconds: Number(e.target.value) })} />
                </Field>
                <Field label="Answer seconds">
                  <input className="ds-input w-full" type="number" min={5} max={600}
                         value={s.response_seconds}
                         onChange={(e) => setSection(i, { response_seconds: Number(e.target.value) })} />
                </Field>
                <Field label="Prompt plays"
                       hint="0 = nothing is played. 1 = one-shot, enforced server-side.">
                  <input className="ds-input w-full" type="number" min={0} max={3}
                         value={s.prompt_plays_allowed}
                         onChange={(e) => setSection(i, {
                           prompt_plays_allowed: Number(e.target.value),
                         })} />
                </Field>
                <Field label="Counts for"
                       hint={weightHint(s.weight ?? 1)}>
                  <input className="ds-input w-full" type="number" min={0} max={10}
                         step={0.5} value={s.weight ?? 1}
                         onChange={(e) => setSection(i, {
                           weight: Number(e.target.value),
                         })} />
                </Field>
              </div>
              <div className="mt-2">
                <Field label="Instructions">
                  <input className="ds-input w-full" value={s.instructions}
                         onChange={(e) => setSection(i, { instructions: e.target.value })}
                         placeholder="What the student is told before this section." />
                </Field>
              </div>

              <SectionPool
                taskType={s.task_type}
                value={s.selection ?? {}}
                onChange={(selection) => setSection(i, { selection })}
              />
            </div>
          ))}
        </div>
      </div>

      <div className="flex gap-2">
        <button className="btn btn-primary btn-sm ds-focus"
                disabled={busy || !draft.name.trim() || draft.sections.length === 0}
                onClick={onSave}>
          {busy ? "Saving…" : "Save as draft"}
        </button>
        <button className="btn btn-ghost btn-sm ds-focus" onClick={onCancel}>
          Cancel
        </button>
      </div>
      <p className="text-[10px] text-muted leading-relaxed">
        Saving does not publish. Review the sections, then publish from the
        profile above.
      </p>
    </div>
  );
}

/** Drop the filters only a Speaking bank can honour. */
function dropClassification(sel: SectionSelection | undefined): SectionSelection {
  const { topics, roles, industries, languages, ...rest } = sel ?? {};
  return rest;
}

/** Which bank a section draws on, and how it draws.
 *
 *  Collapsed until it is configured, because most sections want the default —
 *  every published item of the task type, at random — and a panel of six
 *  empty controls on every section makes the common case look complicated. */
function SectionPool({ taskType, value, onChange }: {
  taskType: string;
  value: SectionSelection;
  onChange: (v: SectionSelection) => void;
}) {
  const classified = CLASSIFIED_TASK_TYPES.has(taskType);
  const configured =
    (value.industries?.length ?? 0) > 0 ||
    Object.keys(value.mix ?? {}).length > 0 ||
    (value.min_pool ?? 0) > 0;
  const [open, setOpen] = useState(configured);

  const set = (patch: Partial<SectionSelection>) => onChange({ ...value, ...patch });

  const toggleIndustry = (name: string) => {
    const have = value.industries ?? [];
    set({
      industries: have.includes(name)
        ? have.filter((x) => x !== name)
        : [...have, name],
    });
  };

  const setShare = (band: string, share: number) => {
    const mix = { ...(value.mix ?? {}) };
    if (share > 0) mix[band] = share;
    else delete mix[band];
    set({ mix });
  };

  if (!open) {
    return (
      <button
        className="btn btn-ghost btn-sm ds-focus mt-2"
        onClick={() => setOpen(true)}
      >
        Narrow the item pool
      </button>
    );
  }

  return (
    <div className="ds-inset p-3 mt-2 space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-bold uppercase tracking-wider text-muted">
          Item pool
        </span>
        <button className="btn btn-ghost btn-sm ds-focus"
                onClick={() => { onChange({}); setOpen(false); }}>
          Use everything
        </button>
      </div>

      {classified ? (
        <Field label="Industry"
               hint="General material stays eligible whatever you pick — a banking round built only from banking sentences would be a five-item test.">
          <div className="flex flex-wrap gap-1.5">
            {INDUSTRIES.map((name) => {
              const on = (value.industries ?? []).includes(name);
              return (
                <button
                  key={name}
                  onClick={() => toggleIndustry(name)}
                  className="ds-inset px-2 py-1 text-[11px] ds-focus"
                  style={on ? {
                    borderColor: "var(--primary)",
                    background: "color-mix(in srgb, var(--primary) 12%, transparent)",
                  } : undefined}
                >
                  {name.toUpperCase()}
                </button>
              );
            })}
          </div>
        </Field>
      ) : (
        <p className="text-[10px] text-muted leading-relaxed">
          Only speaking items carry an industry, role or topic. This section
          draws on a different bank, so difficulty is the only thing to narrow
          on.
        </p>
      )}

      <Field label="Difficulty mix"
             hint="Relative shares. Leave all three at zero to draw at random. A share the bank cannot fill is reported on the result rather than quietly dropped.">
        <div className="grid grid-cols-3 gap-2">
          {BANDS.map((band) => (
            <label key={band} className="block">
              <span className="block text-[10px] text-muted mb-1">{band}</span>
              <input className="ds-input w-full" type="number" min={0} max={10}
                     value={value.mix?.[band] ?? 0}
                     onChange={(e) => setShare(band, Number(e.target.value))} />
            </label>
          ))}
        </div>
      </Field>

      <Field label="Smallest usable pool"
             hint="Refuse to publish unless this many items qualify. A bank the size of the section serves the same test on every retake, and the retake then measures memory.">
        <input className="ds-input w-full" type="number" min={0} max={500}
               value={value.min_pool ?? 0}
               onChange={(e) => set({ min_pool: Number(e.target.value) })} />
      </Field>
    </div>
  );
}

function Field({ label, hint, children }: {
  label: string; hint?: string; children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="block text-[10px] font-bold uppercase tracking-wider text-muted mb-1">
        {label}
      </span>
      {children}
      {hint && <span className="block text-[10px] text-muted mt-1">{hint}</span>}
    </label>
  );
}

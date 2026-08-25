"use client";
import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  AlertTriangle, Building2, Clock, Layers, Mic, Repeat, ShieldCheck, Volume2,
} from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { Badge, EmptyState, ErrorNote, PageHeader, Section, Skeleton } from "@/components/ui";
import { api, ApiError, attemptApi, type ProfileSection, type SimulationProfile } from "@/lib/api";
import { durationLine } from "@/lib/duration";
import { taskLabel } from "@/lib/tasks";
import { useData } from "@/lib/useData";

export default function SimulatePage() {
  return (
    <RequireAuth roles={["student"]}>
      <Simulate />
    </RequireAuth>
  );
}


/** Families, in the order a student should meet them.
 *
 *  The diagnostic first because it is the one that tells them where they are;
 *  company rounds next because that is what they are actually preparing for;
 *  the vendor-style simulations after, as the longer-form practice. */
const FAMILIES: { key: string; label: string; blurb: string }[] = [
  {
    key: "diagnostic",
    label: "Diagnostic",
    blurb: "Where you are now. Take this first — everything else is measured against it.",
  },
  {
    key: "company_round",
    label: "Company rounds",
    blurb:
      "Shaped like the communication round each employer actually runs. Practice for the one you are sitting.",
  },
  {
    key: "vendor",
    label: "Full simulations",
    blurb:
      "Longer assessments in the shape of the automated tests used across campus hiring.",
  },
  {
    key: "professional",
    label: "Professional English",
    blurb:
      "An hour, all four skills, workplace material throughout. Not shaped like anyone else's test — sit it once and read the report properly.",
  },
  { key: "other", label: "Other", blurb: "" },
];

/** What each style is called on a chip. Short, because it is a chip. */
const STYLE_LABEL: Record<string, string> = {
  diagnostic: "Diagnostic",
  company_round: "Company rounds",
  versant_style: "Versant-style",
  svar_style: "SVAR-style",
  speechx_style: "SpeechX-style",
  professional: "Professional English",
  drill: "Drill",
};

function familyOf(profile: SimulationProfile): string {
  if (profile.style === "diagnostic") return "diagnostic";
  if (profile.style === "company_round") return "company_round";
  if (profile.style === "professional") return "professional";
  if (profile.style.endsWith("_style")) return "vendor";
  return "other";
}

function Simulate() {
  const router = useRouter();
  const { data, loading, error } = useData(() => api.studentProfiles().then((rows) => rows.filter((r) => r.style !== "drill")));
  const home = useData(() => api.studentHome());
  const [starting, setStarting] = useState("");
  const [startError, setStartError] = useState("");
  const [company, setCompany] = useState("");
  const [style, setStyle] = useState("");

  const profiles = useMemo(() => data ?? [], [data]);

  // Only companies that actually have a published round. A filter offering a
  // company with nothing behind it is a dead end dressed as a choice.
  const companies = useMemo(() => {
    const seen: string[] = [];
    for (const p of profiles) {
      if (p.company && !seen.includes(p.company)) seen.push(p.company);
    }
    return seen.sort();
  }, [profiles]);

  // The vendor-style simulations are the longest and sit last, so without
  // this a student has to scroll past every company round to discover they
  // exist. Built from what is actually published, in the order below.
  const styles = useMemo(() => {
    const order = ["diagnostic", "company_round", "versant_style",
                   "svar_style", "speechx_style", "professional"];
    const present = new Set(profiles.map((p) => p.style));
    return order.filter((k) => present.has(k));
  }, [profiles]);

  async function start(profileId: string) {
    setStarting(profileId);
    setStartError("");
    try {
      const attempt = await attemptApi.start(profileId, "practice");
      // Straight into the environment check — the runner is never entered
      // without one, because a dead microphone must not cost an attempt.
      router.push(`/attempt/${attempt.attempt_id}/check`);
    } catch (err) {
      setStartError(err instanceof ApiError ? err.detail : "Could not start the simulation");
      setStarting("");
    }
  }

  if (loading) return <Skeleton rows={5} />;
  if (error) return <ErrorNote message={error} />;

  const consented = home.data?.consent_given ?? false;

  const grouped = FAMILIES.map((family) => ({
    ...family,
    profiles: profiles.filter(
      (p) =>
        familyOf(p) === family.key &&
        (!style || p.style === style) &&
        (!company || family.key !== "company_round" || p.company === company),
    ),
  })).filter((f) => f.profiles.length > 0);

  return (
    <>
      <PageHeader
        title="Simulations"
        sub="Format, timing and pressure matched to the real thing. Prompts play once, timers do not pause, and there is no going back a question — because none of that is available on the day either."
      />

      {!home.loading && !consented && (
        <div className="ds-card p-4 mb-4 flex items-start gap-3"
             style={{ borderColor: "var(--rag-amber)" }}>
          <ShieldCheck size={15} className="shrink-0 mt-0.5"
                       style={{ color: "var(--rag-amber)" }} />
          <div>
            <div className="text-sm font-bold mb-0.5">Consent first</div>
            <p className="text-xs text-muted leading-relaxed mb-2">
              Nothing is recorded until you have read what happens to your voice
              and agreed to it. It takes a minute.
            </p>
            <Link href="/consent" className="btn btn-primary btn-sm ds-focus">
              Read and choose
            </Link>
          </div>
        </div>
      )}

      {startError && <div className="mb-4"><ErrorNote message={startError} /></div>}

      <div className="ds-card p-3 mb-4 space-y-3">
        {styles.length > 1 && (
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Layers size={13} className="text-muted" />
              <span className="text-[11px] font-bold uppercase tracking-wider text-muted">
                Which test are you preparing for?
              </span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              <FilterChip label="All" active={style === ""}
                          onClick={() => { setStyle(""); setCompany(""); }} />
              {styles.map((k) => (
                <FilterChip
                  key={k}
                  label={STYLE_LABEL[k] ?? k}
                  active={style === k}
                  onClick={() => {
                    const next = style === k ? "" : k;
                    setStyle(next);
                    // A company filter is meaningless once the student has
                    // narrowed to a vendor format, and leaving it set would
                    // silently hide rounds when they switch back.
                    if (next !== "company_round") setCompany("");
                  }}
                />
              ))}
            </div>
          </div>
        )}

        {companies.length > 0 && (style === "" || style === "company_round") && (
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Building2 size={13} className="text-muted" />
              <span className="text-[11px] font-bold uppercase tracking-wider text-muted">
                Which companies are you targeting?
              </span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              <FilterChip label="All" active={company === ""} onClick={() => setCompany("")} />
              {companies.map((c) => (
                <FilterChip key={c} label={c} active={company === c}
                            onClick={() => setCompany(company === c ? "" : c)} />
              ))}
            </div>
          </div>
        )}
      </div>

      {grouped.length === 0 ? (
        <div className="ds-card">
          {style || company ? (
            <EmptyState icon={Mic} title="Nothing matches that filter"
                        desc="Clear the filters above to see everything published." />
          ) : (
            <EmptyState icon={Mic} title="No published simulations"
                        desc="Your institution has not published a profile yet." />
          )}
        </div>
      ) : (
        <div className="space-y-6">
          {grouped.map((family) => (
            <div key={family.key}>
              <div className="mb-2">
                <h2 className="text-sm font-bold">{family.label}</h2>
                {family.blurb && (
                  <p className="text-[11px] text-muted leading-relaxed mt-0.5">
                    {family.blurb}
                  </p>
                )}
              </div>
              <div className="space-y-4">
                {family.profiles.map((p) => (
                  <ProfileCard key={p.id} profile={p} consented={consented}
                               starting={starting === p.id}
                               onStart={() => void start(p.id)} />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Nominative use, stated once and plainly. These rounds imitate a
          format; no employer or test vendor has reviewed or endorsed any of
          it, and saying so in the product is cheaper than being asked. */}
      <p className="text-[10px] text-muted leading-relaxed mt-6">
        Company and test names are used only to describe the shape of the round
        being practised. Every question here is written by us — none is taken
        from any real assessment — and no employer or assessment provider is
        affiliated with, has reviewed, or endorses these simulations.
      </p>
    </>
  );
}

function FilterChip({ label, active, onClick }: {
  label: string; active: boolean; onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="chip ds-focus"
      style={{
        background: active ? "var(--primary)" : "var(--surface)",
        color: active ? "var(--on-primary, #fff)" : "var(--muted)",
        cursor: "pointer",
        border: "1px solid var(--border)",
      }}
    >
      {label}
    </button>
  );
}

function ProfileCard({ profile, consented, starting, onStart }: {
  profile: SimulationProfile; consented: boolean; starting: boolean;
  onStart: () => void;
}) {
  return (
    <Section
      title={profile.name}
      action={
        <div className="flex items-center gap-2">
          {profile.is_baseline && <Badge tone="var(--accent)">Baseline</Badge>}
          {profile.company && <Badge tone="var(--primary)">{profile.company}</Badge>}
          <button
            className="btn btn-primary btn-sm ds-focus"
            disabled={!consented || starting}
            onClick={onStart}
            title={consented ? "" : "Consent is required before recording"}
          >
            {starting ? "Starting…" : "Start"}
          </button>
        </div>
      }
    >
      <p className="text-xs text-muted mb-3 leading-relaxed">{profile.description}</p>

      {profile.what_to_expect.length > 0 && (
        <div className="ds-inset p-3 mb-3">
          <div className="flex items-center gap-1.5 mb-1.5">
            <AlertTriangle size={12} style={{ color: "var(--rag-amber)" }} />
            <span className="text-[11px] font-bold">What catches people out</span>
          </div>
          <ul className="text-[11px] text-muted leading-relaxed space-y-0.5">
            {profile.what_to_expect.map((line) => (
              <li key={line}>· {line}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Said before they start, not discovered afterwards. A student who
          thinks they have practised the whole test has been misled by the
          omission, whatever the sections page technically showed. */}
      {profile.not_included && (
        <div className="ds-card p-3 mb-3 text-[11px] text-muted leading-relaxed"
             style={{ borderColor: "var(--border)" }}>
          <span className="font-bold" style={{ color: "var(--fg)" }}>
            Not in this simulation.{" "}
          </span>
          {profile.not_included}{" "}
          <Link href="/quiz" className="underline ds-focus">Go to Practice</Link>
        </div>
      )}

      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-2">
        {profile.sections.map((s) => <SectionCard key={s.id} section={s} />)}
      </div>
      {/* Not "up to": the typed and chosen sections have no clock, and the
          sitting is bounded by the server's hard stop, not by the estimate.
          See lib/duration.ts. */}
      <div className="text-[11px] text-muted mt-3">
        {profile.sections.length} sections · {durationLine(profile)}
      </div>
      {/* Which configuration of the real thing this is -- one quiet line,
          not a legal notice. The card's job is to say what they will
          practise; this says where that shape came from. */}
      {profile.provenance && (
        <p className="text-[10px] text-muted mt-1.5 leading-relaxed opacity-80">
          {profile.provenance}
        </p>
      )}
    </Section>
  );
}

function SectionCard({ section }: { section: ProfileSection }) {
  const oneShot = section.prompt_plays_allowed === 1 && !section.allow_replay;
  return (
    <div className="ds-inset p-3">
      <div className="flex items-center justify-between gap-2 mb-1.5">
        <span className="text-xs font-bold">{section.title}</span>
        <span className="text-[10px] text-muted">{section.item_count} items</span>
      </div>
      <div className="text-[11px] text-muted mb-2">
        {taskLabel(section.task_type)}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {section.prep_seconds > 0 ? (
          <span className="chip" style={{ background: "var(--surface)", color: "var(--muted)" }}>
            <Clock size={10} /> {section.prep_seconds}s prep
          </span>
        ) : (
          // Absence of preparation time is the single most common surprise in
          // a company round, so it is stated rather than left to be inferred.
          <span className="chip" style={{
            background: "color-mix(in srgb, var(--rag-amber) 14%, transparent)",
            color: "var(--rag-amber)",
          }}>
            <Clock size={10} /> no prep
          </span>
        )}
        {/* A typed or chosen answer with no clock is untimed, and saying
            "0s to answer" about it is a defect, not a detail. */}
        <span className="chip" style={{ background: "var(--surface)", color: "var(--muted)" }}>
          {section.response_seconds > 0
            ? <><Mic size={10} /> {section.response_seconds}s to answer</>
            : <><Clock size={10} /> Untimed</>}
        </span>
        {section.prompt_plays_allowed > 0 && (
          <span className="chip" style={{
            background: "color-mix(in srgb, var(--rag-amber) 14%, transparent)",
            color: "var(--rag-amber)",
          }}>
            {oneShot ? <><Volume2 size={10} /> plays once</> : <><Repeat size={10} /> {section.prompt_plays_allowed} plays</>}
          </span>
        )}
        {section.budget_seconds > 0 && (
          // The lettered section's budget, stated on every sub-section of it:
          // a candidate reading A2 should know A as a whole has ten minutes.
          <span className="chip" style={{ background: "var(--surface)", color: "var(--muted)" }}>
            <Clock size={10} /> {Math.round(section.budget_seconds / 60)}-min section budget
          </span>
        )}
      </div>
      {section.instructions && (
        <p className="text-[11px] text-muted mt-2 leading-relaxed">{section.instructions}</p>
      )}
    </div>
  );
}

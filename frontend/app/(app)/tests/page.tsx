"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AlertTriangle, Clock, Filter, Mic, ShieldCheck } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { StepGuide } from "@/components/StepGuide";
import {
  Badge, EmptyState, ErrorNote, PageHeader, Section, Skeleton,
} from "@/components/ui";
import { api, ApiError, attemptApi, type SimulationProfile } from "@/lib/api";
import { durationLine } from "@/lib/duration";
import { useData } from "@/lib/useData";

export default function TestsPage() {
  return (
    <RequireAuth roles={["student"]}>
      <Tests />
    </RequireAuth>
  );
}

/** The assessment library.
 *
 *  Every card starts its own test, right here. The first version linked each
 *  card to /simulate — a different screen where the student had to find the
 *  same test a second time and press Start there. Nobody asked for a detour;
 *  they clicked a test because they wanted to take it. So the card now has
 *  the Start button, it starts *that* test, and the only navigation that
 *  happens is the one the flow requires: into the microphone check.
 *
 *  The tests stay grouped by what they are *for* rather than by our internal
 *  `style` field, and each card states the cost before you commit — how
 *  long, how many questions, and the fact that prompts play once and there
 *  is no pause. Discovering "you cannot replay this" from a running clock is
 *  how a practice tool loses a student's trust in one item.
 */
function Tests() {
  const router = useRouter();
  const { data, loading, error } = useData(() => api.studentHome());
  const [starting, setStarting] = useState("");
  const [startError, setStartError] = useState("");
  const [companyFilter, setCompanyFilter] = useState("");

  const inProgressByProfile = new Map<string, string>();
  for (const a of data?.recent_attempts ?? []) {
    if ((a.status === "in_progress" || a.status === "created") && !inProgressByProfile.has(a.profile_id)) {
      inProgressByProfile.set(a.profile_id, a.id);
    }
  }

  if (loading) return <Skeleton rows={6} />;
  if (error) return <ErrorNote message={error} />;

  const consented = data?.consent_given ?? false;
  // Practice sessions (style "drill") are started from a result page, by the
  // weakness they train -- listing them here as "tests" would be confusing.
  const profiles = (data?.assigned_profiles ?? []).filter((p) => p.style !== "drill");
  const baseline = profiles.filter((p) => p.is_baseline);
  const company = profiles.filter((p) => !p.is_baseline && p.company);
  const formats = profiles.filter((p) => !p.is_baseline && !p.company);

  async function start(profileId: string) {
    setStarting(profileId);
    setStartError("");
    try {
      const attempt = await attemptApi.start(profileId, "practice");
      router.push(`/attempt/${attempt.attempt_id}/check`);
    } catch (err) {
      setStartError(err instanceof ApiError ? err.detail : "Could not start the test");
      setStarting("");
    }
  }

  function resume(attemptId: string) {
    router.push(`/attempt/${attemptId}/check`);
  }

  return (
    <>
      <PageHeader
        title="Take a test"
        sub="Timed, one attempt at a time, scored properly. Set aside a quiet ten to twenty minutes."
      />

      <StepGuide
        active={1}
        steps={[
          { label: "Pick a test below", detail: "Each card says how long it takes before you commit." },
          { label: "Press Start on its card", detail: "A microphone check runs first — the clock has not started yet." },
          { label: "Do it in one sitting", detail: "Timed, prompts may play once, no going back a question." },
          { label: "Read your report", detail: "What was measured, and the one change that moves it most." },
        ]}
      />

      {!consented && (
        <div className="ds-card p-4 mb-4 flex items-start gap-3"
             style={{ borderColor: "var(--rag-amber)" }}>
          <ShieldCheck size={15} className="shrink-0 mt-0.5"
                       style={{ color: "var(--rag-amber)" }} />
          <div>
            <div className="text-sm font-bold mb-0.5">One thing before any test: consent</div>
            <p className="text-xs text-muted leading-relaxed mb-2">
              Nothing is recorded until you have read what happens to your voice
              and agreed to it. It takes a minute, and the Start buttons below
              unlock the moment you have.
            </p>
            <Link href="/consent" className="btn btn-primary btn-sm ds-focus">
              Read and choose
            </Link>
          </div>
        </div>
      )}

      {startError && <div className="mb-4"><ErrorNote message={startError} /></div>}

      {/* Everyone needs this first, and it is the only test that is a
          prerequisite, so it is not left for the student to infer. */}
      {baseline.length > 0 && !data?.baseline_done && (
        <div className="ds-card p-4 mb-4" style={{ borderColor: "var(--primary)" }}>
          <div className="text-sm font-bold mb-1">Start with this one</div>
          <p className="text-xs text-muted leading-relaxed">
            Your first test sets the starting point everything else is measured
            against. It is short, and you only do it once.
          </p>
        </div>
      )}

      {baseline.length > 0 && (
        <Section title="Your first test" className="mb-4">
          <div className="grid md:grid-cols-2 gap-3">
            {baseline.map((p) => (
              <TestCard key={p.id} profile={p} first consented={consented}
                        starting={starting === p.id} anyStarting={starting !== ""}
                        inProgressAttemptId={inProgressByProfile.get(p.id)}
                        onStart={() => void start(p.id)}
                        onResume={() => resume(inProgressByProfile.get(p.id)!)} />
            ))}
          </div>
        </Section>
      )}

      {formats.length > 0 && (
        <Section title="Practice tests" className="mb-4">
          <p className="text-xs text-muted mb-3 leading-relaxed">
            Built in the shape of the tests employers use — same section order,
            same timings, same one-shot audio. The questions are ours.
          </p>
          <div className="grid md:grid-cols-2 gap-3">
            {formats.map((p) => (
              <TestCard key={p.id} profile={p} consented={consented}
                        starting={starting === p.id} anyStarting={starting !== ""}
                        inProgressAttemptId={inProgressByProfile.get(p.id)}
                        onStart={() => void start(p.id)}
                        onResume={() => resume(inProgressByProfile.get(p.id)!)} />
            ))}
          </div>
        </Section>
      )}

      {company.length > 0 && (
        <Section title="Company rounds">
          <p className="text-xs text-muted mb-3 leading-relaxed">
            Shaped like the communication round a particular employer runs.
            Pick a company to see its rounds, or view all.
          </p>
          {(() => {
            const companyNames = Array.from(new Set(company.map((p) => p.company))).sort();
            const filteredCompany = companyFilter
              ? company.filter((p) => p.company === companyFilter)
              : company;
            return (
              <>
                {companyNames.length > 1 && (
                  <div className="flex items-center gap-1.5 mb-3">
                    <Filter size={12} className="text-muted" />
                    <select
                      className="ds-input text-xs py-1 px-2"
                      style={{ minWidth: 140 }}
                      value={companyFilter}
                      onChange={(e) => setCompanyFilter(e.target.value)}
                    >
                      <option value="">All Companies</option>
                      {companyNames.map((cn) => <option key={cn} value={cn}>{cn}</option>)}
                    </select>
                  </div>
                )}
                <div className="grid md:grid-cols-2 gap-3">
                  {filteredCompany.map((p) => (
                    <TestCard key={p.id} profile={p} consented={consented}
                              starting={starting === p.id} anyStarting={starting !== ""}
                              inProgressAttemptId={inProgressByProfile.get(p.id)}
                              onStart={() => void start(p.id)}
                              onResume={() => resume(inProgressByProfile.get(p.id)!)} />
                  ))}
                </div>
              </>
            );
          })()}
        </Section>
      )}

      {profiles.length === 0 && (
        <EmptyState icon={Mic} title="No tests yet"
                    desc="Your institution has not published one. Practice is still open in the meantime." />
      )}
    </>
  );
}

function TestCard({ profile: p, first, consented, starting, anyStarting, inProgressAttemptId, onStart, onResume }: {
  profile: SimulationProfile; first?: boolean; consented: boolean;
  starting: boolean; anyStarting: boolean; inProgressAttemptId?: string;
  onStart: () => void; onResume: () => void;
}) {
  const items = p.sections.reduce((n, s) => n + s.item_count, 0);
  const oneShot = p.sections.some((s) => s.prompt_plays_allowed > 0 && !s.allow_replay);

  return (
    <div className="ds-card p-4 flex flex-col">
      <div className="flex items-start justify-between gap-2">
        <div className="text-sm font-bold">{p.name}</div>
        {first && <Badge tone="var(--primary)">Do this first</Badge>}
        {p.company && <Badge tone="var(--accent)">{p.company}</Badge>}
        {inProgressAttemptId && <Badge tone="var(--rag-green)">In Progress</Badge>}
      </div>

      <p className="text-[11px] text-muted mt-1.5 leading-relaxed">{p.description}</p>

      {/* The cost, before you start rather than after the first question. */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-3 pt-3 border-t border-border">
        <span className="flex items-center gap-1 text-[11px] text-muted">
          <Clock size={11} /> {durationLine(p)}
        </span>
        <span className="text-[11px] text-muted">{items} questions</span>
        <span className="text-[11px] text-muted">
          {p.sections.length} part{p.sections.length === 1 ? "" : "s"}
        </span>
      </div>

      {oneShot && (
        <div className="flex items-start gap-1.5 mt-2">
          <AlertTriangle size={11} className="shrink-0 mt-0.5"
                         style={{ color: "var(--rag-amber)" }} />
          <span className="text-[10px] text-muted leading-relaxed">
            Some prompts play once and cannot be repeated. Do it somewhere quiet,
            in one sitting.
          </span>
        </div>
      )}

      {/* The button starts *this* test — no detour through another screen.
          Saying what happens next on the button's own row is what makes it
          safe to press: the clock does not start at Start, the mic check
          does. */}
      <div className="flex items-center justify-between gap-2 mt-3 pt-3 border-t border-border">
        <span className="text-[10px] text-muted leading-relaxed">
          {consented ? "Mic check first, then the test begins."
                     : "Locked until you have consented above."}
        </span>
        <div className="flex items-center gap-2 shrink-0">
          {inProgressAttemptId && (
            <button
              className="btn btn-sm ds-focus"
              style={{ background: "var(--rag-green)", color: "white" }}
              disabled={!consented || anyStarting}
              onClick={onResume}
              title={consented ? "" : "Consent is required before recording"}
            >
              Resume
            </button>
          )}
          <button
            className="btn btn-primary btn-sm ds-focus"
            disabled={!consented || anyStarting}
            onClick={onStart}
            title={consented ? "" : "Consent is required before recording"}
          >
            {starting ? "Starting…" : "Start"}
          </button>
        </div>
      </div>
    </div>
  );
}

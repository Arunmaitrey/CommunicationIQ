"use client";
import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { Badge, ErrorNote, PageHeader, Section, Skeleton } from "@/components/ui";
import { Evidence, Highlights, Plan, Skills, Summary } from "@/components/Report";
import { api, type Attempt } from "@/lib/api";
import { DIMENSION_LABEL, DIMENSION_MEANING } from "@/lib/dimensions";
import { useData } from "@/lib/useData";

export default function StudentResultPage() {
  return (
    <RequireAuth roles={["trainer", "tenant_admin"]}>
      <StudentResult />
    </RequireAuth>
  );
}

/**
 *  What one student actually scored, for the trainer coaching them.
 *
 *  A trainer could see an overall number on the cohort table and a mastery
 *  curve on the student, and had no way to open the report behind either --
 *  so the question coaching starts from, "why is this number what it is", had
 *  no answer anywhere in the product.
 *
 *  The same report the student sees. A coaching view with the caveats removed
 *  would be a different claim about the same measurements, and a trainer
 *  repeating it to a student would be repeating something we did not say.
 */
function StudentResult() {
  const { id, userId } = useParams<{ id: string; userId: string }>();
  const attempts = useData(() => api.cohortStudentAttempts(userId), [userId]);
  const [chosen, setChosen] = useState<string>("");

  const rows = attempts.data ?? [];
  const scored = rows.filter((a) => a.scored_at || a.status === "scored");
  const current = chosen || scored[0]?.id || "";

  return (
    <>
      <Link href={`/cohorts/${id}`}
            className="text-[11px] text-muted inline-flex items-center gap-1 mb-3 ds-focus">
        <ArrowLeft size={12} /> Back to cohort
      </Link>

      {attempts.loading ? <Skeleton rows={5} />
        : attempts.error ? <ErrorNote message={attempts.error} />
        : rows.length === 0 ? (
          <Section title="Nothing sat yet">
            <p className="text-xs text-muted leading-relaxed">
              This student has not sat an assessment. There is no report to
              read, which is not the same as a report that says zero.
            </p>
          </Section>
        ) : (
        <>
          <PageHeader title="Student report"
                      sub={`${rows.length} attempt${rows.length === 1 ? "" : "s"}`} />

          <Section title="Attempts" className="mb-4">
            <div className="space-y-1.5">
              {rows.map((a) => (
                <AttemptRow key={a.id} attempt={a} active={a.id === current}
                            onPick={() => setChosen(a.id)} />
              ))}
            </div>
          </Section>

          {current
            ? <Report attemptId={current} />
            : (
              <Section title="No scored attempt">
                <p className="text-xs text-muted leading-relaxed">
                  Nothing this student has started has finished scoring yet.
                  An unfinished attempt has no report behind it, and showing a
                  zero in its place would describe them wrongly.
                </p>
              </Section>
            )}
        </>
      )}
    </>
  );
}

function AttemptRow({ attempt, active, onPick }: {
  attempt: Attempt; active: boolean; onPick: () => void;
}) {
  const done = attempt.status === "scored" || !!attempt.scored_at;
  return (
    <button onClick={onPick} disabled={!done}
            className={`ds-card p-2.5 w-full text-left ds-focus ${
              done ? "" : "opacity-60 cursor-default"}`}
            style={active ? { boxShadow: "0 0 0 1px var(--primary)" } : undefined}>
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs font-medium">
          {attempt.profile_name || "Assessment"} · attempt {attempt.attempt_number}
        </span>
        <Badge tone={done ? "var(--rag-green)" : "var(--muted)"}>
          {attempt.status}
        </Badge>
      </div>
      {!done && (
        // Named rather than hidden. A trainer seeing four attempts and three
        // reports should be told why, not left to work it out.
        <p className="text-[10px] text-muted mt-1">
          Not finished, so there is no report behind it.
        </p>
      )}
    </button>
  );
}

function Report({ attemptId }: { attemptId: string }) {
  const { data, loading, error } = useData(
    () => api.studentResult(attemptId), [attemptId]);

  if (loading) return <Skeleton rows={6} />;
  if (error) return <ErrorNote message={error} />;
  if (!data) return null;

  return (
    <>
      <Summary text={data.summary} />

      <Section title={data.profile_name} className="mb-4">
        <div className="flex items-baseline gap-2">
          <span className="text-3xl font-bold tabular-nums">
            {data.overall === null ? "—" : data.overall}
          </span>
          <span className="text-xs text-muted">
            of {data.scale_max} · {data.band}
          </span>
        </div>
        {!data.calibrated && data.calibration_note && (
          <p className="text-[11px] text-muted mt-2 leading-relaxed">
            {data.calibration_note}
          </p>
        )}
      </Section>

      <Section title="Measures" className="mb-4">
        <div className="space-y-2">
          {Object.entries(data.dimensions).map(([key, value]) => (
            <div key={key} className="flex items-baseline justify-between gap-3">
              <span className="text-xs">
                {DIMENSION_LABEL[key] ?? key}
                {DIMENSION_MEANING[key] && (
                  <span className="block text-[10px] text-muted">
                    {DIMENSION_MEANING[key]}
                  </span>
                )}
              </span>
              <span className="text-sm font-bold tabular-nums">{value}</span>
            </div>
          ))}
        </div>
        {Object.keys(data.unscored).length > 0 && (
          <div className="mt-3 pt-3 border-t border-border space-y-1">
            {Object.entries(data.unscored).map(([key, why]) => (
              <p key={key} className="text-[10px] text-muted leading-relaxed">
                <strong>{DIMENSION_LABEL[key] ?? key}:</strong> {why}
              </p>
            ))}
          </div>
        )}
      </Section>

      <Skills skills={data.skills ?? []} sections={data.sections ?? []}
              scaleMin={data.scale_min} scaleMax={data.scale_max} />
      <Highlights strengths={data.strengths} weaknesses={data.weaknesses} />
      <Plan result={data} />
      <Evidence evidence={data.evidence} />
    </>
  );
}

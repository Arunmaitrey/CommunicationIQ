"use client";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { ErrorNote, PageHeader, Section, Skeleton } from "@/components/ui";
import { Evidence, Highlights, Plan, Skills, Summary } from "@/components/Report";
import { api } from "@/lib/api";
import { DIMENSION_LABEL, DIMENSION_MEANING } from "@/lib/dimensions";
import { useData } from "@/lib/useData";

export default function InvitationResultPage() {
  return (
    <RequireAuth roles={["tenant_admin"]}>
      <InvitationResult />
    </RequireAuth>
  );
}

/**
 *  What the candidate scored, for the employer who invited them.
 *
 *  This is the last step of the external-hiring flow and it did not exist.
 *  An institution could build an assessment, send a link, watch the
 *  invitation turn "redeemed" -- and had no way to read the result. The
 *  candidate's own report is scoped to the person who sat it, and every
 *  trainer route is cohort-scoped, which a candidate is not in.
 *
 *  Deliberately the same report the candidate sees, with the same caveats
 *  attached. An employer-facing version with the hedging stripped out would
 *  be a different claim about the same numbers.
 */
function InvitationResult() {
  const { id } = useParams<{ id: string }>();
  const { data, loading, error } = useData(() => api.invitationResult(id), [id]);
  // Whose result this is. A report reached from a list of candidates and
  // carrying no name on it is the wrong report waiting to be read as the
  // right one.
  const invitations = useData(() => api.tenantInvitations());
  const invitation = (invitations.data ?? []).find((row) => row.id === id);

  return (
    <>
      <Link href="/tenant/invitations"
            className="text-[11px] text-muted inline-flex items-center gap-1 mb-3 ds-focus">
        <ArrowLeft size={12} /> All invitations
      </Link>

      {loading ? <Skeleton rows={6} />
        : error ? <ErrorNote message={error} />
        : !data ? <ErrorNote message="No result for this invitation yet." />
        : (
        <>
          <PageHeader
            title={invitation?.invited_name || "Candidate"}
            sub={`${data.profile_name} · attempt ${data.attempt_number} · `
                 + `${data.status}`
                 + (invitation?.reference ? ` · ${invitation.reference}` : "")}
          />

          {/* The candidate's own words, marked as theirs.
              The summary is written in the second person, for the person who
              sat the assessment. Shown to an employer without saying so, "You
              scored 41.7" reads as addressed to the reader. */}
          <p className="text-[10px] font-bold uppercase tracking-wider text-muted mb-1">
            What {invitation?.invited_name || "the candidate"} was shown
          </p>
          <Summary text={data.summary} />

          <Section title="Overall" className="mb-4">
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
            {data.cefr_level && (
              <div className="ds-inset p-3 mt-3">
                <div className="text-[11px] font-bold uppercase tracking-wide text-muted">
                  CEFR {data.cefr_level} · indicative
                </div>
                <p className="text-[11px] text-muted mt-1 leading-relaxed">
                  {data.cefr_caveat}
                </p>
              </div>
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
      )}
    </>
  );
}

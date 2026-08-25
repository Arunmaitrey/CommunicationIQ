"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { AlertTriangle, CheckCircle2, CircleDashed, TrendingDown } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import {
  Avatar, Badge, ErrorNote, PageHeader, Section, Skeleton, StatCard, Table,
} from "@/components/ui";
import { api } from "@/lib/api";
import { READINESS } from "@/lib/roles";
import { useData } from "@/lib/useData";

export default function CohortDetailPage() {
  return (
    <RequireAuth roles={["trainer"]}>
      <CohortDetail />
    </RequireAuth>
  );
}

function CohortDetail() {
  const { id } = useParams<{ id: string }>();
  const readiness = useData(() => api.cohortReadiness(id), [id]);
  const students = useData(() => api.cohortStudents(id), [id]);

  if (readiness.loading || students.loading) return <Skeleton rows={6} />;
  if (readiness.error) return <ErrorNote message={readiness.error} />;
  if (!readiness.data) return null;

  const r = readiness.data;

  return (
    <>
      <PageHeader
        title={r.cohort_name}
        sub={r.days_to_drive != null
          ? `${r.assessed} of ${r.total} assessed · ${r.days_to_drive} days to the drive`
          : `${r.assessed} of ${r.total} assessed · no drive date set`}
      />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
        <StatCard icon={CheckCircle2} label="Placement ready" value={r.placement_ready}
                  tone="var(--rag-green)" />
        <StatCard icon={TrendingDown} label="Needs training" value={r.needs_training}
                  tone="var(--rag-amber)" />
        <StatCard icon={AlertTriangle} label="High risk" value={r.high_risk}
                  tone="var(--rag-red)" />
        <StatCard icon={CircleDashed} label="Not started" value={r.not_started}
                  tone="var(--muted)" sub={r.average_overall != null ? `cohort average ${r.average_overall}` : undefined} />
      </div>

      <Section title="Students">
        {students.error ? <ErrorNote message={students.error} /> : (
          <Table
            columns={["Student", "Roll", "L1", "Attempts", "Overall", "Readiness", "Last active"]}
            rows={(students.data ?? []).map((s) => {
              const band = READINESS[s.readiness] ?? READINESS.not_started;
              return [
                <Link key="n" href={`/cohorts/${id}/students/${s.user.id}`}
                      className="flex items-center gap-2 ds-focus">
                  <Avatar name={s.user.full_name} size={22} />
                  <span className="font-medium underline decoration-dotted">
                    {s.user.full_name}
                  </span>
                  {s.flagged && <Badge tone="var(--rag-red)">Flagged</Badge>}
                </Link>,
                s.user.roll_number,
                s.user.l1_language || "—",
                s.attempts,
                <span key="o" className="font-bold">{s.overall_score ?? "—"}</span>,
                <Badge key="b" tone={band.color}>{band.label}</Badge>,
                s.days_since_activity != null ? `${s.days_since_activity}d ago` : "never",
              ];
            })}
          />
        )}
      </Section>
    </>
  );
}

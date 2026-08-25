"use client";
import { useEffect, useState } from "react";
import { RequireAuth } from "@/components/RequireAuth";
import { Badge, ErrorNote, PageHeader, Section, Skeleton, Table } from "@/components/ui";
import { api, type CohortReadiness } from "@/lib/api";
import { READINESS } from "@/lib/roles";
import { useData } from "@/lib/useData";

export default function TenantReadinessPage() {
  return (
    <RequireAuth roles={["tenant_admin"]}>
      <Readiness />
    </RequireAuth>
  );
}

function Readiness() {
  const cohorts = useData(() => api.tenantCohorts());
  const [rows, setRows] = useState<CohortReadiness[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!cohorts.data) return;
    let live = true;
    // A tenant admin reads readiness through the same cohort-scoped endpoint a
    // trainer uses — one definition of the bands, one query, no second path
    // that could drift from it.
    Promise.all(cohorts.data.map((c) => api.cohortReadiness(c.id).catch(() => null)))
      .then((res) => { if (live) setRows(res.filter(Boolean) as CohortReadiness[]); })
      .catch(() => { if (live) setError("Could not load readiness"); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [cohorts.data]);

  const totals = rows.reduce(
    (acc, r) => ({
      total: acc.total + r.total,
      ready: acc.ready + r.placement_ready,
      training: acc.training + r.needs_training,
      risk: acc.risk + r.high_risk,
      none: acc.none + r.not_started,
    }),
    { total: 0, ready: 0, training: 0, risk: 0, none: 0 },
  );

  return (
    <>
      <PageHeader
        title="Cohort readiness"
        sub="Where the institution stands, by cohort. These bands describe practice progress on this platform — they are not a vendor score and are never presented as one."
      />

      {(cohorts.loading || loading) ? <Skeleton rows={5} /> :
       (cohorts.error || error) ? <ErrorNote message={cohorts.error || error} /> : (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
            <Tile label="Placement ready" value={totals.ready} total={totals.total} tone="var(--rag-green)" />
            <Tile label="Needs training" value={totals.training} total={totals.total} tone="var(--rag-amber)" />
            <Tile label="High risk" value={totals.risk} total={totals.total} tone="var(--rag-red)" />
            <Tile label="Not started" value={totals.none} total={totals.total} tone="var(--muted)" />
          </div>

          <Section title="By cohort">
            <Table
              columns={["Cohort", "Assessed", "Ready", "Needs training", "High risk", "Not started", "Average", "Drive in"]}
              rows={rows.map((r) => [
                <span key="n" className="font-medium">{r.cohort_name}</span>,
                `${r.assessed}/${r.total}`,
                <Badge key="a" tone={READINESS.placement_ready.color}>{r.placement_ready}</Badge>,
                <Badge key="b" tone={READINESS.needs_training.color}>{r.needs_training}</Badge>,
                <Badge key="c" tone={READINESS.high_risk.color}>{r.high_risk}</Badge>,
                <Badge key="d" tone={READINESS.not_started.color}>{r.not_started}</Badge>,
                <span key="e" className="font-bold">{r.average_overall ?? "—"}</span>,
                r.days_to_drive != null ? `${r.days_to_drive}d` : "—",
              ])}
            />
          </Section>
        </>
      )}
    </>
  );
}

function Tile({ label, value, total, tone }: {
  label: string; value: number; total: number; tone: string;
}) {
  const pct = total ? Math.round((value / total) * 100) : 0;
  return (
    <div className="ds-card p-4">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-muted">{label}</div>
      <div className="text-2xl font-bold mt-2 leading-none" style={{ color: tone }}>{value}</div>
      <div className="text-[11px] text-muted mt-1.5">{pct}% of {total} students</div>
    </div>
  );
}

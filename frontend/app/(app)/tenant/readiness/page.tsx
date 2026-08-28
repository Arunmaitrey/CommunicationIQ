"use client";
import { useEffect, useState } from "react";
import { Award, TrendingUp, Users } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { Badge, ErrorNote, PageHeader, Section, Skeleton, Table } from "@/components/ui";
import { api, type CohortReadiness, type StudentSummary } from "@/lib/api";
import { READINESS } from "@/lib/roles";
import { useData } from "@/lib/useData";
import {
  PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, Legend,
} from "recharts";

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
  const [topStudents, setTopStudents] = useState<StudentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!cohorts.data) return;
    let live = true;
    Promise.all(cohorts.data.map((c) => api.tenantCohortReadiness(c.id).catch(() => null)))
      .then((res) => { if (live) setRows(res.filter(Boolean) as CohortReadiness[]); })
      .catch(() => { if (live) setError("Could not load readiness"); })
      .finally(() => { if (live) setLoading(false); });

    // Fetch top students across all cohorts for ranking
    Promise.all(cohorts.data.map((c) => api.tenantCohortStudents(c.id).catch(() => [])))
      .then((res) => {
        if (!live) return;
        const all = res.flat().filter((s) => s.overall_score != null);
        all.sort((a, b) => (b.overall_score ?? 0) - (a.overall_score ?? 0));
        setTopStudents(all.slice(0, 10));
      });

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

          {/* Charts */}
          <div className="grid md:grid-cols-2 gap-4 mb-4">
            <Section title="Readiness distribution">
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={[
                        { name: "Placement ready", value: totals.ready },
                        { name: "Needs training", value: totals.training },
                        { name: "High risk", value: totals.risk },
                        { name: "Not started", value: totals.none },
                      ]}
                      cx="50%"
                      cy="50%"
                      innerRadius={45}
                      outerRadius={85}
                      paddingAngle={3}
                      dataKey="value"
                      label={({ name, percent }) => `${name} ${((percent ?? 0) * 100).toFixed(0)}%`}
                      labelLine={false}
                    >
                      <Cell fill="var(--rag-green)" />
                      <Cell fill="var(--rag-amber)" />
                      <Cell fill="var(--rag-red)" />
                      <Cell fill="var(--muted)" />
                    </Pie>
                    <Tooltip />
                    <Legend />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </Section>

            <Section title="Cohort averages">
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={rows.map((r) => ({ name: r.cohort_name, score: r.average_overall ?? 0, students: r.total }))} barSize={30}>
                    <XAxis dataKey="name" tick={{ fontSize: 10 }} />
                    <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} />
                    <Tooltip formatter={(v) => typeof v === "number" ? v.toFixed(1) : v} />
                    <Bar dataKey="score" radius={[4, 4, 0, 0]} fill="var(--primary)">
                      {rows.map((r, i) => (
                        <Cell key={i} fill={(r.average_overall ?? 0) >= 60 ? "var(--rag-green)" : (r.average_overall ?? 0) >= 40 ? "var(--rag-amber)" : "var(--rag-red)"} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Section>
          </div>

          {/* Top performers leaderboard */}
          {topStudents.length > 0 && (
            <Section title="Top performers" className="mb-4">
              <p className="text-[11px] text-muted mb-3">Students with the highest scores across all cohorts.</p>
              <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2">
                {topStudents.map((s, i) => (
                  <div key={s.user.id} className="flex items-center gap-3 p-3 rounded-lg"
                       style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
                    <div className="w-8 h-8 rounded-full flex items-center justify-center text-[11px] font-bold shrink-0"
                         style={{
                           background: i < 3 ? "color-mix(in srgb, var(--primary) 20%, transparent)" : "var(--surface)",
                           color: i < 3 ? "var(--primary)" : "var(--muted)",
                           border: i < 3 ? "2px solid var(--primary)" : "1px solid var(--border)"
                         }}>
                      {i + 1}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="text-[12px] font-medium truncate">{s.user.full_name}</div>
                      <div className="text-[10px] text-muted">{s.user.roll_number || s.user.branch || ""}</div>
                    </div>
                    <div className="text-right shrink-0">
                      <div className="text-sm font-bold" style={{
                        color: (s.overall_score ?? 0) >= 60 ? "var(--rag-green)" : (s.overall_score ?? 0) >= 40 ? "var(--rag-amber)" : "var(--rag-red)"
                      }}>
                        {s.overall_score?.toFixed(1) ?? "—"}
                      </div>
                      <div className="text-[9px] text-muted">{s.attempts} attempts</div>
                    </div>
                  </div>
                ))}
              </div>
            </Section>
          )}

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

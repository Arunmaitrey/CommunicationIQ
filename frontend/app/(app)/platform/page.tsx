"use client";
import Link from "next/link";
import { Building2, ScrollText, Users, BookOpen } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { ErrorNote, PageHeader, Section, Skeleton, StatCard } from "@/components/ui";
import { api, API_BASE, getToken } from "@/lib/api";
import { PLATFORM_ROLES } from "@/lib/roles";
import { useData } from "@/lib/useData";
import {
  PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, Legend,
} from "recharts";

const COLORS = ["var(--primary)", "var(--secondary)", "var(--accent)", "var(--rag-amber)", "var(--rag-green)"];

export default function PlatformOverviewPage() {
  return (
    <RequireAuth roles={PLATFORM_ROLES}>
      <Overview />
    </RequireAuth>
  );
}

function Overview() {
  const { data, loading, error } = useData(() => api.platformOverview());
  const tenants = useData(() => api.platformTenants());
  const questions = useData(async () => {
    const token = getToken();
    const res = await fetch(`${API_BASE}/platform/questions`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) return null;
    return res.json();
  });

  if (loading) return <Skeleton rows={5} />;
  if (error) return <ErrorNote message={error} />;
  if (!data) return null;

  const qd = questions.data as any;
  const questionDistribution = qd?.counts
    ? [
        { name: "Quiz/MCQ", value: qd.counts.quiz_items || 0 },
        { name: "Speaking", value: qd.counts.task_items || 0 },
        { name: "Writing", value: qd.counts.writing_prompts || 0 },
        { name: "Listening", value: qd.counts.listening_passages || 0 },
        { name: "Reading", value: qd.counts.reading_passages || 0 },
      ]
    : [];

  // Seat usage per institution (top by seats sold) — a real cross-tenant
  // comparison; the old two-bar Total/Active chart repeated the stat cards.
  const short = (s: string) => s.length > 18 ? s.slice(0, 17).trimEnd() + "…" : s;
  const seatData = (tenants.data ?? [])
    .slice()
    .sort((a: any, b: any) => (b.seat_limit || 0) - (a.seat_limit || 0))
    .slice(0, 6)
    .map((t: any) => ({
      name: short(t.name || t.slug),
      used: t.seats_used ?? 0,
      limit: t.seat_limit || 0,
    }));

  return (
    <>
      <PageHeader
        title="Platform overview"
        sub="Global view of all institutions, students and system activity. No restrictions — you have full access."
      />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4 reveal-stagger">
        <StatCard icon={Building2} label="Institutions" value={data.tenants_total}
                  sub={`${data.tenants_active} active or in trial`} />
        <StatCard icon={Users} label="Seats sold" value={data.seats_sold}
                  tone="var(--secondary)" sub={`${data.tenants_active} active institutions`} />
        <StatCard icon={ScrollText} label="Audit events (7d)" value={data.audit_events_7d}
                  tone="var(--accent)" />
        <StatCard icon={BookOpen} label="Questions" value={
          qd?.counts
            ? (qd.counts.quiz_items || 0) + (qd.counts.task_items || 0)
              + (qd.counts.writing_prompts || 0) + (qd.counts.listening_passages || 0)
              + (qd.counts.reading_passages || 0)
            : "—"
        } tone="var(--rag-green)" sub="across all banks" />
      </div>

      {/* Charts row */}
      {questionDistribution.length > 0 && (
        <div className="grid md:grid-cols-2 gap-4 mb-4 reveal-stagger">
          <Section title="Question bank distribution">
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={questionDistribution}
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={90}
                    paddingAngle={3}
                    dataKey="value"
                    label={({ name, percent }) => `${name} ${((percent ?? 0) * 100).toFixed(0)}%`}
                    labelLine={false}
                  >
                    {questionDistribution.map((_: any, i: number) => (
                      <Cell key={i} fill={COLORS[i % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </Section>

          <Section title="Seat usage by institution">
            {seatData.length > 0 ? (
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={seatData} layout="vertical" barSize={16}>
                    <XAxis type="number" tick={{ fontSize: 11 }} allowDecimals={false} />
                    <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={130} />
                    <Tooltip
                      formatter={(v: any, _n: any, row: any) => [`${v} / ${row?.payload?.limit ?? "—"} seats`, "Used"]}
                    />
                    <Bar dataKey="used" radius={[0, 6, 6, 0]} name="Seats used">
                      {seatData.map((_: any, i: number) => (
                        <Cell key={i} fill={
                          i === 0 ? "var(--primary)"
                            : i === 1 ? "var(--secondary)"
                            : i === 2 ? "var(--accent)" : "var(--muted)"
                        } />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <p className="text-xs text-muted py-8 text-center">
                No institutions yet. Create one to see seat usage here.
              </p>
            )}
          </Section>
        </div>
      )}

      <Section title="Quick actions">
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3 reveal-stagger">
          <Link href="/platform/tenants" className="ds-card card-interactive p-4 block">
            <div className="flex items-center gap-2">
              <Building2 size={16} style={{ color: "var(--primary)" }} />
              <span className="text-sm font-bold">Institutions</span>
            </div>
            <p className="text-[11px] text-muted mt-1">Create and manage institutions.</p>
          </Link>
          <Link href="/platform/content" className="ds-card card-interactive p-4 block">
            <div className="flex items-center gap-2">
              <BookOpen size={16} style={{ color: "var(--secondary)" }} />
              <span className="text-sm font-bold">Question Bank</span>
            </div>
            <p className="text-[11px] text-muted mt-1">Manage questions across all banks.</p>
          </Link>
          <Link href="/platform/results" className="ds-card card-interactive p-4 block">
            <div className="flex items-center gap-2">
              <Users size={16} style={{ color: "var(--rag-green)" }} />
              <span className="text-sm font-bold">Exam results</span>
            </div>
            <p className="text-[11px] text-muted mt-1">View results across all institutions.</p>
          </Link>
          <Link href="/platform/audit" className="ds-card card-interactive p-4 block">
            <div className="flex items-center gap-2">
              <ScrollText size={16} style={{ color: "var(--accent)" }} />
              <span className="text-sm font-bold">Audit log</span>
            </div>
            <p className="text-[11px] text-muted mt-1">Track all platform actions.</p>
          </Link>
        </div>
      </Section>
    </>
  );
}

"use client";
import { useRouter } from "next/navigation";
import { LineChart } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import {
  Badge, EmptyState, ErrorNote, GapMeter, PageHeader, Section, Skeleton, Table,
} from "@/components/ui";
import { api } from "@/lib/api";
import { skillLabel } from "@/lib/roles";
import { useData } from "@/lib/useData";

export default function ProgressPage() {
  return (
    <RequireAuth roles={["student"]}>
      <Progress />
    </RequireAuth>
  );
}

function Progress() {
  const router = useRouter();
  const { data, loading, error } = useData(() => api.studentHome());

  if (loading) return <Skeleton rows={6} />;
  if (error) return <ErrorNote message={error} />;
  if (!data) return null;

  return (
    <>
      <PageHeader
        title="Your progress"
        sub="Sub-skill mastery over time, and every attempt on record. Mastery moves on evidence — it is not a count of sessions."
      />

      <Section title="Sub-skill mastery" className="mb-4">
        {data.mastery.length === 0 ? (
          <EmptyState icon={LineChart} title="Nothing measured yet"
                      desc="Your baseline diagnostic establishes the starting point for each sub-skill." />
        ) : (
          <div className="space-y-3">
            {data.mastery.map((m) => {
              const pct = Math.round(m.mastery * 100);
              const delta = Math.round(m.last_change * 100);
              return (
                <div key={m.skill}>
                  <div className="flex items-baseline justify-between mb-1 text-xs">
                    <span className="font-semibold">{skillLabel(m.skill)}</span>
                    <span className="text-muted">
                      {pct}%
                      {delta !== 0 && (
                        <span style={{ color: delta > 0 ? "var(--rag-green)" : "var(--rag-red)" }}>
                          {" "}{delta > 0 ? "+" : ""}{delta}
                        </span>
                      )}
                    </span>
                  </div>
                  <GapMeter percent={pct} />
                  <div className="text-[10px] text-muted mt-1">
                    {m.observations} observations
                    {m.baseline != null && ` · baseline ${Math.round(m.baseline * 100)}%`}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Section>

      <Section title="Attempt history">
        {data.recent_attempts.length === 0 ? (
          <EmptyState icon={LineChart} title="No attempts yet" />
        ) : (
          <Table
            onRowClick={(i) => router.push(`/results/${data.recent_attempts[i].id}`)}
            columns={["Simulation", "Attempt", "Mode", "Status", "Overall"]}
            rows={data.recent_attempts.map((a) => [
              a.profile_name,
              `#${a.attempt_number}`,
              a.mode === "official" ? <Badge tone="var(--primary)">Official</Badge> : <Badge>Practice</Badge>,
              a.status,
              <span key="s" className="font-bold">{a.overall_score ?? "—"}</span>,
            ])}
          />
        )}
      </Section>
    </>
  );
}

"use client";
import Link from "next/link";
import { Users } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { EmptyState, ErrorNote, PageHeader, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { useData } from "@/lib/useData";

export default function CohortsPage() {
  return (
    <RequireAuth roles={["trainer"]}>
      <Cohorts />
    </RequireAuth>
  );
}

function Cohorts() {
  const { data, loading, error } = useData(() => api.trainerCohorts());

  if (loading) return <Skeleton rows={4} />;
  if (error) return <ErrorNote message={error} />;

  return (
    <>
      <PageHeader
        title="Your cohorts"
        sub="Only the cohorts assigned to you. You can read diagnostics and assign drills — recorded scores and attempt history are not editable by anyone."
      />

      {(!data || data.length === 0) ? (
        <div className="ds-card">
          <EmptyState icon={Users} title="No cohorts assigned"
                      desc="Your institution admin assigns cohorts to trainers." />
        </div>
      ) : (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3">
          {data.map((c) => {
            const days = c.drive_start
              ? Math.ceil((new Date(c.drive_start).getTime() - Date.now()) / 86400000)
              : null;
            return (
              <Link key={c.id} href={`/cohorts/${c.id}`}
                    className="ds-card p-4 hover:bg-surface2 transition-colors ds-focus block">
                <div className="text-sm font-bold">{c.name}</div>
                <div className="text-[11px] text-muted mt-1">
                  {c.branch} · Section {c.section} · {c.member_count} students
                </div>
                <div className="text-[11px] mt-3" style={{ color: "var(--secondary)" }}>
                  {days != null ? `Drive in ${days} days` : "No drive date set"}
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </>
  );
}

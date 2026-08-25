"use client";
import { GraduationCap, ShieldCheck, Users, Wallet } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { ErrorNote, PageHeader, Progress, Section, Skeleton, StatCard } from "@/components/ui";
import { Workflow, type Step } from "@/components/Workflow";
import { api, type TenantOverview } from "@/lib/api";
import { useData } from "@/lib/useData";

export default function TenantOverviewPage() {
  return (
    <RequireAuth roles={["tenant_admin"]}>
      <Overview />
    </RequireAuth>
  );
}

function Overview() {
  const { data, loading, error } = useData(() => api.tenantOverview());
  // Only to answer "has anybody built or chosen an assessment yet". The list
  // itself lives on its own screen.
  const profiles = useData(() => api.tenantProfiles());

  if (loading) return <Skeleton rows={5} />;
  if (error) return <ErrorNote message={error} />;
  if (!data) return null;

  const seatPct = data.seat_limit ? (data.seats_used / data.seat_limit) * 100 : 0;

  return (
    <>
      <PageHeader title={data.tenant_name} sub={`Plan: ${data.plan_name || "—"}`} />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
        <StatCard icon={Users} label="Students" value={data.students} />
        <StatCard icon={GraduationCap} label="Cohorts" value={data.cohorts} tone="var(--secondary)" />
        <StatCard icon={Wallet} label="Seats used" value={`${data.seats_used}/${data.seat_limit}`}
                  tone="var(--accent)" />
        <StatCard icon={ShieldCheck} label="Consent pending" value={data.consent_pending}
                  tone={data.consent_pending > 0 ? "var(--rag-amber)" : "var(--rag-green)"}
                  sub="no recording without it" />
      </div>

      <Workflow title="Setting up, in order"
                steps={tenantSteps(data, (profiles.data ?? []).length)} />

      <Section title="Seat usage" className="mb-4">
        <Progress value={seatPct} />
        <div className="text-[11px] text-muted mt-2">
          {data.seats_used} of {data.seat_limit} seats — students, trainers and admins all
          count against the limit.
        </div>
      </Section>

      <Section title="Activity">
        <div className="text-xs text-muted">
          {data.attempts_total} attempts recorded across the institution.
        </div>
      </Section>
    </>
  );
}

/** What an institution admin does, in the order it has to happen.
 *
 *  The console opened with four counters. Counters answer "how much"; nobody
 *  had answered "in what order", and the order genuinely matters here —
 *  nothing can be recorded before consent, and consent cannot be collected
 *  from people who have not been added.
 */
function tenantSteps(data: TenantOverview, profileCount: number): Step[] {
  return [
    {
      title: "Add your people",
      detail: "One at a time, or a spreadsheet of the whole year group.",
      href: "/tenant/import",
      done: data.students > 0,
    },
    {
      title: "Group them into cohorts",
      detail: "Branch, year and section. A cohort is what a trainer coaches.",
      href: "/tenant/cohorts",
      done: data.cohorts > 0,
    },
    {
      title: "Set the placement season",
      detail: "The drive date is what turns a score into “how long you have left”.",
      href: "/tenant/season",
    },
    {
      title: "Collect recording consent",
      detail: data.consent_pending > 0
        ? `${data.consent_pending} student${data.consent_pending === 1 ? " has" : "s have"} not agreed yet. Nothing records for them until they do.`
        : "Everyone has agreed. Nothing is ever recorded without it.",
      href: "/tenant/users",
      done: data.consent_pending === 0 && data.students > 0,
    },
    {
      title: "Choose or build assessments",
      detail: "Four standard templates, five company rounds, or your own.",
      href: "/tenant/profiles",
      done: profileCount > 0,
    },
    {
      title: "Watch readiness",
      detail: "Who is on track for the drive, and which skill is holding the group back.",
      href: "/tenant/readiness",
      done: data.attempts_total > 0,
    },
  ];
}

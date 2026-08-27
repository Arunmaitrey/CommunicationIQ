"use client";
import { Building2, ScrollText, Users, BookOpen } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { ErrorNote, PageHeader, Section, Skeleton, StatCard } from "@/components/ui";
import { api } from "@/lib/api";
import { PLATFORM_ROLES } from "@/lib/roles";
import { useData } from "@/lib/useData";


export default function PlatformOverviewPage() {
  return (
    <RequireAuth roles={PLATFORM_ROLES}>
      <Overview />
    </RequireAuth>
  );
}

function Overview() {
  const { data, loading, error } = useData(() => api.platformOverview());


  if (loading) return <Skeleton rows={5} />;
  if (error) return <ErrorNote message={error} />;
  if (!data) return null;



  return (
    <>
      <PageHeader
        title="Platform overview"
        sub="Global view of all institutions, students and system activity. No restrictions — you have full access."
      />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
        <StatCard icon={Building2} label="Institutions" value={data.tenants_total}
                  sub={`${data.tenants_active} active or in trial`} />
        <StatCard icon={Users} label="Seats sold" value={data.seats_sold}
                  tone="var(--secondary)" sub={`${data.tenants_active} active institutions`} />
        <StatCard icon={ScrollText} label="Audit events (7d)" value={data.audit_events_7d}
                  tone="var(--accent)" />
      </div>

      <Section title="Quick actions">
        <div className="grid sm:grid-cols-3 gap-3">
          <a href="/platform/tenants" className="ds-card p-4 hover:bg-surface2 transition-colors block">
            <div className="flex items-center gap-2">
              <Building2 size={16} style={{ color: "var(--primary)" }} />
              <span className="text-sm font-bold">Create institution</span>
            </div>
            <p className="text-[11px] text-muted mt-1">Create a new institution, assign an admin, and set the email domain.</p>
          </a>
          <a href="/platform/content" className="ds-card p-4 hover:bg-surface2 transition-colors block">
            <div className="flex items-center gap-2">
              <BookOpen size={16} style={{ color: "var(--secondary)" }} />
              <span className="text-sm font-bold">Question Bank</span>
            </div>
            <p className="text-[11px] text-muted mt-1">Manage questions for reading, writing, listening and speaking across all institutions.</p>
          </a>
          <a href="/platform/results" className="ds-card p-4 hover:bg-surface2 transition-colors block">
            <div className="flex items-center gap-2">
              <Users size={16} style={{ color: "var(--emerald)" }} />
              <span className="text-sm font-bold">View students</span>
            </div>
            <p className="text-[11px] text-muted mt-1">See student lists and details across all institutions.</p>
          </a>
          <a href="/platform/audit" className="ds-card p-4 hover:bg-surface2 transition-colors block">
            <div className="flex items-center gap-2">
              <ScrollText size={16} style={{ color: "var(--accent)" }} />
              <span className="text-sm font-bold">Audit log</span>
            </div>
            <p className="text-[11px] text-muted mt-1">View all actions across the platform.</p>
          </a>

        </div>
      </Section>
    </>
  );
}

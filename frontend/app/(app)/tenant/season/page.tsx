"use client";
import { CalendarClock } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { Badge, ErrorNote, PageHeader, Section, Skeleton, Table } from "@/components/ui";
import { api } from "@/lib/api";
import { useData } from "@/lib/useData";

export default function TenantSeasonPage() {
  return (
    <RequireAuth roles={["tenant_admin"]}>
      <Season />
    </RequireAuth>
  );
}

function Season() {
  const { data, loading, error } = useData(() => api.tenantSeason());

  return (
    <>
      <PageHeader
        title="Placement season"
        sub="Every countdown in the student app is derived from these dates. There is no other timer in the product — manufactured urgency is not a feature we build."
      />

      <div className="ds-card p-4 mb-4 flex items-start gap-3">
        <CalendarClock size={16} className="text-muted mt-0.5 shrink-0" />
        <p className="text-xs text-muted leading-relaxed">
          A cohort without a drive date runs on a rolling 90-day season. Setting the
          real date re-plans quests within a day, and the student sees the actual
          number of days remaining — never a shortened one.
        </p>
      </div>

      <Section>
        {loading ? <Skeleton rows={4} /> : error ? <ErrorNote message={error} /> : (
          <Table
            columns={["Cohort", "Drive starts", "Drive ends", "Days remaining", "Season basis"]}
            rows={(data ?? []).map((r) => [
              <span key="n" className="font-medium">{r.cohort_name}</span>,
              r.drive_start ? new Date(r.drive_start).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) : "—",
              r.drive_end ? new Date(r.drive_end).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) : "—",
              r.days_to_drive != null
                ? <span key="d" className="font-bold">{r.days_to_drive}</span>
                : <span key="d" className="text-muted">—</span>,
              r.season_source === "drive_date"
                ? <Badge key="s" tone="var(--rag-green)">Real drive date</Badge>
                : <Badge key="s" tone="var(--muted)">Rolling 90 days</Badge>,
            ])}
          />
        )}
      </Section>
    </>
  );
}

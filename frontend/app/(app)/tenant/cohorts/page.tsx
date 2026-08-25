"use client";
import { RequireAuth } from "@/components/RequireAuth";
import { ErrorNote, PageHeader, Section, Skeleton, Table } from "@/components/ui";
import { api } from "@/lib/api";
import { useData } from "@/lib/useData";

export default function TenantCohortsPage() {
  return (
    <RequireAuth roles={["tenant_admin"]}>
      <Cohorts />
    </RequireAuth>
  );
}

function Cohorts() {
  const { data, loading, error } = useData(() => api.tenantCohorts());

  return (
    <>
      <PageHeader
        title="Cohorts"
        sub="Batches by branch, year and section, each with an assigned trainer and a real placement window."
      />
      <Section>
        {loading ? <Skeleton rows={5} /> : error ? <ErrorNote message={error} /> : (
          <Table
            columns={["Cohort", "Branch", "Section", "Trainer", "Students", "Drive window"]}
            rows={(data ?? []).map((c) => [
              <span key="n" className="font-medium">{c.name}</span>,
              c.branch || "—",
              c.section || "—",
              c.trainer_name || <span key="t" className="text-muted">unassigned</span>,
              c.member_count,
              c.drive_start
                ? new Date(c.drive_start).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })
                : <span key="d" className="text-muted">not set</span>,
            ])}
          />
        )}
      </Section>
    </>
  );
}

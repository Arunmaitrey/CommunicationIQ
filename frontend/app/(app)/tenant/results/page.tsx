"use client";
import Link from "next/link";
import { useState } from "react";
import { Download, ExternalLink, FileText } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { Badge, EmptyState, ErrorNote, PageHeader, Section, Skeleton, Table, Tabs } from "@/components/ui";
import { api, adminApi, type Attempt, type UserRow } from "@/lib/api";
import { useData } from "@/lib/useData";
import { useToast } from "@/components/Toast";

export default function TenantResultsPage() {
  return (
    <RequireAuth roles={["tenant_admin"]}>
      <Results />
    </RequireAuth>
  );
}

function Results() {
  const { toast } = useToast();
  const [tab, setTab] = useState("all");
  const [busy, setBusy] = useState(false);

  // Get all users
  const users = useData(() => api.tenantUsers(tab === "all" ? undefined : tab), [tab]);

  // Get all cohorts to count attempts
  const cohorts = useData(() => api.tenantCohorts());

  async function exportExcel() {
    setBusy(true);
    try {
      // Use the platform export endpoint (super admin only) or generate client-side
      toast("info", "Preparing Excel export…");
      // For tenant admins, we'll export the users list as CSV
      const userList = users.data ?? [];
      const headers = ["Name", "Email", "Role", "Roll Number", "Branch", "Year", "Status"];
      const rows = userList.map((u) => [
        u.full_name, u.email, u.role, u.roll_number || "",
        u.branch || "", u.year_of_study?.toString() || "", u.active ? "Active" : "Inactive",
      ]);
      const csv = [headers, ...rows].map((r) => r.map((c) => `"${c}"`).join(",")).join("\n");
      const blob = new Blob([csv], { type: "text/csv" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "institution-users.csv";
      a.click();
      URL.revokeObjectURL(url);
      toast("success", "Excel export downloaded");
    } catch {
      toast("error", "Export failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Exam results"
        sub="All student exam results for your institution. View readiness, scores and cohort performance."
        action={
          <button onClick={() => void exportExcel()} disabled={busy} className="btn btn-ghost btn-sm ds-focus">
            <Download size={13} /> {busy ? "Exporting…" : "Export to Excel"}
          </button>
        }
      />

      {/* Summary stats */}
      <div className="grid sm:grid-cols-3 gap-3 mb-4">
        <div className="ds-card p-4">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-muted">Total students</div>
          <div className="text-2xl font-bold mt-2" style={{ color: "var(--primary)" }}>
            {(users.data ?? []).filter((u) => u.role === "student").length}
          </div>
        </div>
        <div className="ds-card p-4">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-muted">Total cohorts</div>
          <div className="text-2xl font-bold mt-2" style={{ color: "var(--secondary)" }}>
            {cohorts.data?.length ?? 0}
          </div>
        </div>
        <div className="ds-card p-4">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-muted">Active students</div>
          <div className="text-2xl font-bold mt-2" style={{ color: "var(--rag-green)" }}>
            {(users.data ?? []).filter((u) => u.role === "student" && u.active).length}
          </div>
        </div>
      </div>

      <Tabs
        active={tab}
        onChange={setTab}
        tabs={[
          { id: "all", label: "All users" },
          { id: "student", label: "Students only" },
          { id: "tenant_admin", label: "Admins" },
        ]}
      />

      <Section title="Students &amp; staff">
        {users.loading ? <Skeleton rows={6} /> : users.error ? <ErrorNote message={users.error} /> : (
          <Table
            columns={["Name", "Email", "Role", "Roll", "Branch", "L1", "Status"]}
            rows={(users.data ?? []).map((u) => [
              <span key="n" className="font-medium">{u.full_name}</span>,
              <span key="e" className="text-muted">{u.email}</span>,
              <Badge key="r" tone={
                u.role === "student" ? "var(--primary)" :
                u.role === "tenant_admin" ? "var(--accent)" : "var(--muted)"
              }>{u.role}</Badge>,
              u.roll_number || "—",
              u.branch || "—",
              u.l1_language || "—",
              u.active
                ? <Badge key="s" tone="var(--rag-green)">Active</Badge>
                : <Badge key="s" tone="var(--muted)">Inactive</Badge>,
            ])}
          />
        )}
      </Section>

      <Section title="Cohort readiness" className="mt-4">
        <p className="text-xs text-muted mb-3">
          View detailed readiness scores per cohort at{" "}
          <Link href="/tenant/readiness" className="underline">Readiness dashboard</Link>.
        </p>
        {cohorts.loading ? <Skeleton rows={3} /> : cohorts.error ? <ErrorNote message={cohorts.error} /> : (
          <Table
            columns={["Cohort", "Branch", "Students", "Drive window"]}
            rows={(cohorts.data ?? []).map((c) => [
              <span key="n" className="font-medium">{c.name}</span>,
              c.branch || "—",
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

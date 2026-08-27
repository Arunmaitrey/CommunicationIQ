"use client";
import { useState, useEffect } from "react";
import { Building2, Download, Users, ChevronDown, ChevronRight } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { Badge, ErrorNote, PageHeader, Section, Skeleton, Table } from "@/components/ui";
import { api, type TenantRow, type UserRow } from "@/lib/api";
import { PLATFORM_ROLES } from "@/lib/roles";
import { useData } from "@/lib/useData";

type StudentRow = {
  id: string; full_name: string; email: string; role: string; active: boolean;
  branch: string; year_of_study: number | null; roll_number: string;
  last_login_at?: string | null;
};

export default function PlatformResultsPage() {
  return (
    <RequireAuth roles={PLATFORM_ROLES}>
      <Results />
    </RequireAuth>
  );
}

function Results() {
  const tenants = useData(() => api.platformTenants());
  const [selectedTenant, setSelectedTenant] = useState<string>("all");

  return (
    <>
      <PageHeader
        title="Exam results"
        sub="Results across all institutions. Select an institution to see its students with details."
      />

      {tenants.loading ? <Skeleton rows={5} /> : tenants.error ? <ErrorNote message={tenants.error} /> : (
        <>
          {/* Tenant filter */}
          <Section className="mb-4" compact>
            <div className="flex items-center gap-3 flex-wrap">
              <span className="text-[11px] font-bold uppercase tracking-wider text-muted">
                Institution
              </span>
              <div className="flex gap-1.5 flex-wrap">
                <button
                  onClick={() => setSelectedTenant("all")}
                  className={`px-2.5 py-1 text-[11px] font-semibold rounded-lg ds-focus transition-colors ${
                    selectedTenant === "all" ? "text-white" : "text-muted hover:text-text"
                  }`}
                  style={selectedTenant === "all" ? { background: "var(--primary)" } : { background: "var(--surface)" }}
                >
                  All institutions
                </button>
                {(tenants.data ?? []).map((t) => (
                  <button
                    key={t.id}
                    onClick={() => setSelectedTenant(t.id)}
                    className={`px-2.5 py-1 text-[11px] font-semibold rounded-lg ds-focus transition-colors flex items-center gap-1.5 ${
                      selectedTenant === t.id ? "text-white" : "text-muted hover:text-text"
                    }`}
                    style={selectedTenant === t.id ? { background: "var(--primary)" } : { background: "var(--surface)" }}
                  >
                    <Building2 size={10} /> {t.name}
                  </button>
                ))}
              </div>
            </div>
          </Section>

          {/* Show expanded student list for each selected tenant */}
          {(tenants.data ?? []).filter((t) => selectedTenant === "all" || t.id === selectedTenant).map((t) => (
            <TenantStudentsCard key={t.id} tenant={t} />
          ))}

          {/* Quick stats */}
          <div className="grid sm:grid-cols-3 gap-3 mt-4">
            <div className="ds-card p-4">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-muted">Total institutions</div>
              <div className="text-2xl font-bold mt-2" style={{ color: "var(--primary)" }}>
                {(tenants.data ?? []).length}
              </div>
            </div>
            <div className="ds-card p-4">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-muted">Active institutions</div>
              <div className="text-2xl font-bold mt-2" style={{ color: "var(--rag-green)" }}>
                {(tenants.data ?? []).filter((t) => t.status === "active").length}
              </div>
            </div>
            <div className="ds-card p-4">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-muted">Total seats</div>
              <div className="text-2xl font-bold mt-2" style={{ color: "var(--accent)" }}>
                {(tenants.data ?? []).reduce((sum, t) => sum + t.seat_limit, 0)}
              </div>
            </div>
          </div>
        </>
      )}
    </>
  );
}

function TenantStudentsCard({ tenant }: { tenant: TenantRow }) {
  const [expanded, setExpanded] = useState(false);
  const [students, setStudents] = useState<StudentRow[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!expanded || students.length > 0) return;
    setLoading(true);
    api.platformTenantUsers(tenant.id)
      .then((data) => setStudents(data as UserRow[]))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [expanded, tenant.id, students.length]);

  const studentList = students.filter((s) => s.role === "student");
  const adminList = students.filter((s) => s.role === "tenant_admin");

  return (
    <Section className="mb-3">
      <button
        className="w-full flex items-center gap-2 text-left"
        onClick={() => setExpanded(!expanded)}
      >
        {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <Building2 size={14} style={{ color: "var(--primary)" }} />
        <span className="text-sm font-bold flex-1">{tenant.name}</span>
        <Badge tone={
          tenant.status === "active" ? "var(--rag-green)" : tenant.status === "trial" ? "var(--accent)" : "var(--muted)"
        }>{tenant.status}</Badge>
        <span className="text-[11px] text-muted">{studentList.length} students</span>
        <span className="text-[11px] text-muted">{adminList.length} admins</span>
      </button>
      {expanded && (
        <div className="mt-3 pt-3" style={{ borderTop: "1px solid var(--border)" }}>
          {loading ? <Skeleton rows={3} /> : students.length === 0 ? (
            <div className="text-xs text-muted">No users found</div>
          ) : (
            <>
              {adminList.length > 0 && (
                <div className="mb-3">
                  <div className="text-[10px] font-bold uppercase tracking-wider text-muted mb-2">Admins</div>
                  {adminList.map((u) => (
                    <div key={u.id} className="flex items-center gap-3 py-1.5 px-2 text-[11px] rounded mb-1" style={{ background: "var(--surface)" }}>
                      <span className="font-medium flex-1">{u.full_name}</span>
                      <span className="text-muted">{u.email}</span>
                      <Badge tone="var(--accent)">admin</Badge>
                      <span className="text-muted">{u.branch || "—"}</span>
                      <span className="text-muted">Year {u.year_of_study || "—"}</span>
                      <span className="text-muted">Roll: {u.roll_number || "—"}</span>
                    </div>
                  ))}
                </div>
              )}
              <div>
                <div className="text-[10px] font-bold uppercase tracking-wider text-muted mb-2">Students ({studentList.length})</div>
                <Table
                  columns={["Name", "Email", "Branch", "Year", "Roll No", "Status"]}
                  rows={studentList.map((u) => [
                    <span key="n" className="font-medium">{u.full_name}</span>,
                    <span key="e" className="text-muted">{u.email}</span>,
                    <span key="b">{u.branch || "—"}</span>,
                    <span key="y">{u.year_of_study || "—"}</span>,
                    <span key="r">{u.roll_number || "—"}</span>,
                    u.active
                      ? <Badge key="s" tone="var(--rag-green)">Active</Badge>
                      : <Badge key="s" tone="var(--muted)">Inactive</Badge>,
                  ])}
                />
              </div>
            </>
          )}
        </div>
      )}
    </Section>
  );
}

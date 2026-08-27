"use client";
import { useState } from "react";
import { RequireAuth } from "@/components/RequireAuth";
import { Badge, EmptyState, ErrorNote, PageHeader, Section, Skeleton, Table } from "@/components/ui";
import { api } from "@/lib/api";
import { PLATFORM_ROLES } from "@/lib/roles";
import { useData } from "@/lib/useData";

export default function AuditPage() {
  return (
    <RequireAuth roles={PLATFORM_ROLES}>
      <Audit />
    </RequireAuth>
  );
}

function Audit() {
  const { data, loading, error } = useData(() => api.platformAudit());
  const tenants = useData(() => api.platformTenants());
  const [tenantFilter, setTenantFilter] = useState<string>("all");
  const [actionFilter, setActionFilter] = useState<string>("");

  const filtered = (data ?? []).filter((a) => {
    if (tenantFilter !== "all" && a.tenant_id !== tenantFilter) return false;
    if (actionFilter && !a.action.toLowerCase().includes(actionFilter.toLowerCase())) return false;
    return true;
  });

  // Get unique actions for the filter
  const uniqueActions = Array.from(new Set((data ?? []).map((a) => a.action))).sort();

  return (
    <>
      <PageHeader
        title="Audit log"
        sub="Append-only. Nothing in the application updates or deletes a row here, which is the only property that makes an audit log worth having."
      />

      {/* Filters */}
      <Section className="mb-4" compact>
        <div className="flex items-center gap-4 flex-wrap">
          <div>
            <label className="text-[10px] font-bold uppercase tracking-wider text-muted mb-1 block">
              Institution
            </label>
            <select
              className="ds-input text-xs"
              value={tenantFilter}
              onChange={(e) => setTenantFilter(e.target.value)}
            >
              <option value="all">All institutions</option>
              {(tenants.data ?? []).map((t) => (
                <option key={t.id} value={t.id}>{t.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-[10px] font-bold uppercase tracking-wider text-muted mb-1 block">
              Action type
            </label>
            <select
              className="ds-input text-xs"
              value={actionFilter}
              onChange={(e) => setActionFilter(e.target.value)}
            >
              <option value="">All actions</option>
              {uniqueActions.map((a) => (
                <option key={a} value={a}>{a}</option>
              ))}
            </select>
          </div>
          <div className="text-xs text-muted self-end">
            {filtered.length} event{filtered.length !== 1 ? "s" : ""}
          </div>
        </div>
      </Section>

      <Section>
        {loading ? <Skeleton rows={5} /> : error ? <ErrorNote message={error} /> :
         filtered.length === 0 ? <EmptyState title="No events recorded" /> : (
          <Table
            columns={["When", "Actor", "Action", "Entity", "Institution"]}
            rows={filtered.map((a) => [
              new Date(a.at).toLocaleString("en-IN", {
                day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
              }),
              <span key="a">
                <span className="font-medium">{a.actor_label || "system"}</span>
                <Badge tone="var(--muted)">{a.actor_type}</Badge>
              </span>,
              <code key="c" className="kbd">{a.action}</code>,
              `${a.entity}${a.entity_id ? ` · ${a.entity_id.slice(0, 8)}` : ""}`,
              a.tenant_id ? a.tenant_id.slice(0, 8) : "—",
            ])}
          />
        )}
      </Section>
    </>
  );
}

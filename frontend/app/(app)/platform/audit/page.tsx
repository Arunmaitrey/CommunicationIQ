"use client";
import { useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { Badge, EmptyState, ErrorNote, PageHeader, Section, Skeleton, Table } from "@/components/ui";
import { api } from "@/lib/api";
import { PLATFORM_ROLES } from "@/lib/roles";
import { useData } from "@/lib/useData";

const PAGE_SIZE = 15;

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
  const [page, setPage] = useState(0);

  const filtered = (data ?? []).filter((a) => {
    if (tenantFilter !== "all" && a.tenant_id !== tenantFilter) return false;
    if (actionFilter && !a.action.toLowerCase().includes(actionFilter.toLowerCase())) return false;
    return true;
  });

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const pageItems = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

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
            <label className="text-[10px] font-bold uppercase tracking-wider text-muted mb-1 block">Institution</label>
            <select className="ds-input text-xs" value={tenantFilter} onChange={(e) => { setTenantFilter(e.target.value); setPage(0); }}>
              <option value="all">All institutions</option>
              {(tenants.data ?? []).map((t) => (<option key={t.id} value={t.id}>{t.name}</option>))}
            </select>
          </div>
          <div>
            <label className="text-[10px] font-bold uppercase tracking-wider text-muted mb-1 block">Action type</label>
            <select className="ds-input text-xs" value={actionFilter} onChange={(e) => { setActionFilter(e.target.value); setPage(0); }}>
              <option value="">All actions</option>
              {uniqueActions.map((a) => (<option key={a} value={a}>{a}</option>))}
            </select>
          </div>
          <div className="text-xs text-muted self-end">
            {filtered.length} event{filtered.length !== 1 ? "s" : ""} · Page {page + 1} of {Math.max(1, totalPages)}
          </div>
        </div>
      </Section>

      <Section>
        {loading ? <Skeleton rows={5} /> : error ? <ErrorNote message={error} /> :
         filtered.length === 0 ? <EmptyState title="No events recorded" /> : (
          <>
            <Table
              columns={["When", "Actor", "Action", "Entity", "Institution"]}
              rows={pageItems.map((a) => [
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

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between p-3 border-t" style={{ borderColor: "var(--border)" }}>
                <span className="text-[11px] text-muted">
                  Showing {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, filtered.length)} of {filtered.length}
                </span>
                <div className="flex items-center gap-1">
                  <button disabled={page === 0}
                    onClick={() => setPage(page - 1)}
                    className="p-1 rounded disabled:opacity-30 hover:bg-surface2">
                    <ChevronLeft size={14} />
                  </button>
                  {Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
                    let pIdx = i;
                    if (totalPages > 7) {
                      if (page < 3) pIdx = i;
                      else if (page > totalPages - 4) pIdx = totalPages - 7 + i;
                      else pIdx = page - 3 + i;
                    }
                    return (
                      <button key={pIdx}
                        onClick={() => setPage(pIdx)}
                        className="w-6 h-6 rounded text-[11px] font-medium"
                        style={{
                          background: pIdx === page ? "var(--primary)" : "transparent",
                          color: pIdx === page ? "white" : "var(--muted)",
                        }}>
                        {pIdx + 1}
                      </button>
                    );
                  })}
                  <button disabled={page >= totalPages - 1}
                    onClick={() => setPage(page + 1)}
                    className="p-1 rounded disabled:opacity-30 hover:bg-surface2">
                    <ChevronRight size={14} />
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </Section>
    </>
  );
}

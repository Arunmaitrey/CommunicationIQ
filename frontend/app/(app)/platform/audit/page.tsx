"use client";
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

  return (
    <>
      <PageHeader
        title="Audit log"
        sub="Append-only. Nothing in the application updates or deletes a row here, which is the only property that makes an audit log worth having."
      />
      <Section>
        {loading ? <Skeleton rows={5} /> : error ? <ErrorNote message={error} /> :
         (data ?? []).length === 0 ? <EmptyState title="No events recorded" /> : (
          <Table
            columns={["When", "Actor", "Action", "Entity", "Institution"]}
            rows={(data ?? []).map((a) => [
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

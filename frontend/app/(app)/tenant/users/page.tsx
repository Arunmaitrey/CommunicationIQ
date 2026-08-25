"use client";
import { useState } from "react";
import { RequireAuth } from "@/components/RequireAuth";
import {
  Avatar, Badge, ErrorNote, PageHeader, Section, Skeleton, Table, Tabs,
} from "@/components/ui";
import { api } from "@/lib/api";
import { ROLE_LABEL } from "@/lib/roles";
import { useData } from "@/lib/useData";

export default function TenantUsersPage() {
  return (
    <RequireAuth roles={["tenant_admin"]}>
      <People />
    </RequireAuth>
  );
}

function People() {
  const [tab, setTab] = useState("student");
  const { data, loading, error } = useData(() => api.tenantUsers(tab === "all" ? undefined : tab), [tab]);

  return (
    <>
      <PageHeader
        title="People"
        sub="Everyone in your institution. Bulk import and role changes arrive with the rest of the institution console in M3."
      />

      <Tabs
        active={tab}
        onChange={setTab}
        tabs={[
          { id: "student", label: "Students" },
          { id: "trainer", label: "Trainers" },
          { id: "tenant_admin", label: "Admins" },
          { id: "all", label: "Everyone" },
        ]}
      />

      <Section>
        {loading ? <Skeleton rows={6} /> : error ? <ErrorNote message={error} /> : (
          <Table
            columns={["Name", "Email", "Role", "Roll", "Branch", "L1", "Status"]}
            rows={(data ?? []).map((u) => [
              <span key="n" className="flex items-center gap-2">
                <Avatar name={u.full_name} size={22} />
                <span className="font-medium">{u.full_name}</span>
              </span>,
              <span key="e" className="text-muted">{u.email}</span>,
              ROLE_LABEL[u.role as keyof typeof ROLE_LABEL] ?? u.role,
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
    </>
  );
}

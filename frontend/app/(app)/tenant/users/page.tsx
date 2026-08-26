"use client";
import { useState } from "react";
import { UserPlus, X } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import {
  Avatar, Badge, ErrorNote, PageHeader, Section, Skeleton, Table, Tabs,
} from "@/components/ui";
import { api, adminApi } from "@/lib/api";
import { ROLE_LABEL } from "@/lib/roles";
import { useData } from "@/lib/useData";
import { useToast } from "@/components/Toast";

export default function TenantUsersPage() {
  return (
    <RequireAuth roles={["tenant_admin"]}>
      <People />
    </RequireAuth>
  );
}

function People() {
  const [tab, setTab] = useState("student");
  const { data, loading, error, reload } = useData(() => api.tenantUsers(tab === "all" ? undefined : tab), [tab]);
  const [showCreate, setShowCreate] = useState(false);

  return (
    <>
      <PageHeader
        title="People"
        sub="Everyone in your institution. Create users, assign roles, and manage access."
        action={
          <button className="btn btn-primary btn-sm" onClick={() => setShowCreate(true)}>
            <UserPlus size={14} /> Add User
          </button>
        }
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

      {showCreate && <CreateUserModal onClose={() => setShowCreate(false)} onCreated={reload} />}
    </>
  );
}

function CreateUserModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const { toast } = useToast();
  const [form, setForm] = useState({ full_name: "", email: "", role: "student", password: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await adminApi.createUser({
        full_name: form.full_name,
        email: form.email,
        role: form.role,
        password: form.password,
      });
      toast("success", `User ${form.full_name} created successfully`);
      onCreated();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create user");
      setBusy(false);
    }
  }

  return (
    <div className="modal-scrim" onClick={onClose}>
      <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-bold">Add User</h3>
          <button onClick={onClose} className="btn btn-icon btn-ghost btn-sm"><X size={14} /></button>
        </div>

        <form onSubmit={submit} className="space-y-3">
          <div>
            <label className="ds-label">Full Name</label>
            <input className="ds-input" value={form.full_name} required
              onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
          </div>
          <div>
            <label className="ds-label">Email</label>
            <input className="ds-input" type="email" required value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })} />
          </div>
          <div>
            <label className="ds-label">Role</label>
            <select className="ds-select" value={form.role}
              onChange={(e) => setForm({ ...form, role: e.target.value })}>
              <option value="student">Student</option>
              <option value="trainer">Trainer</option>
              <option value="tenant_admin">Tenant Admin</option>
            </select>
          </div>
          <div>
            <label className="ds-label">Password</label>
            <input className="ds-input" type="password" required value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })} />
          </div>
          {error && <div className="text-xs font-medium" style={{ color: "var(--rag-red)" }}>{error}</div>}
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" className="btn btn-ghost btn-sm" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary btn-sm" disabled={busy}>
              {busy ? "Creating…" : "Create User"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

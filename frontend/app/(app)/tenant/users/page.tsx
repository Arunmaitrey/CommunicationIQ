"use client";
import { useState } from "react";
import { UserPlus, X, Eye, EyeOff, Pencil, Key, Power } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import {
  Avatar, Badge, ErrorNote, PageHeader, Section, Skeleton, Table, Tabs,
} from "@/components/ui";
import { api, adminApi, type UserRow } from "@/lib/api";
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
  const { toast } = useToast();
  const [tab, setTab] = useState("student");
  const { data, loading, error, reload } = useData(() => api.tenantUsers(tab === "all" ? undefined : tab), [tab]);
  const [showCreate, setShowCreate] = useState(false);
  const [editingUser, setEditingUser] = useState<UserRow | null>(null);
  const [resettingUser, setResettingUser] = useState<UserRow | null>(null);

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
          { id: "tenant_admin", label: "Admins" },
          { id: "all", label: "Everyone" },
        ]}
      />

      <Section>
        {loading ? <Skeleton rows={6} /> : error ? <ErrorNote message={error} /> : (
          <Table
            columns={["Name", "Email", "Role", "Roll", "Branch", "L1", "Status", ""]}
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
              <div key="a" className="flex items-center gap-1">
                <button className="btn btn-icon btn-ghost btn-sm" title="Edit" onClick={() => setEditingUser(u)}>
                  <Pencil size={14} />
                </button>
                <button className="btn btn-icon btn-ghost btn-sm" title="Reset Password" onClick={() => setResettingUser(u)}>
                  <Key size={14} />
                </button>
                <button className="btn btn-icon btn-ghost btn-sm" title={u.active ? "Deactivate" : "Activate"}
                  onClick={async () => {
                    try {
                      await adminApi.updateUser(u.id, { active: !u.active });
                      toast("success", `User ${u.active ? "deactivated" : "activated"}`);
                      reload();
                    } catch (err) {
                      toast("error", err instanceof Error ? err.message : "Failed to update user");
                    }
                  }}>
                  <Power size={14} style={{ color: u.active ? "var(--rag-red)" : "var(--rag-green)" }} />
                </button>
              </div>,
            ])}
          />
        )}
      </Section>

      {showCreate && <CreateUserModal onClose={() => setShowCreate(false)} onCreated={reload} />}
      {editingUser && <EditUserModal user={editingUser} onClose={() => setEditingUser(null)} onSaved={reload} />}
      {resettingUser && <ResetPasswordDialog user={resettingUser} onClose={() => setResettingUser(null)} />}
    </>
  );
}

function CreateUserModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const { toast } = useToast();
  const [form, setForm] = useState({ full_name: "", email: "", role: "student", password: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [showPw, setShowPw] = useState(false);

  const ROLE_PERMISSIONS: Record<string, { label: string; desc: string; permissions: string[] }> = {
    student: {
      label: "Student",
      desc: "Can take tests, practise, view own reports",
      permissions: ["Take assigned tests", "View own results & reports", "Practice drills & quizzes"],
    },
    tenant_admin: {
      label: "Institution Admin",
      desc: "Full access to manage users, assessments, and reports",
      permissions: ["Create & manage users", "Import users in bulk", "Create & publish assessments", "View all institution reports", "Manage placement season"],
    },
  };

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

  const selectedRole = ROLE_PERMISSIONS[form.role];

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
            <label className="ds-label">Role &amp; Permissions</label>
            <select className="ds-select" value={form.role}
              onChange={(e) => setForm({ ...form, role: e.target.value })}>
              <option value="student">Student</option>

              <option value="tenant_admin">Institution Admin</option>
            </select>
            {selectedRole && (
              <div className="mt-2 p-3 rounded-lg" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
                <div className="text-[11px] font-semibold mb-1">{selectedRole.label} — {selectedRole.desc}</div>
                <ul className="space-y-0.5">
                  {selectedRole.permissions.map((p) => (
                    <li key={p} className="text-[10px] flex items-center gap-1.5" style={{ color: "var(--rag-green)" }}>
                      <span>✓</span> {p}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
          <div>
            <label className="ds-label">Password</label>
            <div className="relative">
              <input className="ds-input pr-10" type={showPw ? "text" : "password"} required value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })} />
              <button type="button" className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-muted hover:text-text"
                      onClick={() => setShowPw(!showPw)} tabIndex={-1}>
                {showPw ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
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

function EditUserModal({ user, onClose, onSaved }: { user: UserRow; onClose: () => void; onSaved: () => void }) {
  const { toast } = useToast();
  const [form, setForm] = useState({ full_name: user.full_name, role: user.role });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await adminApi.updateUser(user.id, { full_name: form.full_name, role: form.role });
      toast("success", "User updated successfully");
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update user");
      setBusy(false);
    }
  }

  return (
    <div className="modal-scrim" onClick={onClose}>
      <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-bold">Edit User</h3>
          <button onClick={onClose} className="btn btn-icon btn-ghost btn-sm"><X size={14} /></button>
        </div>

        <form onSubmit={submit} className="space-y-3">
          <div>
            <label className="ds-label">Full Name</label>
            <input className="ds-input" value={form.full_name} required
              onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
          </div>
          <div>
            <label className="ds-label">Role</label>
            <select className="ds-select" value={form.role}
              onChange={(e) => setForm({ ...form, role: e.target.value })}>
              <option value="student">Student</option>
              <option value="trainer">Trainer</option>
              <option value="tenant_admin">Institution Admin</option>
            </select>
          </div>
          {error && <div className="text-xs font-medium" style={{ color: "var(--rag-red)" }}>{error}</div>}
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" className="btn btn-ghost btn-sm" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary btn-sm" disabled={busy}>
              {busy ? "Saving…" : "Save"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function ResetPasswordDialog({ user, onClose }: { user: UserRow; onClose: () => void }) {
  const { toast } = useToast();
  const [busy, setBusy] = useState(false);
  const [newPassword, setNewPassword] = useState<string | null>(null);
  const [error, setError] = useState("");

  async function confirm() {
    setBusy(true);
    setError("");
    try {
      const res = await adminApi.resetPassword(user.id);
      setNewPassword(res.temporary_password);
      toast("success", "Password reset successfully");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reset password");
      setBusy(false);
    }
  }

  return (
    <div className="modal-scrim" onClick={onClose}>
      <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-bold">Reset Password</h3>
          <button onClick={onClose} className="btn btn-icon btn-ghost btn-sm"><X size={14} /></button>
        </div>

        {newPassword ? (
          <div className="space-y-3">
            <p className="text-xs text-muted">Password has been reset for <strong>{user.full_name}</strong>.</p>
            <div className="p-3 rounded-lg" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
              <div className="text-[10px] font-semibold text-muted mb-1">Temporary Password</div>
              <code className="text-sm font-mono font-medium select-all">{newPassword}</code>
            </div>
            <div className="flex justify-end pt-2">
              <button className="btn btn-primary btn-sm" onClick={onClose}>Done</button>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-xs text-muted">Are you sure you want to reset the password for <strong>{user.full_name}</strong>? A new temporary password will be generated.</p>
            {error && <div className="text-xs font-medium" style={{ color: "var(--rag-red)" }}>{error}</div>}
            <div className="flex justify-end gap-2 pt-2">
              <button className="btn btn-ghost btn-sm" onClick={onClose} disabled={busy}>Cancel</button>
              <button className="btn btn-primary btn-sm" onClick={confirm} disabled={busy}>
                {busy ? "Resetting…" : "Reset Password"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

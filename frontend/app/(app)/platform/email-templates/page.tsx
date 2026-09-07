"use client";
import { useState } from "react";
import { Mail, Plus, Trash2, Edit, Save, Loader2 } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { Badge, EmptyState, ErrorNote, PageHeader, Section, Skeleton } from "@/components/ui";
import { api, type EmailTemplateRow } from "@/lib/api";
import { PLATFORM_ROLES } from "@/lib/roles";
import { useData } from "@/lib/useData";
import { useToast } from "@/components/Toast";

const DEFAULT_TEMPLATES = [
  { key: "first_login", name: "First Login Welcome", subject: "Welcome to CommunicationIQ, {{name}}!", category: "transactional",
    body_html: "<h2>Welcome, {{name}}!</h2><p>Your account is ready. Start practicing to improve your communication skills.</p><p>Login at <a href='{{login_url}}'>CommunicationIQ</a></p>",
    body_text: "Welcome, {{name}}! Your account is ready. Start practicing at {{login_url}}" },
  { key: "report_ready", name: "Exam Report Ready", subject: "Your exam results are ready, {{name}}", category: "transactional",
    body_html: "<h2>Hi {{name}}</h2><p>Your {{exam_name}} results are ready. Score: <strong>{{score}}</strong></p><p>View details at <a href='{{report_url}}'>your dashboard</a></p>",
    body_text: "Hi {{name}}, your {{exam_name}} results are ready. Score: {{score}}. View at {{report_url}}" },
  { key: "weekly_summary", name: "Weekly Progress Summary", subject: "{{name}}'s Weekly Progress Report", category: "transactional",
    body_html: "<h2>Weekly Summary</h2><p>Hi {{name}}, here's your progress this week:</p><ul><li>Questions practiced: {{questions_count}}</li><li>Avg score: {{avg_score}}</li><li>Streak: {{streak}} days</li></ul>",
    body_text: "Hi {{name}}, your weekly progress: {{questions_count}} questions, avg score {{avg_score}}, streak {{streak}} days." },
  { key: "password_reset", name: "Password Reset", subject: "Reset your password", category: "transactional",
    body_html: "<h2>Password Reset</h2><p>Click the link to reset your password: <a href='{{reset_url}}'>Reset Password</a></p><p>This link expires in 1 hour.</p>",
    body_text: "Reset your password: {{reset_url}}. This link expires in 1 hour." },
];

export default function EmailTemplatesPage() {
  return (
    <RequireAuth roles={PLATFORM_ROLES}>
      <EmailTemplates />
    </RequireAuth>
  );
}

function EmailTemplates() {
  const { toast } = useToast();
  const { data, loading, error, reload } = useData(() => api.platformEmailTemplates());
  const [editing, setEditing] = useState<EmailTemplateRow | null>(null);
  const [creating, setCreating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ key: "", name: "", subject: "", body_html: "", body_text: "", category: "transactional", is_active: true });

  const templates = data ?? [];

  const startEdit = (tpl: EmailTemplateRow) => { setEditing(tpl); setCreating(false); setForm({ ...tpl }); };
  const startCreate = () => { setEditing(null); setCreating(true); setForm({ key: "", name: "", subject: "", body_html: "", body_text: "", category: "transactional", is_active: true }); };

  const loadPreset = (preset: typeof DEFAULT_TEMPLATES[0]) => {
    setForm({ ...preset, is_active: true });
    setCreating(true);
    setEditing(null);
  };

  const save = async () => {
    setSaving(true);
    try {
      if (editing) {
        await api.updateEmailTemplate(editing.id, form);
        toast("success", "Template updated");
      } else {
        await api.createEmailTemplate(form);
        toast("success", "Template created");
      }
      setEditing(null);
      setCreating(false);
      reload();
    } catch (e) {
      toast("error", (e instanceof Error ? e.message : String(e)) || "Failed");
    }
    setSaving(false);
  };

  const remove = async (id: string) => {
    if (!confirm("Delete this template?")) return;
    try {
      await api.deleteEmailTemplate(id);
      toast("success", "Deleted");
      reload();
    } catch (e) {
      toast("error", (e instanceof Error ? e.message : String(e)) || "Failed");
    }
  };

  return (
    <>
      <PageHeader
        title="Email Templates"
        sub="Reusable email templates for automated notifications."
        action={
          <button onClick={startCreate} className="btn btn-primary btn-sm flex items-center gap-1">
            <Plus size={14} /> New Template
          </button>
        }
      />

      {loading ? <Skeleton rows={4} /> : error ? <ErrorNote message={error} /> : (
        <>
          {templates.length === 0 && !creating && (
            <div className="mb-4">
              <EmptyState title="No templates yet" desc="Create a template or load a preset below." />
              <Section title="Quick Start Presets" className="mt-4">
                <div className="grid grid-cols-2 gap-2">
                  {DEFAULT_TEMPLATES.map((p) => (
                    <button key={p.key} onClick={() => loadPreset(p)}
                      className="text-left p-3 rounded border hover:bg-surface2" style={{ borderColor: "var(--border)" }}>
                      <div className="text-xs font-semibold">{p.name}</div>
                      <div className="text-[10px] text-muted mt-0.5">{p.key}</div>
                    </button>
                  ))}
                </div>
              </Section>
            </div>
          )}

          {(creating || editing) && (
            <Section title={editing ? "Edit Template" : "New Template"} className="mb-4">
              <div className="grid grid-cols-2 gap-3">
                <label className="block">
                  <span className="text-[10px] font-bold uppercase text-muted">Key *</span>
                  <input value={form.key} onChange={(e) => setForm({ ...form, key: e.target.value })}
                    placeholder="first_login"
                    className="w-full text-xs p-1.5 rounded border bg-transparent mt-1 font-mono" style={{ borderColor: "var(--border)" }} />
                </label>
                <label className="block">
                  <span className="text-[10px] font-bold uppercase text-muted">Name</span>
                  <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                    className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }} />
                </label>
                <label className="block col-span-2">
                  <span className="text-[10px] font-bold uppercase text-muted">Subject *</span>
                  <input value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })}
                    placeholder="Welcome, {{name}}!"
                    className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }} />
                </label>
                <label className="block col-span-2">
                  <span className="text-[10px] font-bold uppercase text-muted">HTML Body</span>
                  <textarea value={form.body_html} onChange={(e) => setForm({ ...form, body_html: e.target.value })}
                    rows={6}
                    className="w-full text-xs p-1.5 rounded border bg-transparent mt-1 font-mono" style={{ borderColor: "var(--border)" }} />
                </label>
                <label className="block col-span-2">
                  <span className="text-[10px] font-bold uppercase text-muted">Plain Text Body</span>
                  <textarea value={form.body_text} onChange={(e) => setForm({ ...form, body_text: e.target.value })}
                    rows={3}
                    className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }} />
                </label>
                <label className="block">
                  <span className="text-[10px] font-bold uppercase text-muted">Category</span>
                  <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}
                    className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }}>
                    <option value="transactional">Transactional</option>
                    <option value="marketing">Marketing</option>
                    <option value="system">System</option>
                  </select>
                </label>
                <label className="flex items-center gap-1.5 text-xs cursor-pointer self-end">
                  <input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />
                  Active
                </label>
              </div>
              <p className="text-[10px] text-muted mt-2">Use {'{{variable}}'} syntax for dynamic content. Available: {'{{name}}'}, {'{{email}}'}, {'{{login_url}}'}, {'{{exam_name}}'}, {'{{score}}'}, {'{{report_url}}'}</p>
              <div className="flex gap-2 mt-3">
                <button onClick={save} disabled={saving || !form.key || !form.subject}
                  className="px-3 py-1.5 text-xs rounded text-white disabled:opacity-50 flex items-center gap-1"
                  style={{ background: "var(--brand-grad)" }}>
                  {saving ? <Loader2 size={10} className="animate-spin" /> : <Save size={10} />}
                  {editing ? "Update" : "Create"}
                </button>
                <button onClick={() => { setEditing(null); setCreating(false); }} className="px-3 py-1.5 text-xs rounded bg-surface2 text-muted">Cancel</button>
              </div>
            </Section>
          )}

          <div className="space-y-2">
            {templates.map((tpl) => (
              <div key={tpl.id} className="ds-card p-3 flex items-center gap-3">
                <Mail size={14} style={{ color: "var(--primary)" }} />
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-semibold">{tpl.name || tpl.key}</div>
                  <div className="text-[10px] text-muted truncate">{tpl.subject}</div>
                </div>
                <Badge tone={tpl.is_active ? "var(--rag-green)" : "var(--muted)"}>{tpl.is_active ? "Active" : "Inactive"}</Badge>
                <Badge tone="var(--muted)">{tpl.category}</Badge>
                <div className="flex gap-1">
                  <button onClick={() => startEdit(tpl)} className="p-1 rounded hover:bg-surface2"><Edit size={11} /></button>
                  <button onClick={() => remove(tpl.id)} className="p-1 rounded hover:bg-surface2" style={{ color: "var(--rag-red)" }}><Trash2 size={11} /></button>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </>
  );
}

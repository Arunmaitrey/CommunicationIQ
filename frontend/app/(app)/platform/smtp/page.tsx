"use client";
import { useState, useEffect } from "react";
import { Send, Save, Loader2 } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { PageHeader, Section } from "@/components/ui";
import { api } from "@/lib/api";
import { PLATFORM_ROLES } from "@/lib/roles";
import { useToast } from "@/components/Toast";

export default function SmtpPage() {
  return (
    <RequireAuth roles={PLATFORM_ROLES}>
      <SmtpSettings />
    </RequireAuth>
  );
}

function SmtpSettings() {
  const { toast } = useToast();
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testEmail, setTestEmail] = useState("");
  const [form, setForm] = useState({
    host: "", port: 587, username: "", password: "",
    from_email: "", from_name: "CommunicationIQ",
    use_tls: true, use_ssl: false, is_active: true,
  });

  useEffect(() => {
    (async () => {
      try {
        const data = await api.platformSmtp();
        if (data) setForm((prev) => ({ ...prev, ...data, password: "" }));
      } catch {}
    })();
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      await api.saveSmtp(form);
      toast("success", "SMTP settings saved");
    } catch (e) {
      toast("error", (e instanceof Error ? e.message : String(e)) || "Failed");
    }
    setSaving(false);
  };

  const sendTest = async () => {
    if (!testEmail) return;
    setTesting(true);
    try {
      const res = await api.testSmtp({ ...form, to_email: testEmail });
      toast(res.ok ? "success" : "error", res.message);
    } catch (e) {
      toast("error", (e instanceof Error ? e.message : String(e)) || "Failed");
    }
    setTesting(false);
  };

  return (
    <>
      <PageHeader title="Email / SMTP Settings" sub="Configure email sending for notifications, welcome emails, and reports." />

      <Section className="mb-4">
        <div className="grid grid-cols-2 gap-3">
          <label className="block">
            <span className="text-[10px] font-bold uppercase text-muted">SMTP Host *</span>
            <input value={form.host} onChange={(e) => setForm({ ...form, host: e.target.value })}
              placeholder="smtp.gmail.com"
              className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }} />
          </label>
          <label className="block">
            <span className="text-[10px] font-bold uppercase text-muted">Port</span>
            <input type="number" value={form.port} onChange={(e) => setForm({ ...form, port: Number(e.target.value) })}
              className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }} />
          </label>
          <label className="block">
            <span className="text-[10px] font-bold uppercase text-muted">Username</span>
            <input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })}
              placeholder="your@gmail.com"
              className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }} />
          </label>
          <label className="block">
            <span className="text-[10px] font-bold uppercase text-muted">Password / App Key</span>
            <input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })}
              placeholder="••••••••"
              className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }} />
          </label>
          <label className="block">
            <span className="text-[10px] font-bold uppercase text-muted">From Email *</span>
            <input value={form.from_email} onChange={(e) => setForm({ ...form, from_email: e.target.value })}
              placeholder="noreply@communicationiq.com"
              className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }} />
          </label>
          <label className="block">
            <span className="text-[10px] font-bold uppercase text-muted">From Name</span>
            <input value={form.from_name} onChange={(e) => setForm({ ...form, from_name: e.target.value })}
              className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }} />
          </label>
        </div>
        <div className="flex gap-4 mt-3">
          <label className="flex items-center gap-1.5 text-xs cursor-pointer">
            <input type="checkbox" checked={form.use_tls} onChange={(e) => setForm({ ...form, use_tls: e.target.checked })} />
            Use TLS
          </label>
          <label className="flex items-center gap-1.5 text-xs cursor-pointer">
            <input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />
            Active
          </label>
        </div>
        <button onClick={save} disabled={saving || !form.host || !form.from_email}
          className="mt-4 px-4 py-2 text-xs rounded text-white disabled:opacity-50 flex items-center gap-2"
          style={{ background: "var(--brand-grad)" }}>
          {saving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
          Save SMTP Settings
        </button>
      </Section>

      <Section title="Send Test Email">
        <div className="flex gap-2 items-end">
          <label className="flex-1">
            <span className="text-[10px] font-bold uppercase text-muted">To Email</span>
            <input value={testEmail} onChange={(e) => setTestEmail(e.target.value)}
              placeholder="test@example.com"
              className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }} />
          </label>
          <button onClick={sendTest} disabled={testing || !testEmail}
            className="px-3 py-1.5 text-xs rounded text-white disabled:opacity-50 flex items-center gap-1"
            style={{ background: "var(--primary)" }}>
            {testing ? <Loader2 size={10} className="animate-spin" /> : <Send size={10} />}
            Send Test
          </button>
        </div>
        <p className="text-[10px] text-muted mt-2">Uses Gmail SMTP by default. For Gmail, use an App Password (not your regular password). Go to myaccount.google.com → Security → 2FA → App Passwords.</p>
      </Section>
    </>
  );
}

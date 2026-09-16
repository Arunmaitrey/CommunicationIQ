"use client";
import { useState } from "react";
import { Check, Lock, Eye, EyeOff, Camera, Loader2 } from "lucide-react";
import { useRole } from "@/components/RoleProvider";
import { THEMES, THEME_GROUPS, useTheme, type ThemeId } from "@/components/ThemeProvider";
import { PageHeader, Section } from "@/components/ui";
import { ROLE_LABEL } from "@/lib/roles";
import { api, API_BASE, ApiError, getToken } from "@/lib/api"
import { useToast } from "@/components/Toast"

type SettingsTab = "account" | "security" | "profile" | "notifications" | "appearance";

const TABS: { id: SettingsTab; label: string; forStudent?: boolean }[] = [
  { id: "account", label: "Account" },
  { id: "security", label: "Security" },
  { id: "profile", label: "Profile", forStudent: true },
  { id: "notifications", label: "Notifications" },
  { id: "appearance", label: "Appearance" },
];

export default function SettingsPage() {
  const { user } = useRole();
  const { theme, setTheme } = useTheme();
  const [tab, setTab] = useState<SettingsTab>("account");

  const visibleTabs = TABS.filter((t) => !t.forStudent || user?.role === "student");

  return (
    <>
      <PageHeader
        title="Settings"
        sub="Your account and how the app looks to you."
      />

      {/* Tab bar */}
      <div className="flex gap-1 mb-4 overflow-x-auto pb-1">
        {visibleTabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-colors ds-focus ${
              tab === t.id
                ? "text-white"
                : "text-muted hover:text-text hover:bg-surface2"
            }`}
            style={tab === t.id ? { background: "var(--primary)" } : undefined}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {tab === "account" && (
        <Section title="Account details" className="mb-4">
          <p className="text-xs text-muted mb-4 leading-relaxed">
            Your identity on this platform. This information is visible to your institution administrators.
          </p>
          <div className="flex items-center gap-4 mb-4">
            <div className="relative group">
              <div className="w-16 h-16 rounded-full flex items-center justify-center text-xl font-bold overflow-hidden"
                style={{ background: "var(--brand-grad)", color: "white" }}>
                {user?.avatar_url ? (
                  <img src={user.avatar_url} alt="Avatar" className="w-full h-full object-cover" />
                ) : (
                  <span>{user?.full_name?.charAt(0) || user?.email?.charAt(0) || "U"}</span>
                )}
              </div>
              <AvatarUploadButton />
            </div>
            <dl className="grid sm:grid-cols-2 gap-3 text-xs flex-1">
              <Field label="Name" value={user?.full_name ?? "—"} />
              <Field label="Email" value={user?.email ?? "—"} />
              <Field label="Role" value={user ? ROLE_LABEL[user.role] ?? user.role : "—"} />
              <Field label="Institution" value={user?.tenant_name ?? "Platform console"} />
            </dl>
          </div>
        </Section>
      )}

      {tab === "security" && (
        <Section title="Change Password" className="mb-4">
          <p className="text-xs text-muted mb-4 leading-relaxed">
            Update your password regularly to keep your account secure. Your new password must be at least 8 characters.
          </p>
          <ChangePasswordForm />
        </Section>
      )}

      {tab === "profile" && user?.role === "student" && (
        <Section title="Student Profile" className="mb-4">
          <p className="text-xs text-muted mb-4 leading-relaxed">
            Your academic details help tailor the assessment experience. Roll number and branch are used for institutional reporting.
          </p>
          <StudentProfileForm />
        </Section>
      )}

      {tab === "notifications" && (
        <Section title="Notification Preferences" className="mb-4">
          <p className="text-xs text-muted mb-4 leading-relaxed">
            Choose what notifications you receive. Practice reminders help maintain your streak; exam alerts notify you of upcoming deadlines.
          </p>
          <NotificationPrefs />
        </Section>
      )}

      {tab === "appearance" && (
        <Section title="Appearance">
          <p className="text-xs text-muted mb-4 leading-relaxed">
            Every screen in the product is built from the same design tokens, so all themes work everywhere.
            Pick whichever you can read for twenty minutes at a stretch. Your choice is saved to your account.
          </p>

          {THEME_GROUPS.map((group) => (
            <div key={group} className="mb-4 last:mb-0">
              <div className="text-[10px] font-bold uppercase tracking-wider text-muted mb-2">
                {group}
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
                {THEMES.filter((t) => t.group === group).map((t) => (
                  <button
                    key={t.id}
                    onClick={() => setTheme(t.id as ThemeId)}
                    className="ds-card p-2.5 text-left hover:bg-surface2 transition-colors ds-focus"
                    style={t.id === theme ? { borderColor: "var(--primary)" } : undefined}
                  >
                    <div data-theme={t.id} className="rounded mb-2 p-2.5 flex gap-1.5"
                         style={{ background: "var(--bg)", border: "1px solid var(--border)" }}>
                      <i className="block w-4 h-4 rounded" style={{ background: "var(--primary)" }} />
                      <i className="block w-4 h-4 rounded" style={{ background: "var(--secondary)" }} />
                      <i className="block w-4 h-4 rounded" style={{ background: "var(--accent)" }} />
                      <i className="block w-4 h-4 rounded" style={{ background: "var(--surface-2)" }} />
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span className="text-xs font-semibold flex-1 truncate">{t.label}</span>
                      {t.id === theme && <Check size={13} className="text-primary shrink-0" />}
                    </div>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </Section>
      )}
    </>
  );
}

function ChangePasswordForm() {
  const { toast } = useToast();
  const [form, setForm] = useState({ current: "", newPass: "", confirm: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [ok, setOk] = useState(false);
  const [showCurrent, setShowCurrent] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (form.newPass !== form.confirm) {
      setError("New passwords do not match");
      return;
    }
    if (form.newPass.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }
    setBusy(true);
    setError("");
    setOk(false);
    try {
      const token = getToken();
      const res = await fetch(`${API_BASE}/auth/change-password`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          current_password: form.current,
          new_password: form.newPass,
        }),
      });
      if (!res.ok) {
        let detail = res.statusText;
        try { detail = (await res.json())?.detail ?? detail; } catch { /* */ }
        throw new ApiError(res.status, detail);
      }
      setOk(true);
      toast("success", "Password changed successfully");
      setForm({ current: "", newPass: "", confirm: "" });
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Could not change password";
      setError(msg);
      toast("error", msg);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3 max-w-sm">
      <div>
        <label className="ds-label" htmlFor="cur_pw">Current password</label>
        <div className="relative">
          <input id="cur_pw" type={showCurrent ? "text" : "password"} required className="ds-input w-full ds-focus pr-10"
                 value={form.current}
                 onChange={(e) => setForm({ ...form, current: e.target.value })} />
          <button type="button" className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-muted hover:text-text"
                  onClick={() => setShowCurrent(!showCurrent)} tabIndex={-1}>
            {showCurrent ? <EyeOff size={14} /> : <Eye size={14} />}
          </button>
        </div>
      </div>
      <div>
        <label className="ds-label" htmlFor="new_pw">New password</label>
        <div className="relative">
          <input id="new_pw" type={showNew ? "text" : "password"} required minLength={8} className="ds-input w-full ds-focus pr-10"
                 value={form.newPass}
                 onChange={(e) => setForm({ ...form, newPass: e.target.value })} />
          <button type="button" className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-muted hover:text-text"
                  onClick={() => setShowNew(!showNew)} tabIndex={-1}>
            {showNew ? <EyeOff size={14} /> : <Eye size={14} />}
          </button>
        </div>
      </div>
      <div>
        <label className="ds-label" htmlFor="confirm_pw">Confirm new password</label>
        <div className="relative">
          <input id="confirm_pw" type={showConfirm ? "text" : "password"} required minLength={8} className="ds-input w-full ds-focus pr-10"
                 value={form.confirm}
                 onChange={(e) => setForm({ ...form, confirm: e.target.value })} />
          <button type="button" className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-muted hover:text-text"
                  onClick={() => setShowConfirm(!showConfirm)} tabIndex={-1}>
            {showConfirm ? <EyeOff size={14} /> : <Eye size={14} />}
          </button>
        </div>
      </div>
      {error && <div className="text-xs" style={{ color: "var(--rag-red)" }}>{error}</div>}
      {ok && <div className="text-xs" style={{ color: "var(--rag-green)" }}>Password changed successfully.</div>}
      <button type="submit" disabled={busy} className="btn btn-primary btn-sm ds-focus">
        <Lock size={13} /> {busy ? "Changing…" : "Change password"}
      </button>
    </form>
  );
}

function StudentProfileForm() {
  const { user } = useRole();
  const { toast } = useToast();
  const [fullName, setFullName] = useState(user?.full_name ?? "");
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    try {
      await api.savePreferences({ full_name: fullName });
      toast("success", "Profile updated");
    } catch (err) {
      toast("error", err instanceof ApiError ? err.message : "Could not save profile");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3 max-w-sm">
      <div>
        <label className="ds-label" htmlFor="pf_name">Full Name</label>
        <input id="pf_name" className="ds-input w-full ds-focus" value={fullName}
               onChange={(e) => setFullName(e.target.value)} />
      </div>
      <dl className="grid sm:grid-cols-2 gap-3 text-xs">
        <Field label="Roll Number" value={user?.roll_number || "Not set"} />
        <Field label="Branch" value={user?.branch || "Not set"} />
        <Field label="Year of Study" value={user?.year_of_study ? String(user.year_of_study) : "Not set"} />
        <Field label="L1 Language" value={user?.l1_language || "Not set"} />
      </dl>
      <button type="button" disabled={busy} onClick={save} className="btn btn-primary btn-sm ds-focus">
        {busy ? "Saving…" : "Save Profile"}
      </button>
    </div>
  );
}

function NotificationPrefs() {
  const [practiceReminders, setPracticeReminders] = useState(() => {
    try { return localStorage.getItem("commiq.prefs.practiceReminders") !== "false"; } catch { return true; }
  });
  const [examAlerts, setExamAlerts] = useState(() => {
    try { return localStorage.getItem("commiq.prefs.examAlerts") !== "false"; } catch { return true; }
  });

  function toggle(key: string, value: boolean, setter: (v: boolean) => void) {
    setter(value);
    try { localStorage.setItem(`commiq.prefs.${key}`, String(value)); } catch { /* */ }
  }

  return (
    <div className="space-y-3 max-w-sm">
      <label className="flex items-center gap-3 cursor-pointer">
        <input type="checkbox" checked={practiceReminders}
               onChange={(e) => toggle("practiceReminders", e.target.checked, setPracticeReminders)}
               className="ds-focus" />
        <span className="text-xs">Practice reminders</span>
      </label>
      <label className="flex items-center gap-3 cursor-pointer">
        <input type="checkbox" checked={examAlerts}
               onChange={(e) => toggle("examAlerts", e.target.checked, setExamAlerts)}
               className="ds-focus" />
        <span className="text-xs">Exam deadline alerts</span>
      </label>
    </div>
  );
}

function AvatarUploadButton() {
  const { toast } = useToast();
  const { user } = useRole();
  const [uploading, setUploading] = useState(false);
  const inputRef = useState<{ el: HTMLInputElement | null }>({ el: null });

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const token = getToken();
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch(`${API_BASE}/auth/avatar`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: formData,
      });
      if (!res.ok) throw new Error("Upload failed");
      const data = await res.json();
      toast("success", "Avatar updated");
      window.location.reload();
    } catch {
      toast("error", "Failed to upload avatar");
    } finally {
      setUploading(false);
      if (inputRef[0].el) inputRef[0].el.value = "";
    }
  };

  return (
    <>
      <input ref={(el) => { inputRef[0].el = el; }} type="file" accept="image/*" className="hidden" onChange={handleUpload} />
      <button
        onClick={() => inputRef[0].el?.click()}
        disabled={uploading}
        className="absolute -bottom-1 -right-1 w-7 h-7 rounded-full flex items-center justify-center text-white shadow-lg hover:opacity-90 transition-opacity"
        style={{ background: "var(--primary)" }}
        title="Change avatar"
      >
        {uploading ? <Loader2 size={12} className="animate-spin" /> : <Camera size={12} />}
      </button>
    </>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="ds-inset p-2.5">
      <dt className="text-[10px] font-bold uppercase tracking-wide text-muted">{label}</dt>
      <dd className="mt-0.5 font-medium">{value}</dd>
    </div>
  );
}

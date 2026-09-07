"use client";
import { useEffect, useState } from "react";
import {
  Check, Compass, Eye, EyeOff, KeyRound, ShieldCheck, User as UserIcon,
} from "lucide-react";
import { useRole } from "@/components/RoleProvider";
import { THEMES, THEME_GROUPS, useTheme, type ThemeId } from "@/components/ThemeProvider";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { useOnboarding } from "@/components/onboarding/OnboardingProvider";
import { useToast } from "@/components/Toast";
import { ErrorNote, PageHeader, Section } from "@/components/ui";
import { api, ApiError, type SessionUser } from "@/lib/api";
import { useData } from "@/lib/useData";
import { ROLE_LABEL } from "@/lib/roles";

// Mirrors backend/app/importer.py's VALID_L1 exactly, so a value saved here
// is always one the CSV importer and the narration pipeline also recognise.
const L1_LANGUAGES = [
  { value: "", label: "Not set" },
  { value: "telugu", label: "Telugu" },
  { value: "hindi", label: "Hindi" },
  { value: "tamil", label: "Tamil" },
  { value: "kannada", label: "Kannada" },
  { value: "malayalam", label: "Malayalam" },
  { value: "marathi", label: "Marathi" },
  { value: "bengali", label: "Bengali" },
  { value: "gujarati", label: "Gujarati" },
  { value: "punjabi", label: "Punjabi" },
  { value: "odia", label: "Odia" },
  { value: "other", label: "Other" },
];

export default function SettingsPage() {
  const { user, refresh } = useRole();
  const { theme, setTheme } = useTheme();
  const { available: tourAvailable, restartTour } = useOnboarding();
  const isTenant = user?.scope === "tenant";
  const isStudent = user?.role === "student";

  // Interface language is chosen via LanguageSwitcher, which manages its own
  // localStorage state and broadcasts "locale-changed" on every pick. Rather
  // than modify that shared component, this listens for the event it already
  // fires and persists it server-side alongside the localStorage copy.
  useEffect(() => {
    if (!isTenant) return;
    const onChange = (e: Event) => {
      const code = (e as CustomEvent<string>).detail;
      if (code) api.updatePreferences({ ui_language: code }).catch(() => {});
    };
    window.addEventListener("locale-changed", onChange);
    return () => window.removeEventListener("locale-changed", onChange);
  }, [isTenant]);

  return (
    <>
      <PageHeader
        title="Settings"
        sub="Your account, your security, and how the app looks and feels to you."
      />

      <ProfileSection user={user} isTenant={isTenant} onSaved={refresh} />

      <SecuritySection />

      {isStudent && <PrivacySection />}

      <Section title="Language" className="mb-4">
        <p className="text-xs text-muted mb-3 leading-relaxed">
          Choose the language for feedback messages and UI hints. Practice
          content stays in English — only explanations switch.
        </p>
        <LanguageSwitcher />
      </Section>

      <Section title={`Theme — ${THEMES.length} available`} className="mb-4">
        <p className="text-xs text-muted mb-4 leading-relaxed">
          Every screen in the product is built from the same design tokens, so all
          sixteen work everywhere — including the test runner and the score reveal.
          Pick whichever you can read for twenty minutes at a stretch.
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
                  onClick={() => {
                    setTheme(t.id as ThemeId);
                    if (isTenant) api.updatePreferences({ preferred_theme: t.id }).catch(() => {});
                  }}
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

      {tourAvailable && (
        <Section title="Help" className="mb-4">
          <p className="text-xs text-muted mb-3 leading-relaxed">
            Replay the welcome tour to see what's where and what to do first.
          </p>
          <button type="button" onClick={restartTour} className="btn btn-soft btn-sm">
            <Compass size={14} />
            Replay the product tour
          </button>
        </Section>
      )}

      <Section title="Account">
        <dl className="grid sm:grid-cols-2 gap-3 text-xs">
          <Field label="Email" value={user?.email ?? "—"} />
          <Field label="Role" value={user ? ROLE_LABEL[user.role] ?? user.role : "—"} />
          <Field label="Institution" value={user?.tenant_name ?? "Platform console"} />
        </dl>
      </Section>
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

/** Name, and — for a tenant account — the language explanations should be
 *  gently shaped toward. Saves to the self-service PATCH /auth/profile,
 *  the counterpart to the admin-only endpoint that edits someone else. */
function ProfileSection({ user, isTenant, onSaved }: {
  user: SessionUser | null;
  isTenant: boolean;
  onSaved: () => Promise<void>;
}) {
  const { toast } = useToast();
  const [fullName, setFullName] = useState(user?.full_name ?? "");
  const [l1, setL1] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => { setFullName(user?.full_name ?? ""); }, [user?.full_name]);

  const dirty = user != null && fullName.trim() !== user.full_name;

  async function save() {
    if (!fullName.trim()) {
      setError("Name can't be empty.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await api.updateProfile({
        full_name: fullName.trim(),
        ...(isTenant ? { l1_language: l1 } : {}),
      });
      await onSaved();
      toast("success", "Profile updated");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not save your profile");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Section title="Profile" className="mb-4">
      <div className="grid sm:grid-cols-2 gap-3 max-w-xl">
        <div>
          <label className="ds-label" htmlFor="settings-name">Full name</label>
          <input
            id="settings-name" className="ds-input" value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            maxLength={120}
          />
        </div>
        {isTenant && (
          <div>
            <label className="ds-label" htmlFor="settings-l1">
              Feedback shaped toward
            </label>
            <select
              id="settings-l1" className="ds-select" value={l1}
              onChange={(e) => setL1(e.target.value)}
            >
              {L1_LANGUAGES.map((l) => (
                <option key={l.value} value={l.value}>{l.label}</option>
              ))}
            </select>
          </div>
        )}
      </div>

      {error && <div className="mt-3 max-w-xl"><ErrorNote message={error} /></div>}

      <button
        type="button" onClick={save} disabled={busy || !dirty}
        className="btn btn-primary btn-sm mt-4"
      >
        <UserIcon size={14} />
        {busy ? "Saving…" : "Save profile"}
      </button>
    </Section>
  );
}

/** Self-service password change. Wired to POST /auth/change-password,
 *  which — as a side effect for a tenant account — also clears
 *  must_change_password if an admin had reset it. */
function SecuritySection() {
  const { toast } = useToast();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showCurrent, setShowCurrent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const mismatch = confirm.length > 0 && next !== confirm;
  const tooShort = next.length > 0 && next.length < 8;
  const canSave = current.length > 0 && next.length >= 8 && next === confirm;

  async function save() {
    setBusy(true);
    setError("");
    try {
      await api.changePassword(current, next);
      setCurrent(""); setNext(""); setConfirm("");
      toast("success", "Password changed");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not change your password");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Section title="Security" className="mb-4">
      <p className="text-xs text-muted mb-3 leading-relaxed">
        Use a password you don't use anywhere else.
      </p>

      <div className="grid gap-3 max-w-xl">
        <div>
          <label className="ds-label" htmlFor="settings-current-pw">Current password</label>
          <div className="relative">
            <input
              id="settings-current-pw" className="ds-input pr-9"
              type={showCurrent ? "text" : "password"}
              value={current} onChange={(e) => setCurrent(e.target.value)}
              autoComplete="current-password"
            />
            <button
              type="button" onClick={() => setShowCurrent((v) => !v)}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-muted"
              aria-label={showCurrent ? "Hide password" : "Show password"}
              tabIndex={-1}
            >
              {showCurrent ? <EyeOff size={14} /> : <Eye size={14} />}
            </button>
          </div>
        </div>

        <div className="grid sm:grid-cols-2 gap-3">
          <div>
            <label className="ds-label" htmlFor="settings-new-pw">New password</label>
            <input
              id="settings-new-pw" className="ds-input" type="password"
              value={next} onChange={(e) => setNext(e.target.value)}
              autoComplete="new-password"
            />
            {tooShort && (
              <p className="mt-1 text-[11px]" style={{ color: "var(--rag-amber)" }}>
                At least 8 characters.
              </p>
            )}
          </div>
          <div>
            <label className="ds-label" htmlFor="settings-confirm-pw">Confirm new password</label>
            <input
              id="settings-confirm-pw" className="ds-input" type="password"
              value={confirm} onChange={(e) => setConfirm(e.target.value)}
              autoComplete="new-password"
            />
            {mismatch && (
              <p className="mt-1 text-[11px]" style={{ color: "var(--rag-red)" }}>
                Doesn't match.
              </p>
            )}
          </div>
        </div>
      </div>

      {error && <div className="mt-3 max-w-xl"><ErrorNote message={error} /></div>}

      <button
        type="button" onClick={save} disabled={busy || !canSave}
        className="btn btn-primary btn-sm mt-4"
      >
        <KeyRound size={14} />
        {busy ? "Changing…" : "Change password"}
      </button>
    </Section>
  );
}

/** The three optional consent scopes the /consent page also manages,
 *  surfaced here so a student doesn't have to hunt down the original
 *  consent screen to change their mind later. "recording" is shown as a
 *  status, not a toggle -- it's required to take any assessment, and
 *  revoking it belongs on the dedicated consent flow, not buried here.
 *  ai_explanation is deliberately left out: the /consent page's own save
 *  doesn't know about it yet, and since a consent save replaces every
 *  scope at once, adding a fourth toggle only here would make a later
 *  save from /consent silently revert it. */
function PrivacySection() {
  const { toast } = useToast();
  const { data: consent } = useData(() => api.getConsent());
  const [recordingGranted, setRecordingGranted] = useState(false);
  const [training, setTraining] = useState(false);
  const [outcome, setOutcome] = useState(false);
  const [notifications, setNotifications] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!consent) return;
    setRecordingGranted(consent.granted.includes("recording"));
    setTraining(consent.granted.includes("training_data"));
    setOutcome(consent.granted.includes("outcome_sharing"));
    setNotifications(consent.granted.includes("notifications"));
  }, [consent]);

  async function save() {
    setBusy(true);
    setError("");
    const scopes = [
      ...(recordingGranted ? ["recording"] : []),
      ...(training ? ["training_data"] : []),
      ...(outcome ? ["outcome_sharing"] : []),
      ...(notifications ? ["notifications"] : []),
    ];
    try {
      await api.giveConsent(scopes);
      toast("success", "Privacy choices saved");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not save your choices");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Section title="Notifications & Privacy" className="mb-4">
      <div className="space-y-3">
        <div className="ds-inset p-3 flex items-start gap-3">
          <ShieldCheck size={16} className="mt-0.5 shrink-0" style={{ color: "var(--rag-green)" }} />
          <span>
            <span className="text-xs font-semibold block">Record and score my speech</span>
            <span className="text-[11px] text-muted block mt-0.5 leading-relaxed">
              {recordingGranted
                ? "Granted — required to take any simulation."
                : "Not granted — you'll be asked again before your next simulation."}
            </span>
          </span>
        </div>
        <Toggle
          checked={training} onChange={setTraining}
          label="Use my recordings to improve the scoring models"
          note="Optional. Declining changes nothing about your own scores or your report."
        />
        <Toggle
          checked={outcome} onChange={setOutcome}
          label="Let my institution link my practice to my placement outcome"
          note="Optional. Your individual outcome is never shown to other students."
        />
        <Toggle
          checked={notifications} onChange={setNotifications}
          label="Send me practice reminders"
          note="Optional. At most one a day, quiet hours respected."
        />
      </div>

      {error && <div className="mt-3"><ErrorNote message={error} /></div>}

      <button
        type="button" onClick={save} disabled={busy}
        className="btn btn-primary btn-sm mt-4"
      >
        <Check size={14} />
        {busy ? "Saving…" : "Save choices"}
      </button>
    </Section>
  );
}

function Toggle({ checked, onChange, label, note }: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  note: string;
}) {
  return (
    <label className="ds-inset p-3 flex items-start gap-3 cursor-pointer">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 ds-focus"
        style={{ accentColor: "var(--primary)", width: 16, height: 16 }}
      />
      <span>
        <span className="text-xs font-semibold block">{label}</span>
        <span className="text-[11px] text-muted block mt-0.5 leading-relaxed">{note}</span>
      </span>
    </label>
  );
}

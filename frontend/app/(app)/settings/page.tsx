"use client";
import { Check } from "lucide-react";
import { useRole } from "@/components/RoleProvider";
import { THEMES, THEME_GROUPS, useTheme, type ThemeId } from "@/components/ThemeProvider";
import { PageHeader, Section } from "@/components/ui";
import { ROLE_LABEL } from "@/lib/roles";

export default function SettingsPage() {
  const { user } = useRole();
  const { theme, setTheme } = useTheme();

  return (
    <>
      <PageHeader
        title="Settings"
        sub="Your account and how the app looks to you. A theme is a personal preference — it follows your account on this device, not the machine."
      />

      <Section title="Account" className="mb-4">
        <dl className="grid sm:grid-cols-2 gap-3 text-xs">
          <Field label="Name" value={user?.full_name ?? "—"} />
          <Field label="Email" value={user?.email ?? "—"} />
          <Field label="Role" value={user ? ROLE_LABEL[user.role] ?? user.role : "—"} />
          <Field label="Institution" value={user?.tenant_name ?? "Platform console"} />
        </dl>
      </Section>

      <Section title={`Theme — ${THEMES.length} available`}>
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

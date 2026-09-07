"use client";
import { Compass, Sparkles } from "lucide-react";
import { useRole } from "@/components/RoleProvider";
import { useOnboarding } from "./OnboardingProvider";
import type { Role } from "@/lib/api";

const COPY: Partial<Record<Role, { headline: string; bullets: string[] }>> = {
  student: {
    headline: "Simulate the real test, and see exactly what to fix.",
    bullets: [
      "Take timed, one-shot assessments that feel like the real thing.",
      "Get a report that names the one change that moves your score most.",
      "Short daily practice keeps your streak going and your skills sharp.",
    ],
  },
  trainer: {
    headline: "See who's ready, who's drifting, and who needs you next.",
    bullets: [
      "Cohort-level readiness bands, updated as students test.",
      "A momentum view of who's actually practising.",
      "At-risk flags surface automatically — nothing to check for manually.",
    ],
  },
  tenant_admin: {
    headline: "Run your institution's placement prep from one console.",
    bullets: [
      "Add people one at a time or bulk-import a whole cohort.",
      "One-time invitation links for candidates who need a single assessment.",
      "Readiness and results across every cohort, in one place.",
    ],
  },
};

export function WelcomeModal() {
  const { user } = useRole();
  const { welcomeOpen, startTour, dismissWelcome } = useOnboarding();

  if (!welcomeOpen || !user) return null;
  const copy = COPY[user.role] ?? COPY.student!;

  return (
    <div className="onboarding-scrim" role="dialog" aria-modal="true" aria-labelledby="welcome-title">
      <div className="modal-panel text-center">
        <div
          className="w-14 h-14 rounded-full mx-auto mb-4 flex items-center justify-center"
          style={{ background: "color-mix(in srgb, var(--brand) 15%, transparent)" }}
        >
          <Sparkles size={26} style={{ color: "var(--brand)" }} />
        </div>

        <h2 id="welcome-title" className="text-lg font-bold" style={{ color: "var(--text)" }}>
          Welcome, {user.full_name.split(" ")[0]}
        </h2>
        <p className="mt-2 text-sm leading-relaxed" style={{ color: "var(--muted)" }}>
          {copy.headline}
        </p>

        <ul className="mt-4 space-y-2.5 text-left text-[13px]">
          {copy.bullets.map((b) => (
            <li key={b} className="flex items-start gap-2.5">
              <span
                className="mt-0.5 w-4 h-4 rounded-full shrink-0 flex items-center justify-center"
                style={{ background: "color-mix(in srgb, var(--brand) 18%, transparent)" }}
              >
                <span className="w-1.5 h-1.5 rounded-full" style={{ background: "var(--brand)" }} />
              </span>
              <span style={{ color: "var(--text)" }}>{b}</span>
            </li>
          ))}
        </ul>

        <p className="mt-4 text-[12px]" style={{ color: "var(--muted)" }}>
          A quick tour below shows you where everything lives. Takes about a minute.
        </p>

        <div className="mt-5 flex flex-col gap-2">
          <button type="button" onClick={startTour} className="btn btn-primary w-full">
            <Compass size={15} />
            Start tour
          </button>
          <button type="button" onClick={dismissWelcome} className="btn btn-ghost w-full">
            Skip for now
          </button>
        </div>
      </div>
    </div>
  );
}

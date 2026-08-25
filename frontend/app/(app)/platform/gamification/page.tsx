"use client";
import { Ban, ShieldCheck } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { ErrorNote, PageHeader, Section, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { PLATFORM_ROLES } from "@/lib/roles";
import { useData } from "@/lib/useData";

export default function GamificationPage() {
  return (
    <RequireAuth roles={PLATFORM_ROLES}>
      <Economy />
    </RequireAuth>
  );
}

/** The guardrails of GAM-21…25, stated as what does not exist.
 *
 *  They are listed here rather than buried in a policy document because each
 *  one is a build-time fact: there is no payment hook in the gamification
 *  service, no individual leaderboard query, no countdown field that is not
 *  the institution's real drive date. Nothing on this page can switch them on,
 *  because there is nothing to switch. */
const GUARDRAILS = [
  "Streak freezes and repairs are never purchasable — no payment hook exists in the gamification service.",
  "No loot boxes, no gacha, no in-app currency bought with money.",
  "No public individual leaderboards. Leagues are opt-in and pseudonymous; staff see mastery and participation, not vanity metrics.",
  "The only countdown is the institution's real drive date.",
  "Engagement notifications are capped and mutable in one tap — and the mute cannot be configured away.",
];

function Economy() {
  const { data, loading, error } = useData(() => api.platformGamification());

  if (loading) return <Skeleton rows={6} />;
  if (error) return <ErrorNote message={error} />;
  if (!data) return null;

  return (
    <>
      <PageHeader
        title="Game economy"
        sub="XP values, multipliers and streak rules — tunable per institution without a deployment. Every change is audit-logged."
      />

      <div className="grid md:grid-cols-2 gap-4 mb-4">
        <Section title="XP per activity">
          <dl className="space-y-1.5">
            {Object.entries(data.xp_table).map(([k, v]) => (
              <div key={k} className="flex items-center justify-between text-xs py-1 border-b border-border last:border-0">
                <dt className="text-muted">{k.replace(/_/g, " ")}</dt>
                <dd className="font-bold">{v} XP</dd>
              </div>
            ))}
          </dl>
        </Section>

        <Section title="Multipliers & caps">
          <dl className="space-y-1.5 text-xs">
            {Object.entries(data.difficulty_multipliers).map(([k, v]) => (
              <Row key={k} label={`Difficulty — ${k.replace(/_/g, " ")}`} value={`×${v}`} />
            ))}
            <Row label="Weakness multiplier" value={`×${data.weakness_multiplier}`}
                 note="training a diagnosed gap is worth more than repeating a strength" />
            <Row label="Quiz XP cap" value={`${data.quiz_xp_cap_percent}% of weekly XP`}
                 note="quizzes cannot substitute for speaking practice" />
            <Row label="Free streak freezes" value={`${data.free_freezes_per_month}/month`}
                 note="free and earned only — never for sale" />
            <Row label="Engagement notifications"
                 value={`${data.max_engagement_notifications_per_day}/day`}
                 note="quiet hours enforced; suppressed entirely in the 24h before a drive" />
            <Row label="Leagues" value={data.leagues_enabled ? "enabled" : "disabled"} />
          </dl>
        </Section>
      </div>

      <Section title="Structural guardrails">
        <div className="flex items-start gap-2 mb-3 text-xs text-muted">
          <ShieldCheck size={14} className="shrink-0 mt-0.5" style={{ color: "var(--rag-green)" }} />
          <span>
            These are not settings. They describe systems that were not built, which
            is why there is no control here to turn them off.
          </span>
        </div>
        <ul className="space-y-2">
          {GUARDRAILS.map((g) => (
            <li key={g} className="flex items-start gap-2 text-xs">
              <Ban size={13} className="shrink-0 mt-0.5" style={{ color: "var(--rag-red)" }} />
              <span className="leading-relaxed">{g}</span>
            </li>
          ))}
        </ul>
      </Section>
    </>
  );
}

function Row({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="py-1 border-b border-border last:border-0">
      <div className="flex items-center justify-between">
        <dt className="text-muted">{label}</dt>
        <dd className="font-bold">{value}</dd>
      </div>
      {note && <div className="text-[10px] text-muted mt-0.5">{note}</div>}
    </div>
  );
}

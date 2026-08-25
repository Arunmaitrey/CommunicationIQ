"use client";
import { Award, CalendarClock, Flame, Lock, Zap } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import {
  Badge, ErrorNote, GapMeter, LevelMeter, PageHeader, Section, Skeleton, Table,
} from "@/components/ui";
import { gameApi } from "@/lib/api";
import { skillLabel } from "@/lib/roles";
import { useData } from "@/lib/useData";

export default function SeasonPage() {
  return (
    <RequireAuth roles={["student"]}>
      <SeasonView />
    </RequireAuth>
  );
}

/** The season, the badges, and the XP arithmetic.
 *
 *  The ledger is on this page deliberately. An economy a student cannot
 *  inspect is one they have to take on trust, and the rows where a cap
 *  reduced an award are exactly the ones worth showing.
 */
function SeasonView() {
  const { data, loading, error } = useData(() => gameApi.state());
  const ledger = useData(() => gameApi.ledger());
  const badges = useData(() => gameApi.badges());

  if (loading) return <Skeleton rows={6} />;
  if (error) return <ErrorNote message={error} />;
  if (!data) return null;

  const season = data.season;
  const closed = data.gap_at_baseline != null && data.gap_percent != null
    ? Math.round(data.gap_percent - data.gap_at_baseline) : null;
  const earned = (badges.data ?? []).filter((b) => b.earned_at).length;

  return (
    <>
      <PageHeader
        title="Your season"
        sub={season.is_real_drive_date
          ? `${season.days_remaining} days to your placement drive. Everything here counts backwards from that date.`
          : "No drive date set for your cohort, so this is a rolling 90-day plan — not a deadline anyone chose."}
      />

      {!season.is_real_drive_date && (
        <div className="ds-card p-3 mb-4 text-xs text-muted flex items-start gap-2">
          <CalendarClock size={14} className="shrink-0 mt-0.5" />
          <span>
            The only countdown this app will ever show you is a real one. Until your
            institution sets the drive date, this is a default, and it says so.
          </span>
        </div>
      )}

      {/* The two bars again, and again kept apart. Effort rises; mastery is
          allowed to stall. Merging them would be the whole dishonesty. */}
      <div className="grid md:grid-cols-2 gap-4 mb-4">
        <Section title="Effort">
          <div className="flex items-baseline justify-between mb-1.5">
            <span className="text-xs font-semibold">Level {data.level}</span>
            <span className="text-[11px] text-muted">
              {data.xp_into_level}/{data.xp_per_level} XP
            </span>
          </div>
          <LevelMeter percent={(data.xp_into_level / data.xp_per_level) * 100} />
          <p className="text-[11px] text-muted mt-2 leading-relaxed">
            {data.total_xp.toLocaleString()} XP in total. This only ever goes up. It
            records what you did, not what you can do.
          </p>
        </Section>

        <Section title="Mastery">
          <div className="flex items-baseline justify-between mb-1.5">
            <span className="text-xs font-semibold">Gap meter</span>
            <span className="text-[11px] text-muted">
              {data.gap_percent != null ? `${data.gap_percent}%` : "not measured"}
            </span>
          </div>
          <GapMeter percent={data.gap_percent ?? 0} />
          <p className="text-[11px] text-muted mt-2 leading-relaxed">
            {closed != null && closed !== 0
              ? `${closed > 0 ? "+" : ""}${closed} points since your baseline.`
              : "Moves only when a diagnosed gap actually closes. It is allowed to stall."}
          </p>
        </Section>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
        <Stat icon={Flame} label="Streak" value={`${data.streak.current_streak}d`}
              sub={`best ${data.streak.best_streak}d`} tone="var(--rag-amber)" />
        <Stat icon={Lock} label="Freezes" value={data.streak.freezes_available}
              sub="free, never for sale" tone="var(--secondary)" />
        <Stat icon={Zap} label="Daily target" value={`${season.daily_minutes_target}m`}
              sub="planned from your drive date" />
        <Stat icon={Award} label="Badges" value={earned}
              sub={`of ${(badges.data ?? []).length}`} tone="var(--accent)" />
      </div>

      <Section title="Week by week" className="mb-4">
        {season.weeks.length === 0 ? (
          <div className="text-xs text-muted">
            Your plan is built once there is a diagnosis to plan around.
          </div>
        ) : (
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-2">
            {season.weeks.map((w) => (
              <div key={w.week} className="ds-inset p-3">
                <div className="text-[10px] font-bold uppercase tracking-wide text-muted">
                  Week {w.week}
                </div>
                <div className="text-xs font-semibold mt-1">{w.theme}</div>
                <div className="text-[11px] text-muted mt-1">
                  {skillLabel(w.target_skill)}
                </div>
              </div>
            ))}
          </div>
        )}
        {season.replans > 0 && (
          <p className="text-[11px] text-muted mt-3">
            Re-planned {season.replans} time(s) — your institution moved the drive date.
          </p>
        )}
      </Section>

      <Section title="Badges" className="mb-4">
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2">
          {(badges.data ?? []).map((b) => (
            <div key={b.code} className="ds-inset p-3"
                 style={b.earned_at ? undefined : { opacity: 0.5 }}>
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-semibold">{b.name}</span>
                <Badge tone={b.category === "courage" ? "var(--accent)"
                  : b.category === "mastery" ? "var(--rag-green)" : "var(--secondary)"}>
                  {b.category}
                </Badge>
              </div>
              <p className="text-[11px] text-muted mt-1 leading-relaxed">{b.description}</p>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Where your XP came from">
        <p className="text-[11px] text-muted mb-3 leading-relaxed">
          Every award, with the arithmetic. Training a diagnosed weakness is worth
          more than repeating something you already do well — that is the multiplier.
        </p>
        {(ledger.data ?? []).length === 0 ? (
          <div className="text-xs text-muted">Nothing earned yet.</div>
        ) : (
          <Table
            columns={["When", "For", "Base", "Difficulty", "Weakness", "Awarded", ""]}
            rows={(ledger.data ?? []).map((e) => [
              new Date(e.at).toLocaleDateString("en-IN", { day: "numeric", month: "short" }),
              <span key="a">
                {e.activity.replace(/_/g, " ")}
                {e.target_skill && (
                  <span className="text-muted"> · {skillLabel(e.target_skill)}</span>
                )}
              </span>,
              e.base_xp,
              `x${e.difficulty_multiplier}`,
              `x${e.weakness_multiplier}`,
              <span key="x" className="font-bold">{e.awarded_xp}</span>,
              e.cap_applied
                ? <Badge key="c" tone="var(--rag-amber)">capped</Badge>
                : "",
            ])}
          />
        )}
      </Section>
    </>
  );
}

function Stat({ icon: Icon, label, value, sub, tone = "var(--primary)" }: {
  icon: typeof Flame; label: string; value: string | number; sub: string; tone?: string;
}) {
  return (
    <div className="ds-card p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="text-[11px] font-semibold uppercase tracking-wide text-muted">
          {label}
        </div>
        <Icon size={14} style={{ color: tone }} />
      </div>
      <div className="text-2xl font-bold mt-2 leading-none" style={{ color: tone }}>
        {value}
      </div>
      <div className="text-[11px] text-muted mt-1.5">{sub}</div>
    </div>
  );
}

"use client";
import Link from "next/link";
import { Award, Flame, LineChart, TrendingUp } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import {
  ErrorNote, GapMeter, PageHeader, Section, Skeleton, StatCard,
} from "@/components/ui";
import { api, practiceApi, type Mastery, type StudentHome } from "@/lib/api";
import { skillLabel } from "@/lib/roles";
import { useData } from "@/lib/useData";

export default function MyProgressPage() {
  return (
    <RequireAuth roles={["student"]}>
      <MyProgress />
    </RequireAuth>
  );
}

/** Everything about how you are doing, in one place.
 *
 *  Replaces three destinations — Progress and Season — plus
 *  the halves of Today that were about the past rather than about what to do
 *  next.
 *
 *  It opens with one sentence in plain English. The numbers underneath are
 *  unchanged and still there for anyone who wants them, but a student who
 *  reads only the first line should come away with something true. A report
 *  whose top line is "49.1%" tells a person nothing about themselves.
 */
function MyProgress() {
  const home = useData(() => api.studentHome());
  const skills = useData(() => practiceApi.skills());

  if (home.loading) return <Skeleton rows={6} />;
  if (home.error) return <ErrorNote message={home.error} />;
  if (!home.data) return null;

  const d = home.data;
  const weakest = d.mastery?.[0];
  const strongest = d.mastery?.length
    ? [...d.mastery].sort((a, b) => b.mastery - a.mastery)[0]
    : undefined;

  return (
    <>
      <PageHeader title="My progress" sub="Where you are, and what is moving." />

      {/* The plain-language line. Written as a sentence about the person, not
          a restatement of the metric above it. */}
      <div className="ds-card p-4 mb-4">
        <p className="text-sm leading-relaxed">{summarise(d, weakest, strongest)}</p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
        <StatCard icon={Flame} label="Practice streak" tone="var(--rag-amber)"
                  value={`${d.streak.current_streak}d`}
                  sub={`best ${d.streak.best_streak}d`} />
        <StatCard icon={TrendingUp} label="Skill" tone="var(--rag-green)"
                  value={d.gap_percent != null ? `${d.gap_percent}%` : "—"}
                  sub="how much you have actually improved" />
        <StatCard icon={Award} label="Effort" value={`Level ${d.level}`}
                  sub={`${d.total_xp.toLocaleString()} XP`} />
        <StatCard icon={LineChart} label="Drive in" tone="var(--secondary)"
                  value={d.days_to_drive != null ? `${d.days_to_drive}d` : "—"}
                  sub="your cohort's date" />
      </div>

      {/* Kept from the old Progress screen, because the distinction is real
          and worth teaching: one bar is work done, the other is skill gained. */}
      <Section title="Effort and skill are not the same thing" className="mb-4">
        <p className="text-xs text-muted leading-relaxed">
          <strong>Effort</strong> goes up whenever you practise. <strong>Skill</strong>{" "}
          only moves when something you were weak at actually gets better. A
          week where effort climbs and skill does not means the practice needs
          changing, not repeating.
        </p>
        {d.mastery?.length > 0 && (
          <div className="space-y-2.5 mt-4">
            {d.mastery.map((m) => (
              <div key={m.skill}>
                <div className="flex items-baseline justify-between mb-1">
                  <span className="text-xs font-medium">{skillLabel(m.skill)}</span>
                  <span className="text-[11px] text-muted">
                    {Math.round(m.mastery * 100)}%
                  </span>
                </div>
                <GapMeter percent={m.mastery * 100} />
              </div>
            ))}
          </div>
        )}
      </Section>

      <div className="grid md:grid-cols-2 gap-3 mb-4">
        <Link href="/season"
              className="ds-card p-4 hover:bg-surface2 transition-colors ds-focus block">
          <div className="text-sm font-bold">Your plan to the drive</div>
          <p className="text-[11px] text-muted mt-1 leading-relaxed">
            What to work on each week between now and your placement date.
          </p>
          <div className="text-[11px] mt-2" style={{ color: "var(--primary)" }}>
            {d.days_to_drive != null ? `${d.days_to_drive} days left →` : "Open →"}
          </div>
        </Link>
      </div>

      {/* Finished tests only, and in plain words.
          This listed every row including "created" and "in_progress" — our
          lifecycle states, shown to a student as though they meant something.
          A test you opened and abandoned is not a result, and putting eight of
          them above your real scores buries the thing you came to see. */}
      <Section title="Your tests">
        {d.recent_attempts.length === 0 ? (
          <p className="text-xs text-muted">
            You have not taken one yet.{" "}
            <Link href="/tests" className="underline ds-focus">Take your first test</Link>.
          </p>
        ) : (
          <div className="space-y-2">
            {d.recent_attempts.filter((a) => a.status === "scored").map((a) => (
              <Link key={a.id} href={`/results/${a.id}`}
                    className="flex items-center gap-3 text-xs py-1.5 border-b border-border last:border-0 hover:bg-surface2 ds-focus">
                <span className="flex-1 font-medium">{a.profile_name}</span>
                <span className="font-bold w-12 text-right">
                  {a.overall_score != null ? a.overall_score : "not scored"}
                </span>
              </Link>
            ))}
            {d.recent_attempts.every((a) => a.status !== "scored") && (
              <p className="text-xs text-muted">
                Nothing finished yet. A test only appears here once it has been
                scored.
              </p>
            )}
          </div>
        )}
      </Section>
    </>
  );
}

/** One true sentence about this student.
 *
 *  Ordered so the most useful thing comes first: whether they have been
 *  measured at all, then what is weakest, then whether the effort is landing.
 */
function summarise(d: StudentHome, weakest: Mastery | undefined,
                   strongest: Mastery | undefined): string {
  if (!d.baseline_done) {
    return "You have not taken your first test yet, so there is nothing measured "
      + "to report. It takes about eight minutes and everything else is compared "
      + "against it.";
  }

  const parts: string[] = [];

  if (weakest && strongest && weakest.skill !== strongest.skill) {
    parts.push(
      `Your strongest area is ${skillLabel(strongest.skill).toLowerCase()} and `
      + `your weakest is ${skillLabel(weakest.skill).toLowerCase()}, so that is `
      + `where practice will pay off most.`);
  } else if (weakest) {
    parts.push(
      `Your weakest area is ${skillLabel(weakest.skill).toLowerCase()}, so that `
      + `is where practice will pay off most.`);
  }

  if (d.streak.current_streak >= 3) {
    parts.push(`You have practised ${d.streak.current_streak} days in a row.`);
  } else if (d.streak.current_streak === 0) {
    parts.push("You have not practised yet today.");
  }

  if (d.days_to_drive != null && d.days_to_drive <= 30) {
    parts.push(`Your placement drive is ${d.days_to_drive} days away.`);
  }

  return parts.join(" ") || "Keep practising — there is not enough measured yet to say much.";
}

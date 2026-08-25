"use client";
import Link from "next/link";
import { ArrowRight, Play, TrendingUp } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { ErrorNote, PageHeader, Section, Skeleton, StatCard } from "@/components/ui";
import { StreakChip, Workflow, type Step } from "@/components/Workflow";
import { api, type StudentHome } from "@/lib/api";
import { useData } from "@/lib/useData";

export default function StudentHomePage() {
  return (
    <RequireAuth roles={["student"]}>
      <Home />
    </RequireAuth>
  );
}

/** What to do right now, in one box with one button.
 *
 *  Ordered by what actually blocks the student: consent first, because
 *  nothing records without it; then the first test, because everything else
 *  is measured against it; then today's goal.
 */
function NextAction({ quest, baselineDone, consent, hasAttempts }: {
  quest: StudentHome["quest"]; baselineDone: boolean; consent: boolean;
  hasAttempts: boolean;
}) {
  let title: string;
  let why: string;
  let href: string;
  let cta: string;

  if (!consent) {
    title = "First, a quick permission";
    why = "Nothing is recorded until you have read what we keep and agreed to it. Two minutes.";
    href = "/consent";
    cta = "Read and choose";
  } else if (!baselineDone) {
    // Two different people reach this branch. Someone brand new, and someone
    // who has taken practice tests but never the short starting one -- and
    // telling that second person to "take your first test" while their last
    // test sits on the same screen is exactly the kind of thing that makes
    // software feel like it is not paying attention.
    title = hasAttempts ? "Set your starting point" : "Take your first test";
    why = hasAttempts
      ? "You have practised, but not yet done the short test that sets your baseline. "
        + "About eight minutes, and it is what everything else gets measured against."
      : "About eight minutes. It sets the starting point everything else is measured against.";
    href = "/tests";
    cta = "Start";
  } else if (quest && !quest.completed) {
    title = quest.title;
    why = `${quest.description} Finishing it counts today towards your streak.`;
    href = "/practise";
    cta = "Start";
  } else {
    title = "You are done for today";
    why = "Today counts towards your streak. Come back tomorrow, or keep going if you have ten minutes.";
    href = "/practise";
    cta = "Keep practising";
  }

  return (
    <div className="ds-card p-5 mb-4" style={{ borderColor: "var(--primary)" }}>
      <div className="flex items-center gap-4 flex-wrap">
        <span className="rounded-full p-3 shrink-0"
              style={{ background: "color-mix(in srgb, var(--primary) 14%, transparent)" }}>
          <Play size={20} style={{ color: "var(--primary)" }} />
        </span>
        <div className="flex-1 min-w-[16rem]">
          <div className="text-[11px] font-bold uppercase tracking-wider"
               style={{ color: "var(--primary)" }}>
            Do this next
          </div>
          <div className="text-base font-bold mt-0.5">{title}</div>
          <p className="text-xs text-muted mt-1 leading-relaxed">{why}</p>
        </div>
        <Link href={href} className="btn btn-primary ds-focus shrink-0">{cta}</Link>
      </div>
    </div>
  );
}

/** The home screen. Deliberately short.
 *
 *  It used to open with four stat cards, two explained meters, a quest card,
 *  the full list of every published test and a recent-attempts table — nine
 *  blocks before a student found out what to do. Most of it was reference
 *  material that belongs on a page someone chooses to visit.
 *
 *  What is left: one action, two numbers that change behaviour, and two doors.
 *  Everything removed still exists at /practise, /tests and /my-progress.
 */
function Home() {
  const { data, loading, error } = useData(() => api.studentHome());

  if (loading) return <Skeleton rows={4} />;
  if (error) return <ErrorNote message={error} />;
  if (!data) return null;

  // "Today" is whatever the server says today is, taken from the quest it
  // just generated. Deriving it on the client would put a device in one
  // timezone against a server in another, and the streak would claim the day
  // was counted when it was not.
  const serverToday = data.quest?.for_date ?? null;
  const countedToday =
    serverToday != null && data.streak.last_qualifying_day === serverToday;

  return (
    <>
      <PageHeader
        title={`Hello, ${data.user.full_name.split(" ")[0]}`}
        sub={data.days_to_drive != null
          ? `${data.days_to_drive} days until your placement drive.`
          : "No drive date set for your cohort yet."}
      />

      {/* The streak, at the top, as a chip. It had half a stat row, which is
          more room than a number that moves once a day has earned. */}
      <div className="mb-3">
        <StreakChip days={data.streak.current_streak} countedToday={countedToday} />
      </div>

      <NextAction quest={data.quest} baselineDone={data.baseline_done}
                  consent={data.consent_given}
                  hasAttempts={data.recent_attempts.length > 0} />

      <Workflow title="How this works" steps={studentSteps(data, countedToday)} />

      {/* One number, and it changes what a student does today. Level and XP
          moved to My progress: they are a record of the past, and nobody acts
          differently because of them. */}
      <div className="mb-4">
        <StatCard icon={TrendingUp} label="Skill" tone="var(--rag-green)"
                  value={data.gap_percent != null ? `${data.gap_percent}%` : "—"}
                  sub={data.gap_percent != null
                    ? "how much you have improved"
                    : "take your first test"} />
      </div>

      <div className="grid sm:grid-cols-2 gap-3">
        <Doorway href="/practise" title="Practise"
                 detail="Speaking, listening, reading and writing. Short sessions." />
        <Doorway href="/tests" title="Take a test"
                 detail="Timed practice tests and company rounds." />
      </div>

      {data.recent_attempts.some((a) => a.status === "scored") && (
        <Section title="Your last test" className="mt-4">
          {data.recent_attempts.filter((a) => a.status === "scored").slice(0, 1).map((a) => (
            <Link key={a.id} href={`/results/${a.id}`}
                  className="flex items-center gap-3 text-xs hover:bg-surface2 ds-focus py-1">
              <span className="flex-1 font-medium">{a.profile_name}</span>
              <span className="font-bold">
                {a.overall_score != null ? a.overall_score : "not scored"}
              </span>
              <ArrowRight size={13} className="text-muted" />
            </Link>
          ))}
          <Link href="/my-progress"
                className="text-[11px] underline text-muted ds-focus mt-2 inline-block">
            See everything
          </Link>
        </Section>
      )}
    </>
  );
}

/** The five things a student does, in order, and where they have got to.
 *
 *  Each `done` comes from data the home endpoint already returns. Nothing
 *  here is a guess: "sat a full assessment" means a scored attempt exists
 *  that is not the baseline, not that they visited the page.
 */
function studentSteps(data: StudentHome, countedToday: boolean): Step[] {
  const scored = data.recent_attempts.filter((a) => a.status === "scored");
  return [
    {
      title: "Agree to being recorded",
      detail: "Nothing is recorded until you have read what we keep and said yes.",
      href: "/consent",
      done: data.consent_given,
    },
    {
      title: "Take the short starting test",
      detail: "About eight minutes. Everything later is measured against it.",
      href: "/tests",
      done: data.baseline_done,
    },
    {
      title: "Read your report",
      detail: "What was measured, what it means, and the one thing to fix first.",
      href: "/my-progress",
      done: scored.length > 0,
    },
    {
      title: "Practise a little, most days",
      detail: "Short sessions on your weakest skill. This is where the score moves.",
      href: "/practise",
      done: countedToday,
    },
    {
      title: "Sit a full assessment",
      detail: "A company round or a full simulation, under a real clock.",
      href: "/tests",
      done: scored.some((a) => !a.is_baseline),
    },
  ];
}

function Doorway({ href, title, detail }: {
  href: string; title: string; detail: string;
}) {
  return (
    <Link href={href}
          className="ds-card p-4 hover:bg-surface2 transition-colors ds-focus block">
      <div className="flex items-center gap-2">
        <span className="text-sm font-bold">{title}</span>
        <ArrowRight size={14} className="text-muted ml-auto" />
      </div>
      <p className="text-[11px] text-muted mt-1 leading-relaxed">{detail}</p>
    </Link>
  );
}

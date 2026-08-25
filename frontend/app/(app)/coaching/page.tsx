"use client";
import { Activity, Flag, Users } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { ErrorNote, PageHeader, Skeleton, StatCard } from "@/components/ui";
import { Workflow, type Step } from "@/components/Workflow";
import { api, trainerApi } from "@/lib/api";
import { useData } from "@/lib/useData";

export default function CoachingHomePage() {
  return (
    <RequireAuth roles={["trainer"]}>
      <Coaching />
    </RequireAuth>
  );
}

/**
 *  A trainer's landing page.
 *
 *  There was not one. Signing in as a trainer dropped you on the cohort list,
 *  which is a table — it says how many students are in each group and nothing
 *  about what a coach is supposed to do with them, or in what order. The three
 *  screens that follow existed and were reachable only if you already knew
 *  they were the answer.
 */
function Coaching() {
  const cohorts = useData(() => api.trainerCohorts());
  const momentum = useData(() => trainerApi.momentum());
  const flags = useData(() => trainerApi.flags(false));

  const loading = cohorts.loading || momentum.loading || flags.loading;
  const error = cohorts.error || momentum.error || flags.error;

  if (loading) return <Skeleton rows={5} />;
  if (error) return <ErrorNote message={error} />;

  const rows = momentum.data ?? [];
  const open = flags.data ?? [];
  const students = rows.length;
  // Somebody the system thinks is drifting and nobody has looked at yet. This
  // is the number a coach's day is actually made of.
  const needsLooking = rows.filter((r) => r.suggest_flag && !r.flagged).length;

  return (
    <>
      <PageHeader
        title="Coaching"
        sub="Your cohorts, who is drifting, and who you have already picked up."
      />

      <div className="grid grid-cols-3 gap-3 mb-4">
        <StatCard icon={Users} label="Students" value={students}
                  sub={`${(cohorts.data ?? []).length} cohorts`} />
        <StatCard icon={Activity} label="Suggested" value={needsLooking}
                  tone={needsLooking > 0 ? "var(--rag-amber)" : "var(--rag-green)"}
                  sub="drifting, not yet flagged" />
        <StatCard icon={Flag} label="Open flags" value={open.length}
                  tone={open.length > 0 ? "var(--rag-amber)" : "var(--rag-green)"}
                  sub="picked up, not resolved" />
      </div>

      <Workflow title="Your week, in order" steps={coachingSteps(needsLooking, open.length)} />
    </>
  );
}

/** Four steps, and only two of them can ever be finished.
 *
 *  Watching momentum has no end state, so it is marked ongoing rather than
 *  given a tick it would never earn. Reviewing your cohorts likewise.
 */
function coachingSteps(needsLooking: number, openFlags: number): Step[] {
  return [
    {
      title: "Know your cohorts",
      detail: "Who is in each group, and how far off their placement drive is.",
      href: "/cohorts",
    },
    {
      title: "Check momentum weekly",
      detail: "Who has stopped practising, who has slowed, and who is fine.",
      href: "/momentum",
    },
    {
      title: "Flag the ones who are drifting",
      detail: needsLooking > 0
        ? `${needsLooking} student${needsLooking === 1 ? "" : "s"} the system suggests you look at.`
        : "Nobody is currently suggested. The suggestion is a prompt, not a verdict.",
      href: "/momentum",
      done: needsLooking === 0,
    },
    {
      title: "Work the open flags",
      detail: openFlags > 0
        ? `${openFlags} still open. Resolve one when you have actually spoken to them.`
        : "None open. A flag is closed by a conversation, not by the clock.",
      href: "/flags",
      done: openFlags === 0,
    },
  ];
}

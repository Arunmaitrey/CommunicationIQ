"use client";
import Link from "next/link";
import { ArrowRight, Check, Flame } from "lucide-react";

/**
 *  The steps a role works through, and which one they are on.
 *
 *  Every console had numbers on it and no shape: a admin landed on a list of
 *  cohorts, an institution admin on four counters, and neither screen said
 *  what to do first or what came after it. The counters answer "how much";
 *  nobody had answered "in what order".
 *
 *  **Driven by real state, never a static picture.** Each step carries a
 *  `done` flag computed from data the console already loads, so the list says
 *  where this account actually is. A fixed diagram of five steps would look
 *  identical on day one and day ninety, which is the failure this whole
 *  codebase keeps naming: something that looks live and is not.
 *
 *  A step with `done: undefined` is one whose completion we cannot honestly
 *  determine — ongoing work like "watch momentum" has no finish line. It
 *  renders as a plain step rather than being guessed either way.
 *
 *  **Why the rail is segmented rather than one line.** These steps are a
 *  route, not a queue: somebody can practise before reading their report, and
 *  the screenshot that prompted this rewrite showed exactly that — step four
 *  ticked while step three was still current. A single bar filled to a
 *  percentage would have called that impossible. Each segment is coloured from
 *  the step above it instead, so an out-of-order tick reads as what it is.
 */
export interface Step {
  /** Imperative and short. What the person does, not what the screen is. */
  title: string;
  /** Why it comes here. One line, in their words. */
  detail: string;
  href: string;
  /** true = finished, false = not yet, undefined = ongoing, no finish line. */
  done?: boolean;
}

const MARKER = 26;
const RAIL_X = MARKER / 2;

export function Workflow({ title, steps }: { title: string; steps: Step[] }) {
  // The first unfinished step is the one to point at. Steps with no finish
  // line are never "current" — telling somebody their next action is a thing
  // they can never complete is not guidance.
  const current = steps.findIndex((s) => s.done === false);
  const finished = steps.filter((s) => s.done === true).length;
  const finishable = steps.filter((s) => s.done !== undefined).length;

  return (
    <section className="ds-card p-4 mb-4">
      <header className="flex items-baseline justify-between gap-3 mb-3">
        <h2 className="text-[11px] font-bold uppercase tracking-wider text-muted">
          {title}
        </h2>
        {finishable > 0 && (
          <span className="text-[11px] text-muted tabular-nums shrink-0">
            <span className="font-bold" style={{ color: "var(--rag-green)" }}>
              {finished}
            </span>
            {` of ${finishable} done`}
          </span>
        )}
      </header>

      <ol className="relative">
        {steps.map((step, n) => {
          const isCurrent = n === current;
          const isDone = step.done === true;
          const isOngoing = step.done === undefined;
          const prevDone = n > 0 && steps[n - 1].done === true;

          return (
            <li key={step.href + step.title} className="relative">
              {/* The segment above this marker, coloured by the step it comes
                  from. Sits behind the marker, which is opaque. */}
              {n > 0 && (
                <span
                  aria-hidden
                  className="absolute w-px"
                  style={{
                    left: RAIL_X, top: 0, height: 18,
                    background: prevDone
                      ? "color-mix(in srgb, var(--rag-green) 45%, transparent)"
                      : "var(--border)",
                  }}
                />
              )}

              <Link
                href={step.href}
                aria-current={isCurrent ? "step" : undefined}
                className="group relative flex items-start gap-3 rounded-lg px-2.5 py-2.5 ds-focus transition-colors hover:bg-surface2"
                style={isCurrent ? {
                  background: "color-mix(in srgb, var(--primary) 7%, transparent)",
                } : undefined}
              >
                <span
                  className="relative shrink-0 grid place-items-center rounded-full text-[11px] font-bold tabular-nums"
                  style={{
                    width: MARKER, height: MARKER,
                    background: isDone
                      ? "color-mix(in srgb, var(--rag-green) 16%, transparent)"
                      : isCurrent
                        ? "var(--primary)"
                        : "var(--surface-2)",
                    color: isDone
                      ? "var(--rag-green)"
                      : isCurrent
                        ? "var(--on-primary, #fff)"
                        : "var(--muted)",
                    // A ring rather than a border, so the marker keeps its
                    // size and the rail meets it cleanly.
                    boxShadow: isDone
                      ? "0 0 0 1px color-mix(in srgb, var(--rag-green) 35%, transparent)"
                      : isCurrent
                        ? "0 0 0 3px color-mix(in srgb, var(--primary) 18%, transparent)"
                        : "inset 0 0 0 1px var(--border)",
                  }}
                >
                  {isDone ? <Check size={13} strokeWidth={3} />
                    : isOngoing ? <span className="block rounded-full"
                                        style={{ width: 5, height: 5,
                                                 background: "var(--muted)" }} />
                    : n + 1}
                </span>

                <span className="flex-1 min-w-0 pt-0.5">
                  <span className="flex items-center gap-2 flex-wrap">
                    <span
                      className={`text-sm leading-snug ${isCurrent ? "font-bold" : "font-medium"}`}
                      style={isDone ? { color: "var(--muted)" } : undefined}
                    >
                      {step.title}
                    </span>
                    {isCurrent && (
                      <span
                        className="text-[9.5px] font-bold uppercase tracking-wider rounded-full px-1.5 py-0.5 leading-none"
                        style={{
                          background: "color-mix(in srgb, var(--primary) 14%, transparent)",
                          color: "var(--primary)",
                        }}
                      >
                        you are here
                      </span>
                    )}
                    {isOngoing && (
                      // Said plainly rather than left as an unticked box that
                      // looks like something they forgot to do.
                      <span className="text-[9.5px] uppercase tracking-wider text-muted">
                        ongoing
                      </span>
                    )}
                  </span>
                  <span className="block text-[11px] text-muted leading-relaxed mt-1">
                    {step.detail}
                  </span>
                </span>

                <ArrowRight
                  size={14}
                  className="shrink-0 mt-1 transition-transform group-hover:translate-x-0.5 motion-reduce:transform-none"
                  style={{
                    color: isCurrent ? "var(--primary)" : "var(--muted)",
                    opacity: isCurrent ? 1 : 0.55,
                  }}
                />
              </Link>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

/**
 *  The streak, as a chip rather than a card.
 *
 *  It had half a row of the student's home screen, which is more room than a
 *  number that changes once a day has earned. It matters — it is the one
 *  thing that rewards coming back — but it is a status, not a headline, and a
 *  full card next to it implied the two were equally worth reading.
 */
export function StreakChip({ days, countedToday }: {
  days: number; countedToday: boolean;
}) {
  const tone = countedToday ? "var(--rag-green)" : "var(--rag-amber)";
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-bold"
      style={{
        background: `color-mix(in srgb, ${tone} 14%, transparent)`,
        color: tone,
      }}
      title={countedToday
        ? "Today is counted towards your streak."
        : "Today is not counted yet. Finish one practice session."}
    >
      <Flame size={13} aria-hidden />
      {days}-day streak
      <span className="font-medium opacity-80">
        {countedToday ? "· today counted" : "· not today"}
      </span>
    </span>
  );
}

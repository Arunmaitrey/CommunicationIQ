"use client";
import { Check } from "lucide-react";

/** A numbered "what happens next" strip.
 *
 *  Screens that start something (a test, a practice session) kept assuming
 *  the student already knew the shape of the flow — pick, start, mic check,
 *  do it, read the report. Anyone who did not know found out by being
 *  redirected somewhere unfamiliar. This states the steps up front, once,
 *  in one visual language shared by every screen that starts anything.
 *
 *  `active` highlights where the student is right now (1-based). Steps
 *  before it render as done. Pass 1 on browse screens — the first step is
 *  the one they are doing by looking at the page.
 */
export function StepGuide({ steps, active = 1, title = "How this works" }: {
  steps: { label: string; detail?: string }[];
  active?: number;
  title?: string;
}) {
  return (
    <div className="ds-card p-3 mb-4">
      <div className="text-[10px] font-bold uppercase tracking-wider text-muted mb-2">
        {title}
      </div>
      <ol className="flex flex-col sm:flex-row sm:flex-wrap gap-x-6 gap-y-2">
        {steps.map((s, i) => {
          const n = i + 1;
          const done = n < active;
          const now = n === active;
          return (
            <li key={s.label} className="flex items-start gap-2 min-w-0 sm:max-w-[15rem]">
              <span
                className="w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold shrink-0 mt-px"
                style={done || now ? {
                  background: now
                    ? "var(--primary)"
                    : "color-mix(in srgb, var(--primary) 18%, transparent)",
                  color: now ? "var(--on-primary, #fff)" : "var(--primary)",
                } : {
                  background: "var(--surface2)",
                  color: "var(--muted)",
                }}
              >
                {done ? <Check size={11} /> : n}
              </span>
              <span className="min-w-0">
                <span className="text-xs font-semibold block"
                      style={{ color: now ? "var(--fg)" : undefined }}>
                  {s.label}
                  {now && (
                    <span className="ml-1.5 text-[9px] font-bold uppercase tracking-wider"
                          style={{ color: "var(--primary)" }}>
                      you are here
                    </span>
                  )}
                </span>
                {s.detail && (
                  <span className="text-[10px] text-muted leading-relaxed block mt-0.5">
                    {s.detail}
                  </span>
                )}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

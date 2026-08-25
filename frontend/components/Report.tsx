"use client";
import { useState } from "react";
import { ChevronDown, Download, Loader2, Sparkles, ThumbsUp, TrendingUp } from "lucide-react";
import { Section } from "@/components/ui";
import { DIMENSION_LABEL } from "@/lib/dimensions";
import type { AttemptResult, EvidenceRow, Highlight, Narration, SectionResult,
              SkillScore } from "@/lib/api";

/**
 *  The parts of a result that are not a number.
 *
 *  What was here before: a score, a set of bars, and one "biggest lever"
 *  naming the single worst thing about how somebody speaks. Every time.
 *  Nothing about what they were good at, one instruction rather than a plan,
 *  and no way to see what any of it was counted from — so a student who
 *  disagreed with a score had nothing to disagree *with*.
 */

/** The plain sentence, before any chart. The Phase 0 rule. */
export function Summary({ text }: { text: string }) {
  if (!text) return null;
  return (
    <div className="ds-card p-4 mb-4" style={{ borderColor: "var(--primary)" }}>
      <p className="text-sm leading-relaxed">{text}</p>
    </div>
  );
}


/** "What your assessment says" — the AI explanation of the frozen result.
 *
 *  It never stands in for the deterministic report, which renders in full
 *  below it. Three honest states:
 *    ready       — the AI explanation, tagged as AI-generated and uncalibrated
 *    in-flight   — a "being prepared" note; the page keeps polling
 *    failed/none — a plain "couldn't generate" note, or nothing at all
 *
 *  It is never given the deterministic summary to display as if the model
 *  wrote it: when there is no AI text, it says so, and the real summary is
 *  the separate <Summary> card underneath.
 */
export function NarrationCard({ narration }: { narration: Narration | null }) {
  if (!narration) return null;

  const inFlight = narration.status === "pending"
    || narration.status === "processing"
    || narration.status === "retry_pending";

  return (
    <div className="ds-card p-4 mb-4" style={{ borderColor: "var(--primary)" }}>
      <div className="flex items-center gap-2 mb-2">
        <Sparkles size={15} style={{ color: "var(--primary)" }} />
        <span className="text-[11px] font-bold uppercase tracking-wider"
              style={{ color: "var(--primary)" }}>
          What your assessment says
        </span>
        {narration.status === "ready" && (
          <span className="text-[10px] text-muted ml-auto">
            AI-generated · not yet calibrated
          </span>
        )}
      </div>

      {inFlight && (
        <div className="flex items-center gap-2">
          <Loader2 size={15} className="animate-spin text-muted" />
          <p className="text-sm text-muted leading-relaxed">
            We&apos;re preparing your personalised explanation of these results.
            Your full results are below.
          </p>
        </div>
      )}

      {narration.status === "failed" && (
        <p className="text-sm text-muted leading-relaxed">
          We couldn&apos;t generate the personalised explanation right now. Your
          assessment results are still available below.
        </p>
      )}

      {narration.status === "ready" && (
        <>
          <p className="text-base font-bold mb-1">{narration.headline}</p>
          <p className="text-sm leading-relaxed mb-3">{narration.summary}</p>
          <div className="grid sm:grid-cols-2 gap-3">
            <div className="ds-inset p-3">
              <div className="text-[10px] font-bold uppercase tracking-wider text-muted mb-1">
                Focus on
              </div>
              <p className="text-xs leading-relaxed">{narration.primary_focus}</p>
            </div>
            <div className="ds-inset p-3">
              <div className="text-[10px] font-bold uppercase tracking-wider text-muted mb-1">
                Try this
              </div>
              <p className="text-xs leading-relaxed">{narration.practice_action}</p>
            </div>
          </div>
          {narration.caveats.length > 0 && (
            <ul className="mt-3 space-y-0.5">
              {narration.caveats.map((c) => (
                <li key={c} className="text-[11px] text-muted leading-relaxed">· {c}</li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}

const LABEL = DIMENSION_LABEL;

const name = (d: string) => LABEL[d] ?? d;

/**
 *  What went well, beside what did not.
 *
 *  Both are measured against the student's own average rather than a cohort —
 *  this product has no population norms, and "ahead of your own average" needs
 *  none while "good" would be a claim about people nobody has measured.
 */
export function Highlights({ strengths, weaknesses }: {
  strengths: Highlight[]; weaknesses: Highlight[];
}) {
  if (!strengths.length && !weaknesses.length) return null;

  return (
    <div className="grid sm:grid-cols-2 gap-3 mb-4">
      <HighlightList title="Ahead of your own average" tone="var(--rag-green)"
                     icon={<ThumbsUp size={14} />} rows={strengths}
                     empty="Nothing stands out above the rest this time." />
      <HighlightList title="Behind your own average" tone="var(--rag-amber)"
                     icon={<TrendingUp size={14} />} rows={weaknesses}
                     empty="Nothing is lagging behind the rest." />
    </div>
  );
}

function HighlightList({ title, tone, icon, rows, empty }: {
  title: string; tone: string; icon: React.ReactNode;
  rows: Highlight[]; empty: string;
}) {
  return (
    <div className="ds-card p-4">
      <div className="flex items-center gap-2 mb-2" style={{ color: tone }}>
        {icon}
        <span className="text-[11px] font-bold uppercase tracking-wider">{title}</span>
      </div>
      {rows.length === 0 ? (
        <p className="text-[11px] text-muted leading-relaxed">{empty}</p>
      ) : (
        <ul className="space-y-1.5">
          {rows.map((row) => (
            <li key={row.dimension} className="flex items-baseline gap-2">
              <span className="text-sm font-medium flex-1">{name(row.dimension)}</span>
              <span className="text-sm font-bold tabular-nums">{row.score}</span>
              <span className="text-[11px] tabular-nums" style={{ color: tone }}>
                {row.delta > 0 ? "+" : ""}{row.delta}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 *  The plan. Ordered by what each change would actually be worth.
 *
 *  The gains are computed from the student's own scores — what the overall
 *  *would be* if this measure matched their own best — not chosen because
 *  they read well. Saying so matters: a number a student cannot check is a
 *  number they are asked to take on faith.
 */
/**
 *  What to work on, in the one order the product stands behind.
 *
 *  Rendered from the result's primary diagnosis and its priorities -- the
 *  same objects the student's result card, the practice buttons and the AI
 *  narration consume -- so a trainer or employer reading this view sees the
 *  same first answer the student saw. It used to rank by the composite's
 *  weighted gain, which on a level result named a different area from the
 *  summary sentence above it.
 */
export function Plan({ result }: { result: AttemptResult }) {
  const primary = result.primary_diagnosis;
  const rows = result.priorities ?? [];
  if (!rows.length) {
    return (
      <Section title="What to work on" className="mb-4">
        <p className="text-xs text-muted leading-relaxed">
          {primary?.reason
            ?? "Nothing was measured on enough answers to point at one area yet."}
        </p>
      </Section>
    );
  }

  const identified = primary?.status === "identified";
  return (
    <Section title={identified ? "What to work on, in order" : "What to work on"}
             className="mb-4">
      {primary && !identified && (
        <p className="text-xs text-muted leading-relaxed mb-3">
          <span className="font-bold text-text">{primary.headline}.</span> {primary.reason}
        </p>
      )}
      <ol className="space-y-3">
        {rows.map((rec, n) => (
          <li key={rec.dimension} className="flex items-start gap-3">
            <span className="shrink-0 grid place-items-center rounded-full text-[11px] font-bold mt-0.5"
                  style={{ width: 22, height: 22, background: "var(--surface2)" }}>
              {n + 1}
            </span>
            <div className="flex-1 min-w-0">
              <div className="flex items-baseline gap-2 flex-wrap">
                <span className="text-sm font-bold">{name(rec.dimension)}</span>
                {rec.verdict === "needs_most" && (
                  <span className="text-[11px] font-bold" style={{ color: "var(--rag-amber)" }}>
                    first
                  </span>
                )}
                <span className="text-[11px] text-muted">{rec.evidence}</span>
              </div>
              {rec.advice && (
                <p className="text-xs text-muted mt-1 leading-relaxed">{rec.advice}</p>
              )}
            </div>
          </li>
        ))}
      </ol>
    </Section>
  );
}

/**
 *  What each number was counted from.
 *
 *  All of it has been stored since the engine first ran and none of it was
 *  ever shown next to the score it produced. "Your grammar was 44" is an
 *  assertion; "your grammar was 44, and here are the sentences it was counted
 *  from" is something a student can argue with — and a student who can argue
 *  with a score is being treated as a person rather than a subject.
 *
 *  Collapsed by default. Most people want the number; the ones who want the
 *  working want all of it.
 */
export function Evidence({ evidence }: { evidence: Record<string, EvidenceRow[]> }) {
  const dimensions = Object.keys(evidence).sort();
  const [open, setOpen] = useState<string | null>(null);

  if (!dimensions.length) return null;

  return (
    <Section title="What these numbers were counted from" className="mb-4">
      <div className="space-y-1">
        {dimensions.map((dimension) => {
          const rows = evidence[dimension];
          const isOpen = open === dimension;
          return (
            <div key={dimension}>
              <button
                onClick={() => setOpen(isOpen ? null : dimension)}
                className="w-full flex items-center gap-2 py-1.5 text-left ds-focus"
                aria-expanded={isOpen}
              >
                <ChevronDown size={13} className="text-muted shrink-0"
                             style={{ transform: isOpen ? undefined : "rotate(-90deg)" }} />
                <span className="text-xs font-medium flex-1">{name(dimension)}</span>
                <span className="text-[11px] text-muted">
                  {rows.length} {rows.length === 1 ? "answer" : "answers"}
                </span>
              </button>
              {isOpen && (
                <ul className="pl-6 pb-2 space-y-2">
                  {rows.map((row) => <EvidenceItem key={row.response_id} row={row} />)}
                </ul>
              )}
            </div>
          );
        })}
      </div>
    </Section>
  );
}

function EvidenceItem({ row }: { row: EvidenceRow }) {
  const facts: string[] = [];
  if (row.words_per_minute != null) facts.push(`${Math.round(row.words_per_minute)} words a minute`);
  if (row.onset_ms != null) facts.push(`started after ${(row.onset_ms / 1000).toFixed(1)}s`);
  if (row.pauses?.length) facts.push(`${row.pauses.length} pauses`);
  if (row.disfluencies?.length) facts.push(`${row.disfluencies.length} fillers`);
  if (row.grammar_errors?.length) facts.push(`${row.grammar_errors.length} error patterns`);
  if (row.word_errors?.length) facts.push(`${row.word_errors.length} unclear words`);

  return (
    <li className="text-[11px] leading-relaxed">
      <div className="flex items-baseline gap-2">
        <span className="text-muted">Item {row.position}</span>
        <span className="font-bold tabular-nums">{row.score}</span>
      </div>
      {facts.length > 0 && (
        <div className="text-muted">{facts.join(" · ")}</div>
      )}
      {row.transcript && (
        <div className="ds-inset p-2 mt-1 italic">“{row.transcript}”</div>
      )}
    </li>
  );
}

/**
 *  Export.
 *
 *  CSV via a plain link, PDF via the browser's own print. A rendered PDF from
 *  the server would mean a new dependency and a second layout to keep in step
 *  with this one — and the thing most people mean by "PDF" is the page they
 *  are looking at, which is exactly what printing produces.
 */
export function Export({ csvUrl }: { csvUrl: string }) {
  return (
    <div className="flex flex-wrap gap-2 mb-4 print:hidden">
      <a href={csvUrl} className="btn btn-ghost btn-sm ds-focus" download>
        <Download size={13} /> Download as a spreadsheet
      </a>
      <button onClick={() => window.print()} className="btn btn-ghost btn-sm ds-focus">
        Print or save as PDF
      </button>
    </div>
  );
}

/**
 *  The four skills, and the sections each was built from.
 *
 *  The server has returned this on every result since M7. Nothing declared it
 *  and nothing drew it, so an assessment that measured listening and speaking
 *  separately reported one blended number and a candidate had no way to see
 *  which half was the problem.
 *
 *  Each skill names its sections and what each counted for. A weight is shown
 *  only where it is not the default, because "1 part" on every row is noise
 *  and a "0 parts" or "3 parts" is the answer to the question somebody is
 *  about to ask.
 */
export function Skills({ skills, sections, scaleMin, scaleMax }: {
  skills: SkillScore[]; sections: SectionResult[];
  scaleMin: number; scaleMax: number;
}) {
  const measured = skills.filter((s) => s.section_count > 0);
  if (measured.length < 2) {
    // One skill is not a rollup, it is the overall score again under a
    // different heading.
    return null;
  }

  const span = Math.max(1, scaleMax - scaleMin);

  return (
    <Section title="By skill" className="mb-4">
      <p className="text-[11px] text-muted mb-3 leading-relaxed">
        Each skill is built only from the sections that measure it. A weak
        listening score does not pull down speaking, and neither is an average
        of the other.
      </p>

      <div className="space-y-3">
        {measured.map((skill) => {
          const mine = sections
            .filter((x) => x.skill === skill.skill)
            .sort((a, b) => a.position - b.position);

          return (
            <div key={skill.skill}>
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-xs font-bold capitalize">{skill.skill}</span>
                <span className="text-sm font-bold tabular-nums">
                  {skill.score === null ? "—" : skill.score}
                </span>
              </div>

              <div className="h-1.5 rounded-full mt-1 overflow-hidden"
                   style={{ background: "var(--inset)" }}>
                {skill.score !== null && (
                  <div className="h-full rounded-full"
                       style={{
                         width: `${Math.max(0, Math.min(100,
                           ((skill.score - scaleMin) / span) * 100))}%`,
                         background: "var(--primary)",
                       }} />
                )}
              </div>

              <div className="mt-1.5 space-y-0.5">
                {mine.map((section) => (
                  <div key={section.section_id}
                       className="flex items-baseline justify-between gap-2 text-[11px]">
                    <span className="text-muted truncate">
                      {section.title}
                      {section.weight !== 1 && (
                        <span className="ml-1.5 opacity-70">
                          {section.weight === 0
                            ? "· does not count"
                            : `· ${section.weight} parts`}
                        </span>
                      )}
                    </span>
                    <span className="text-muted tabular-nums shrink-0">
                      {section.score === null
                        ? section.unscored_reason || "not scored"
                        : section.score}
                    </span>
                  </div>
                ))}
              </div>

              {skill.note && (
                <p className="text-[10px] text-muted mt-1">{skill.note}</p>
              )}
            </div>
          );
        })}
      </div>
    </Section>
  );
}


/**
 *  How to refer to what a candidate gave, given what they actually did.
 *
 *  Extracted from the result page because it was wrong there, silently, for
 *  as long as non-speaking sections have existed: an assessment can be
 *  entirely reading and writing, and that candidate was told their recordings
 *  were kept, that every figure came from their recording, and that what they
 *  typed was "heard". Every one of those is a true sentence about a different
 *  attempt.
 *
 *  A ternary inside a page cannot be tested without mounting the page, which
 *  means fetching, which means nobody writes the test. Named here, the rule is
 *  three lines and four assertions.
 */
export function answerLabel(hasAudio: boolean): string {
  return hasAudio ? "heard: " : "you wrote: ";
}

export function itemsFootnote(anyAudio: boolean): string {
  return anyAudio
    ? "Every figure here was measured from your own answers. Open a spoken "
      + "item to hear it back with your words on the timeline."
    : "Every figure here was measured from your own answers. Open an item to "
      + "see what you gave and how it was marked.";
}

"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  AlertTriangle, ChevronDown, ChevronRight, Clock, Gauge, Loader2, Lock, Mic,
  Volume2,
} from "lucide-react";
import { ListenBack } from "@/components/ListenBack";
import { RequireAuth } from "@/components/RequireAuth";
import { useRole } from "@/components/RoleProvider";
import { SITTING_ROLES } from "@/lib/nav";
import { taskLabel } from "@/lib/tasks";
import { DIMENSION_LABEL, DIMENSION_MEANING } from "@/lib/dimensions";
import {
  Badge, ErrorNote, PageHeader, Section, Skeleton,
} from "@/components/ui";
import {
  ApiError, attemptApi, type PreviousAttempt,
  type PracticeOutcome, type PrimaryDiagnosis, type ResponseMetrics,
  type ResultPriority,
} from "@/lib/api";
import { Evidence, Export, Highlights, NarrationCard, Skills, Summary, answerLabel,
         itemsFootnote } from "@/components/Report";
import { useData } from "@/lib/useData";



/** Whose names the sub-scores borrow, for the inline "not an X result" label. */
function vendorResultName(style: string): string {
  switch (style) {
    case "svar_style": return "an SVAR";
    case "versant_style": return "a Versant";
    case "speechx_style": return "a SpeechX";
    default: return "an official";
  }
}

export default function ResultPage() {
  return (
    <RequireAuth roles={SITTING_ROLES}>
      <Result />
    </RequireAuth>
  );
}



function Result() {
  const { user } = useRole();
  const { id } = useParams<{ id: string }>();
  const { data, loading, error, reload } = useData(() => attemptApi.result(id), [id]);

  // Most answers were scored while the student was still talking, so this
  // almost never fires. It exists for the case where the last item was a long
  // one and the model is still working on it.
  useEffect(() => {
    if (!data || data.status === "scored") return;
    const timer = setTimeout(reload, 1500);
    return () => clearTimeout(timer);
  }, [data, reload]);

  // Poll while the AI explanation is still being generated, so the card
  // swaps from "being prepared" to the real thing without a manual refresh.
  // Bounded to a couple of minutes: after that the sweeper is still working
  // and the page can be reopened, but we stop hitting the endpoint.
  const [narrationPolls, setNarrationPolls] = useState(0);
  const narrationStatus = data?.narration?.status;
  useEffect(() => {
    if (!data || data.status !== "scored") return;
    const inFlight = narrationStatus === "pending"
      || narrationStatus === "processing"
      || narrationStatus === "retry_pending";
    if (!inFlight || narrationPolls > 40) return;
    const timer = setTimeout(() => {
      setNarrationPolls((n) => n + 1);
      reload();
    }, 3000);
    return () => clearTimeout(timer);
  }, [data, narrationStatus, narrationPolls, reload]);

  if (loading) return <Skeleton rows={6} />;
  if (error) return <ErrorNote message={error} />;
  if (!data) return null;

  if (data.status !== "scored") {
    return (
      <>
        <PageHeader
          title="Scoring your simulation"
          sub="Transcribing the last of your answers. This page updates itself."
        />
        <div className="ds-card p-6 flex items-center gap-3">
          <Loader2 size={18} className="animate-spin text-muted" />
          <span className="text-xs text-muted">Almost there…</span>
        </div>
      </>
    );
  }

  const measured = Object.entries(data.dimensions);
  const answered = data.responses.filter((r) => !r.skipped);

  return (
    <>
      <PageHeader
        title={data.profile_name}
        sub={`Attempt ${data.attempt_number}${data.is_baseline ? " · baseline" : ""}${
          data.mode === "practice" ? " · practice" : ""}`}
        // Students only.
        //
        // An invited candidate cannot take another -- the server refuses a
        // second attempt, because an invitation is one sitting -- and
        // /simulate is a student page, so clicking this ejected them from
        // their own result to a login screen they have no account for.
        action={user?.role === "candidate" ? undefined
          : <Link href="/simulate" className="btn btn-ghost btn-sm ds-focus">Take another</Link>}
      />

      {/* A sentence before a chart. The Phase 0 rule: a student opening their
          result should meet language they use, not a radar plot. It says what
          happened, where they are and what to do -- and when nothing could be
          scored it says that plainly instead of leading with a blank. */}
      {data.previous && (
        <DeltaCard previous={data.previous} overall={data.overall} />
      )}

      <NarrationCard narration={data.narration} />

      <Summary text={data.summary} />

      {data.practice && (
        <PracticeResult outcome={data.practice} carried={data.primary_diagnosis} />
      )}

      {/* ONE answer to "what should I work on first?". The server builds it
          once (app/diagnosis.py) from measured evidence; the summary above,
          the AI card, the button here and the practice result all say what
          it says. This page never derives a weakness of its own. */}
      {!data.practice && data.primary_diagnosis && (
        <WhatToWorkOnFirst primary={data.primary_diagnosis}
                           priorities={data.priorities}
                           attemptId={data.attempt_id}
                           canPractise={user?.role !== "candidate"} />
      )}

      {!data.practice && user?.role !== "candidate"
        && (data.priorities.length > 0 || data.primary_diagnosis) && (
        <PractiseNext priorities={data.priorities} primary={data.primary_diagnosis}
                      profileId={data.profile_id} attemptId={data.attempt_id} />
      )}

      {/* Staged reveal (GAM-18): the number, then each sub-score, then the one
          thing to change. The reward is information arriving in order — there
          is nothing random about it. */}
      <div className="grid lg:grid-cols-3 gap-4 mb-4">
        <Section className="lg:col-span-1 reveal reveal-1">
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] font-bold uppercase tracking-wide text-muted">
              Overall
            </span>
            {!data.calibrated && (
              <Badge tone="var(--rag-amber)">
                <AlertTriangle size={9} /> not validated
              </Badge>
            )}
          </div>
          {/* A missing overall used to render as an em dash at 48px in grey,
              which reads as a redacted number rather than an absent one --
              and said nothing about why. If nothing could be measured, the
              honest thing is to say so where the score would have been. */}
          {data.overall != null ? (
            <div className="flex items-baseline gap-2 mt-1">
              <span className="text-5xl font-bold leading-none"
                    style={{ color: data.calibrated ? "var(--primary)" : "var(--muted)" }}>
                {data.overall}
              </span>
              <span className="text-xs text-muted">/ {data.scale_max}</span>
            </div>
          ) : (
            <div className="mt-2">
              <div className="text-sm font-bold" style={{ color: "var(--rag-amber)" }}>
                Not scored
              </div>
              <p className="text-[11px] text-muted mt-1.5 leading-relaxed">
                {Object.keys(data.unscored).length > 0
                  ? "This server could not produce enough measures to combine into an overall. Your recordings are saved — the detail below says what was missing."
                  : "There were not enough measured dimensions to combine into an overall for this attempt."}
              </p>
            </div>
          )}
          {data.band && data.calibrated && (
            <div className="mt-2"><Badge tone="var(--primary)">{data.band}</Badge></div>
          )}
          {/* An uncalibrated composite shown in the product's brand colour,
              on a 20-80 scale that looks like a vendor band, is how somebody
              ends up quoting it to a recruiter. Greyed, badged, and explained
              until a validation study says otherwise. */}
          <p className="text-[11px] text-muted mt-3 leading-relaxed">
            {data.calibration_note || (
              `Built from the ${data.overall_basis.length} measures below. Not a ` +
              `vendor score and not to be quoted as one.`)}
          </p>
          {data.overall_basis.length > 0 && (
            <p className="text-[10px] text-muted mt-2 leading-relaxed">
              Based on: {data.overall_basis.join(", ")}. An attempt measuring
              different things is not directly comparable to this one.
            </p>
          )}

          {/* Where this sits on the CEFR ladder.
              Deliberately small, deliberately below the number, and
              deliberately carrying its own disclaimer rather than relying on
              one further down the page: a level is the most quotable thing on
              this screen, and no concordance study stands behind it. The cut
              points are the same ones the bands above use, so the two can
              never contradict each other. */}
          {data.cefr_level && (
            <div className="ds-inset p-3 mt-4">
              <div className="flex items-baseline gap-2">
                <span className="text-[11px] font-bold uppercase tracking-wide text-muted">
                  CEFR
                </span>
                <span className="text-lg font-bold leading-none">
                  {data.cefr_level}
                </span>
                <Badge tone="var(--rag-amber)">
                  <AlertTriangle size={9} /> indicative
                </Badge>
              </div>
              <p className="text-[11px] text-muted mt-1.5 leading-relaxed">
                {data.cefr_descriptor}
              </p>
              <p className="text-[10px] text-muted mt-1.5 leading-relaxed">
                {data.cefr_caveat}
              </p>
            </div>
          )}

          {/* A vendor-style simulation restates the same composite on the
              scale that format publishes, under that format's sub-score
              names. It sits below our own number rather than replacing it,
              because ours is the one we can defend: no concordance study has
              ever been run, so this is orientation, not a predicted result. */}
          {data.presentation && (
            <div className="ds-inset p-3 mt-4">
              <div className="flex items-center gap-1.5 mb-1">
                <span className="text-[11px] font-bold uppercase tracking-wide text-muted">
                  On this format&rsquo;s scale
                </span>
                {data.presentation.estimated && (
                  <Badge tone="var(--rag-amber)">
                    <AlertTriangle size={9} /> estimated
                  </Badge>
                )}
              </div>
              {/* Said where the band is read, not only in the note below it:
                  the rows borrow the vendor's competency names, and a
                  recruiter skimming could take the band for the vendor's. */}
              <p className="text-[11px] font-semibold mt-1" style={{ color: "var(--rag-amber)" }}>
                Our estimate — not {vendorResultName(data.profile_style)} result
              </p>
              {/* A number only where the internal scale was built on this
                  format's range. Everywhere else the band carries the
                  ordering and no figure is invented. */}
              <div className="flex items-baseline gap-2 mt-1">
                {data.presentation.score !== null ? (
                  <>
                    <span className="text-2xl font-bold leading-none text-muted">
                      {data.presentation.score}
                    </span>
                    <span className="text-[11px] text-muted">
                      of {data.presentation.scale_max} · {data.presentation.band}
                    </span>
                  </>
                ) : (
                  <span className="text-lg font-bold leading-none text-muted">
                    {data.presentation.band}
                  </span>
                )}
              </div>

              {/* Each sub-score names the tasks it was built from. A student
                  asking "why is my Vocabulary low when I read well" deserves
                  the answer that reading aloud was never counted towards it. */}
              {data.presentation.subscores.length > 0 && (
                <div className="space-y-2 mt-3">
                  {data.presentation.subscores.map((sub) => (
                    <div key={sub.label}>
                      <div className="flex items-baseline justify-between gap-2">
                        <span className="text-[11px] font-semibold">{sub.label}</span>
                        <span className="text-[11px] font-bold">
                          {sub.score !== null ? sub.score : sub.band}
                        </span>
                      </div>
                      {sub.means && (
                        <p className="text-[10px] text-muted leading-relaxed">
                          {sub.means}
                        </p>
                      )}
                      {sub.from_tasks.length > 0 && (
                        <p className="text-[10px] text-muted leading-relaxed opacity-80">
                          From {sub.from_tasks.map(taskLabel).join(", ")}
                          {" "}· {sub.responses} answers
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {/* A sub-score the attempt could not support changes what the
                  overall means, so it is named rather than quietly dropped. */}
              {Object.keys(data.presentation.missing).length > 0 && (
                <div className="mt-3 pt-2" style={{ borderTop: "1px solid var(--border)" }}>
                  <div className="text-[10px] font-bold uppercase tracking-wide text-muted mb-1">
                    Not reported for this attempt
                  </div>
                  {Object.entries(data.presentation.missing).map(([label, why]) => (
                    <p key={label} className="text-[10px] text-muted leading-relaxed">
                      <span className="font-semibold">{label}</span> — {why}
                    </p>
                  ))}
                </div>
              )}

              <p className="text-[10px] text-muted mt-3 leading-relaxed">
                {data.presentation.note}
              </p>
              {data.presentation.subscore_note && (
                <p className="text-[10px] text-muted mt-1.5 leading-relaxed">
                  {data.presentation.subscore_note}
                </p>
              )}
              {data.presentation.structure_note && (
                <p className="text-[10px] text-muted mt-1.5 leading-relaxed opacity-80">
                  {data.presentation.structure_note}
                  {!data.presentation.weights_published && (
                    <> The four are weighted equally here because no official
                    weighting is published.</>
                  )}
                </p>
              )}
            </div>
          )}

          {/* Company rounds answer the question the student actually has,
              which is not "what is my number" but "would I have got through".
              It sits below the number, not above it, and carries its own
              hedge -- an outcome claim is the easiest thing here to overread,
              and nothing has ever been checked against a real employer
              result. */}
          {data.verdict && (
            <div className="ds-inset p-3 mt-4">
              <div className="flex items-center gap-1.5 mb-1">
                <span className="text-[11px] font-bold uppercase tracking-wide text-muted">
                  On a round of this shape
                </span>
                {data.verdict.estimated && (
                  <Badge tone="var(--rag-amber)">
                    <AlertTriangle size={9} /> estimated
                  </Badge>
                )}
              </div>
              <div className="text-sm font-bold mt-1">{data.verdict.label}</div>
              <p className="text-[11px] text-muted mt-1 leading-relaxed">
                {data.verdict.detail}
              </p>
              <p className="text-[10px] text-muted mt-2 leading-relaxed">
                {data.verdict.note}
              </p>
            </div>
          )}
        </Section>

        <div className="lg:col-span-2 space-y-3">
          {measured.map(([dimension, score], i) => (
            <div key={dimension} className={`ds-card p-3 reveal reveal-${Math.min(i + 2, 4)}`}>
              <div className="flex items-baseline justify-between gap-2 mb-1.5">
                <span className="text-xs font-bold">
                  {DIMENSION_LABEL[dimension] ?? dimension}
                </span>
                <span className="text-sm font-bold">{score}</span>
              </div>
              <div className="ds-track">
                <div className="ds-fill"
                     style={{ width: `${((score - data.scale_min) / (data.scale_max - data.scale_min)) * 100}%` }} />
              </div>
              <div className="flex items-center justify-between gap-2 mt-1.5">
                <span className="text-[11px] text-muted">{DIMENSION_MEANING[dimension] ?? ""}</span>
                {data.confidence[dimension] != null && (
                  <span className="text-[10px] text-muted whitespace-nowrap">
                    confidence {Math.round(data.confidence[dimension] * 100)}%
                  </span>
                )}
              </div>
              {data.dimension_notes[dimension] && (
                <p className="text-[10px] text-muted mt-1 leading-relaxed">
                  {data.dimension_notes[dimension]}
                </p>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* The plan, the evidence, and the export. Everything below is
          derived from measurements already on this page -- nothing here
          computes a score.

          The engine's weighted "biggest lever" and the gain-ranked plan are
          no longer drawn here: both were second answers to "what should I
          work on first?", and on a level result they disagreed with the
          card above. One diagnosis, one voice. */}
      {/* Before the strengths and the plan, because "which skill" is the
          question somebody asks first and it changes what the rest means. */}
      <Skills skills={data.skills ?? []} sections={data.sections ?? []}
              scaleMin={data.scale_min} scaleMax={data.scale_max} />

      <Highlights strengths={data.strengths} weaknesses={data.weaknesses} />

      <Evidence evidence={data.evidence} />

      <Export csvUrl={attemptApi.exportCsvUrl(id)} />

      {data.overall == null && measured.length > 0 && (
        <div className="ds-card p-4 mb-4 text-xs text-muted leading-relaxed">
          No single overall figure for this attempt — too few dimensions were
          measured to combine into one without it meaning something different
          from a full simulation&rsquo;s. The measures above are the useful part.
        </div>
      )}

      {data.environment_note && (
        <div className="ds-card p-4 mb-4 flex items-start gap-3"
             style={{ borderColor: "var(--rag-amber)" }}>
          <AlertTriangle size={15} className="shrink-0 mt-0.5"
                         style={{ color: "var(--rag-amber)" }} />
          <p className="text-xs leading-relaxed">{data.environment_note}</p>
        </div>
      )}

      {/* What is not scored, said out loud. A blank is more useful than a
          confident number with nothing behind it. */}
      {Object.keys(data.unscored).length > 0 && (
        <Section title="Not scored yet" className="mb-4">
          <div className="grid sm:grid-cols-3 gap-2">
            {Object.entries(data.unscored).map(([dimension, why]) => (
              <div key={dimension} className="ds-inset p-3">
                <div className="flex items-center gap-1.5 mb-1">
                  <Lock size={11} className="text-muted" />
                  <span className="text-xs font-semibold">
                    {DIMENSION_LABEL[dimension] ?? dimension}
                  </span>
                </div>
                <p className="text-[11px] text-muted leading-relaxed">{why}</p>
              </div>
            ))}
          </div>
          <p className="text-[11px] text-muted mt-3 leading-relaxed">
            The engine measures what it can actually hear today: timing, pauses
            and speech rate. Pronunciation and grammar need transcription, which
            arrives with the Tier-1 speech model. Until then they are blank
            rather than guessed.
          </p>
        </Section>
      )}

      <Section title={`Item by item — ${answered.length} of ${data.responses.length} answered`}>
        <div className="space-y-2">
          {data.responses.map((item) => (
            <ItemRow key={item.response_id} attemptId={data.attempt_id} item={item} />
          ))}
        </div>
        <p className="text-[11px] text-muted mt-3 leading-relaxed">
          {itemsFootnote(data.responses.some((r) => r.has_audio))}
        </p>
      </Section>

      {data.scoring_ms != null && (
        <div className="text-[10px] text-muted mt-3 flex items-center gap-1.5">
          <Mic size={10} /> Scored in {data.scoring_ms} ms
        </div>
      )}
    </>
  );
}

/** One answer, collapsed to its numbers until the student asks to hear it.
 *
 *  Collapsed by default on purpose: eight expanded players would fetch eight
 *  recordings on page load, which on a hostel connection is the difference
 *  between a report that opens and one that does not.
 */
function ItemRow({ attemptId, item }: { attemptId: string; item: ResponseMetrics }) {
  const [open, setOpen] = useState(false);
  const Chevron = open ? ChevronDown : ChevronRight;

  return (
    <div className="ds-card p-3">
      <button
        onClick={() => setOpen((v) => !v)}
        disabled={item.skipped || !item.has_audio}
        className="w-full flex items-center gap-2 text-left ds-focus disabled:cursor-default"
      >
        {item.skipped || !item.has_audio
          ? <span style={{ width: 14 }} />
          : <Chevron size={14} className="text-muted shrink-0" />}

        <span className="text-[11px] font-bold text-muted w-5 shrink-0">{item.position}</span>

        <span className="flex-1 min-w-0">
          <span className="text-xs font-medium block truncate">
            {item.prompt_text || "—"}
          </span>
          {item.transcript && item.transcript !== item.prompt_text && (
            <span className="text-[11px] text-muted block truncate">
              {answerLabel(item.has_audio)}{item.transcript}
            </span>
          )}
        </span>

        {item.skipped ? (
          <Badge tone="var(--muted)">skipped</Badge>
        ) : (
          <span className="flex items-center gap-3 text-[11px] text-muted shrink-0">
            {item.accuracy != null && (
              <span className="font-bold" style={{
                color: item.accuracy >= 0.9 ? "var(--rag-green)"
                  : item.accuracy >= 0.6 ? "var(--rag-amber)" : "var(--rag-red)",
              }}>
                {Math.round(item.accuracy * 100)}%
              </span>
            )}
            {item.onset_ms != null && (
              <span className="whitespace-nowrap">
                <Clock size={10} className="inline mr-1" />
                {(item.onset_ms / 1000).toFixed(1)}s
              </span>
            )}
            {item.words_per_minute != null && (
              <span className="whitespace-nowrap hidden sm:inline">
                <Gauge size={10} className="inline mr-1" />
                {Math.round(item.words_per_minute)} wpm
              </span>
            )}
            {item.pause_count ? <span>{item.pause_count} pauses</span> : null}
            {item.quality !== "good" && (
              <Badge tone="var(--rag-amber)"><Volume2 size={10} /> {item.quality}</Badge>
            )}
          </span>
        )}
      </button>

      {open && <ListenBack attemptId={attemptId} item={item} />}
    </div>
  );
}

// --------------------------------------------------------------------------
// The improvement loop: before/after, and what to practise next.
// --------------------------------------------------------------------------

/** "+8 since your last attempt" — the number a student actually remembers.
 *  Honest in both directions, and absent when either sitting has no overall. */
function DeltaCard({ previous, overall }: {
  previous: PreviousAttempt; overall: number | null;
}) {
  if (previous.delta == null || overall == null || previous.overall == null) return null;
  const amount = Math.abs(previous.delta);
  // Under two points between two sittings of different items is not a claim
  // worth making either way -- the numbers are shown, the verdict stays calm.
  const same = amount < 2;
  const up = !same && previous.delta > 0;
  const tone = same ? "var(--muted)" : up ? "var(--rag-green)" : "var(--rag-amber)";
  return (
    <div className="ds-card p-3 mb-4 flex items-center gap-4"
         style={{ borderColor: tone }}>
      <div>
        <div className="text-2xl font-bold leading-none">
          {previous.overall} <span className="text-muted">→</span> {overall}
        </div>
        <div className="text-[11px] font-bold mt-1" style={{ color: tone }}>
          {same ? "About the same" : up ? `Up ${amount} points` : `Down ${amount} points`}
        </div>
      </div>
      <div className="text-xs text-muted leading-relaxed">
        {same
          ? `Compared with attempt ${previous.attempt_number}.`
          : up
            ? `Since attempt ${previous.attempt_number}. Keep going.`
            : `Since attempt ${previous.attempt_number}. One sitting can vary — the practice list below is the plan.`}
      </div>
    </div>
  );
}

/** Starting a practice session anchored to THIS result, so its outcome and
 *  retake point at the assessment that prescribed it -- never "whatever is
 *  latest". One hook, so the diagnosis card and the secondary cards cannot
 *  start sessions by different rules. */
function usePracticeStart(attemptId: string) {
  const router = useRouter();
  const [busy, setBusy] = useState("");
  const [problem, setProblem] = useState("");

  async function start(key: string, profileId: string, sourceAttemptId?: string) {
    setBusy(key); setProblem("");
    try {
      const attempt = await attemptApi.start(profileId, "practice", sourceAttemptId ?? attemptId);
      router.push(`/attempt/${attempt.attempt_id}/check`);
    } catch (err) {
      setProblem(err instanceof ApiError ? err.detail : "Could not start the practice");
      setBusy("");
    }
  }
  async function retake(profileId: string) {
    setBusy("retake"); setProblem("");
    try {
      const attempt = await attemptApi.start(profileId, "practice");
      router.push(`/attempt/${attempt.attempt_id}/check`);
    } catch (err) {
      setProblem(err instanceof ApiError ? err.detail : "Could not start the test");
      setBusy("");
    }
  }
  return { busy, problem, start, retake };
}

/** WHAT TO WORK ON FIRST -- the one diagnosis, in the student's words.
 *
 *  Renders the server's PrimaryDiagnosis and nothing else. "Identified"
 *  names one area, says why, and offers exactly its practice. "Tied"
 *  names the level areas and offers each without crowning one. "Level",
 *  "insufficient" and "none" say honestly that nothing clearly stands out
 *  yet and point at the next attempt. There is no branch here that picks a
 *  dimension from the scores: if the server did not choose, nobody does. */
function WhatToWorkOnFirst({ primary, priorities, attemptId, canPractise }: {
  primary: PrimaryDiagnosis; priorities: ResultPriority[]; attemptId: string;
  canPractise: boolean;
}) {
  const { busy, problem, start } = usePracticeStart(attemptId);
  const identified = primary.status === "identified";
  const tied = primary.status === "tied";
  // The tied group's practice profiles come from the priorities list, which
  // the server ordered to lead with exactly these dimensions.
  const tiedOptions = tied
    ? primary.candidates
        .map((c) => priorities.find((p) => p.dimension === c.dimension))
        .filter((p): p is ResultPriority => Boolean(p && p.practice_profile_id))
    : [];

  return (
    <section className="ds-card p-4 mb-4" style={{ borderColor: "var(--primary)" }}
             data-testid="what-to-work-on-first">
      <div className="text-[11px] font-bold uppercase tracking-wide"
           style={{ color: identified ? "var(--rag-amber)" : "var(--muted)" }}>
        What to work on first
      </div>
      <div className="text-xl font-bold mt-1" data-testid="primary-headline">
        {primary.headline}
      </div>
      <p className="text-sm leading-relaxed mt-1">{primary.reason}</p>

      {primary.evidence && (
        <div className="mt-3">
          <div className="text-[10px] font-bold uppercase tracking-wider text-muted mb-1">
            Why we say this
          </div>
          <p className="text-xs text-muted leading-relaxed">{primary.evidence}</p>
          {identified && primary.confidence === "moderate" && (
            <p className="text-[11px] text-muted leading-relaxed mt-1">
              Based on a small number of answers — another attempt will firm this up.
            </p>
          )}
        </div>
      )}

      {identified && (
        <div className="mt-3">
          <div className="text-[10px] font-bold uppercase tracking-wider text-muted mb-1">
            Practise this
          </div>
          {primary.advice && (
            <p className="text-xs text-muted leading-relaxed mb-2">{primary.advice}</p>
          )}
          {canPractise && primary.practice_profile_id && (
            <button
              onClick={() => void start(primary.dimension, primary.practice_profile_id)}
              disabled={busy !== ""}
              data-testid="primary-practice"
              className="btn btn-primary ds-focus">
              {busy === primary.dimension ? "Starting…"
                : `Practise ${primary.label} — about ${primary.practice_minutes} min`}
            </button>
          )}
        </div>
      )}

      {tied && tiedOptions.length > 0 && canPractise && (
        <div className="mt-3">
          <div className="text-[10px] font-bold uppercase tracking-wider text-muted mb-1">
            {tiedOptions.length === 2 ? "Practise either" : "Practise any of these"}
          </div>
          <div className="flex flex-wrap gap-2">
            {tiedOptions.map((p) => (
              <button key={p.dimension}
                      onClick={() => void start(p.dimension, p.practice_profile_id)}
                      disabled={busy !== ""}
                      className="btn btn-primary btn-sm ds-focus">
                {busy === p.dimension ? "Starting…"
                  : `Practise ${DIMENSION_LABEL[p.dimension] ?? p.dimension} — about ${p.practice_minutes} min`}
              </button>
            ))}
          </div>
        </div>
      )}

      {!identified && !tied && (
        <p className="text-xs text-muted leading-relaxed mt-3">
          The right next step is another attempt — it adds the evidence this
          needs. Practise anything you like in the meantime.
        </p>
      )}

      {problem && <div className="mt-3"><ErrorNote message={problem} /></div>}
    </section>
  );
}

function PractiseNext({ priorities, primary, profileId, attemptId }: {
  priorities: ResultPriority[]; primary: PrimaryDiagnosis | null;
  profileId: string; attemptId: string;
}) {
  const { busy, problem, start, retake } = usePracticeStart(attemptId);

  // The diagnosis card already offered the primary (or the tied group);
  // this lists what is left, and never calls any of it "the most".
  const shown = new Set<string>(
    primary?.status === "identified" ? [primary.dimension]
      : primary?.status === "tied" ? primary.candidates.map((c) => c.dimension)
      : []);
  const rest = priorities.filter((p) => !shown.has(p.dimension));

  return (
    <Section title={rest.length ? "Also worth practising" : "Next step"} className="mb-4">
      {rest.length > 0 && (
        <div className="grid md:grid-cols-3 gap-3">
          {rest.map((priority) => (
            <div key={priority.dimension} className="ds-card p-4 flex flex-col">
              <div className="text-[11px] font-bold uppercase tracking-wide text-muted">
                Needs work
              </div>
              <div className="text-base font-bold mt-0.5">
                {DIMENSION_LABEL[priority.dimension] ?? priority.dimension}
              </div>
              <p className="text-[11px] text-muted leading-relaxed mt-1">
                {DIMENSION_MEANING[priority.dimension] ?? ""}
              </p>
              <p className="text-[10px] text-muted leading-relaxed mt-1 mb-3">
                {priority.evidence}
              </p>
              <button
                onClick={() => void start(priority.dimension, priority.practice_profile_id)}
                disabled={busy !== "" || !priority.practice_profile_id}
                className="btn btn-ghost btn-sm ds-focus mt-auto">
                {busy === priority.dimension ? "Starting…"
                  : `Practise — about ${priority.practice_minutes} min`}
              </button>
            </div>
          ))}
        </div>
      )}
      {problem && <div className="mt-3"><ErrorNote message={problem} /></div>}
      <div className={`${rest.length ? "mt-4" : ""} flex items-center gap-3`}>
        <button onClick={() => void retake(profileId)} disabled={busy !== ""}
                className="btn btn-ghost ds-focus">
          {busy === "retake" ? "Starting…" : "Take this test again"}
        </button>
        <span className="text-[11px] text-muted">
          Practise first, then retake — this page will show the change.
        </span>
      </div>
    </Section>
  );
}

/** A finished practice session: what you practised, how it compares with
 *  your last assessment, and the way back. Never a dead end. */
function PracticeResult({ outcome, carried }: {
  outcome: PracticeOutcome; carried: PrimaryDiagnosis | null;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");
  const label = DIMENSION_LABEL[outcome.dimension] ?? outcome.dimension;

  // Where this practice came from, said exactly. A linked practice carries
  // the prescribing assessment's own diagnosis (recomputed server-side from
  // that attempt's scores, so it is what that page showed). An unlinked one
  // is compared with the most recent assessment and says so -- it never
  // claims that assessment prescribed it.
  const prescribed = outcome.source_linked ? carried : null;
  const prescribedLabel = prescribed?.dimension
    ? (DIMENSION_LABEL[prescribed.dimension] ?? prescribed.dimension) : "";
  const provenance = !outcome.assessment_profile_name ? ""
    : !outcome.source_linked
      ? `This practice was not started from a result, so it is compared with your most recent assessment, ${outcome.assessment_profile_name}.`
      : outcome.trained_primary
        ? `Prescribed by ${outcome.assessment_profile_name}, where ${label.toLowerCase()} was the area to work on first.`
        : prescribed?.status === "identified"
          ? `Prescribed by ${outcome.assessment_profile_name}, where ${prescribedLabel.toLowerCase()} was the area to work on first and ${label.toLowerCase()} was one of the other priorities.`
          : `From ${outcome.assessment_profile_name}, where nothing clearly stood out yet — you chose ${label.toLowerCase()}.`;

  async function retakeAssessment() {
    setBusy(true); setProblem("");
    try {
      const attempt = await attemptApi.start(outcome.assessment_profile_id, "practice");
      router.push(`/attempt/${attempt.attempt_id}/check`);
    } catch (err) {
      setProblem(err instanceof ApiError ? err.detail : "Could not start the test");
      setBusy(false);
    }
  }

  // What one session can honestly claim. "higher/lower" only outside a
  // deliberately conservative band; small movement is "about level"; a thin
  // measurement produces no verdict at all. Practice performance is never
  // presented as proven skill improvement -- the retake is the proof.
  const VERDICT_COPY: Record<string, { head: string; tone: string; body: string }> = {
    higher: {
      head: "Higher than your assessment measured",
      tone: "var(--rag-green)",
      body: "A good sign — but practice items differ from test items. The retake is the real proof.",
    },
    level: {
      head: "About level with your assessment",
      tone: "var(--muted)",
      body: "One short session rarely moves a skill. Practise again, or take the retake when you are ready.",
    },
    lower: {
      head: "Lower than your assessment this time",
      tone: "var(--rag-amber)",
      body: "Practice sessions vary — one session is not a trend. Another short practice may help.",
    },
    insufficient: {
      head: "Not enough measured to compare",
      tone: "var(--muted)",
      body: "Too little was measured this session to say anything reliable. Keep practising and the picture gets clearer.",
    },
  };
  const v = VERDICT_COPY[outcome.verdict] ?? VERDICT_COPY.insufficient;
  return (
    <Section title={`You practised: ${label}`} className="mb-4">
      {provenance && (
        <p className="text-xs leading-relaxed mb-3" data-testid="practice-provenance">
          {provenance}
        </p>
      )}
      {outcome.practice_score != null && outcome.assessment_score != null
        && outcome.verdict !== "insufficient" ? (
        <div className="flex items-center gap-4 mb-3">
          <div>
            <div className="text-2xl font-bold leading-none">
              {outcome.assessment_score} <span className="text-muted">→</span> {outcome.practice_score}
            </div>
            <div className="text-[11px] font-bold mt-1" style={{ color: v.tone }}>
              {v.head}
            </div>
          </div>
          <p className="text-xs text-muted leading-relaxed">
            Assessment score for {label.toLowerCase()}: {outcome.assessment_score}.
            Your practice score this session: {outcome.practice_score}. {v.body}
          </p>
        </div>
      ) : (
        <p className="text-xs text-muted leading-relaxed mb-3">
          This practice focused on {label.toLowerCase()}. {v.body}
        </p>
      )}
      {problem && <div className="mb-3"><ErrorNote message={problem} /></div>}
      <div className="flex items-center gap-3">
        {outcome.assessment_profile_id && (
          <button onClick={() => void retakeAssessment()} disabled={busy}
                  className="btn btn-primary ds-focus">
            {busy ? "Starting…"
              : `${outcome.source_linked ? "Retake" : "Take"} ${outcome.assessment_profile_name}`}
          </button>
        )}
        <Link href="/practise" className="btn btn-ghost ds-focus">
          More practice
        </Link>
      </div>
    </Section>
  );
}

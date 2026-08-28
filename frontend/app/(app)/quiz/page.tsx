"use client";
import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle, Check, ChevronRight, Loader2, RotateCcw, X, Zap,
} from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { useToast } from "@/components/Toast";
import {
  Badge, EmptyState, ErrorNote, PageHeader, Section,
} from "@/components/ui";
import {
  ApiError, practiceApi, type QuizItem, type QuizResult,
} from "@/lib/api";
import { FullscreenPrompt } from "@/components/FullscreenPrompt";
import { useProctoring } from "@/lib/proctoring";
import { CameraPreview } from "@/components/proctoring/CameraPreview";

export default function QuizPage() {
  return (
    <RequireAuth roles={["student"]}>
      <Quiz />
    </RequireAuth>
  );
}

type Stage = "intro" | "idle" | "loading" | "playing" | "marked";

/** The fast loop (QUIZ-01/03).
 *
 *  Three minutes, one item at a time, with a per-item clock — the time
 *  pressure is the point, because it is what fails people in the real MCQ
 *  sections. Running out of time answers the item as unanswered rather than
 *  wrong; those are different facts and the report keeps them apart.
 */
function Quiz() {
  const { toast } = useToast();
  const proctoring = useProctoring();
  const [stage, setStage] = useState<Stage>("intro");
  const [items, setItems] = useState<QuizItem[]>([]);
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<string, number | null>>({});
  const [seconds, setSeconds] = useState(0);
  const [result, setResult] = useState<QuizResult | null>(null);
  const [error, setError] = useState("");

  const item = items[index];

  async function start() {
    setStage("loading");
    setError("");
    setResult(null);
    setAnswers({});
    setIndex(0);
    try {
      const next = await practiceApi.nextQuiz(10);
      if (!next.length) {
        setError("No quiz items have been published for your institution yet.");
        setStage("idle");
        return;
      }
      setItems(next);
      setSeconds(next[0].seconds_allowed);
      setStage("playing");
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : "Could not load a quiz";
      setError(msg);
      toast("error", msg);
      setStage("idle");
    }
  }

  // Auto-start quiz after fullscreen prompt
  useEffect(() => {
    if (stage === "idle") {
      void start();
    }
  }, [stage]); // eslint-disable-line react-hooks/exhaustive-deps

  // Request camera when quiz starts
  useEffect(() => {
    if (stage !== "intro" && !proctoring.state.cameraActive) {
      proctoring.requestCamera();
    }
  }, [stage]);

  if (stage === "intro") {
    return <FullscreenPrompt onStart={() => setStage("idle")} />;
  }

  // The shot clock. Running out is an unanswered item, not a wrong one.
  useEffect(() => {
    if (stage !== "playing" || !item) return;
    if (seconds <= 0) {
      answer(null);
      return;
    }
    const timer = setTimeout(() => setSeconds((s) => s - 1), 1000);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stage, seconds, index]);

  function answer(choice: number | null) {
    if (!item) return;
    const updated = { ...answers, [item.id]: choice };
    setAnswers(updated);

    if (index + 1 < items.length) {
      setIndex(index + 1);
      setSeconds(items[index + 1].seconds_allowed);
    } else {
      void submit(updated);
    }
  }

  async function submit(final: Record<string, number | null>) {
    setStage("loading");
    try {
      setResult(await practiceApi.submitQuiz(
        items.map((i) => ({ item_id: i.id, selected_index: final[i.id] ?? null }))));
      toast("success", "Quiz submitted successfully");
      setStage("marked");
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : "Could not mark the quiz";
      setError(msg);
      toast("error", msg);
      setStage("idle");
    }
  }

  const progress = useMemo(
    () => (items.length ? (index / items.length) * 100 : 0), [index, items.length]);

  if (stage === "loading") {
    return (
      <>
        <PageHeader title="Quiz" />
        <div className="ds-card p-8 flex items-center justify-center gap-3">
          <Loader2 size={18} className="animate-spin text-muted" />
          <span className="text-xs text-muted">One moment…</span>
        </div>
      </>
    );
  }

  if (stage === "marked" && result) {
    return <Marked result={result} onAgain={start} />;
  }

  if (stage === "playing" && item) {
    return (
      <>
        <CameraPreview
          videoRef={proctoring.videoRef}
          faceCount={proctoring.state.faceCount}
          strikes={proctoring.state.strikes}
          isFocused={proctoring.state.isFocused}
        />
        <div className="flex items-center gap-3 mb-4">
          <span className="text-[11px] font-bold uppercase tracking-wider text-muted">
            {item.category.replace(/_/g, " ")}
          </span>
          {item.is_review && <Badge tone="var(--secondary)">from your mistakes</Badge>}
          <div className="flex-1" />
          <span className="text-[11px] text-muted">{index + 1} of {items.length}</span>
          <span className={`text-sm font-bold tabular-nums ${
            seconds <= 5 ? "countdown-critical" : seconds <= 10 ? "countdown-warn" : ""}`}>
            {seconds}s
          </span>
        </div>

        <div className="ds-track mb-5">
          <div className="ds-fill" style={{ width: `${progress}%` }} />
        </div>

        <Section className="mb-4">
          <p className="text-base font-semibold leading-relaxed">{item.stem}</p>
        </Section>

        <div className="space-y-2">
          {item.options.map((option, i) => (
            <button
              key={i}
              onClick={() => answer(i)}
              className="ds-card w-full p-3 text-left text-sm hover:bg-surface2 transition-colors ds-focus flex items-center gap-3"
            >
              <span className="kbd shrink-0">{String.fromCharCode(65 + i)}</span>
              <span className="flex-1">{option}</span>
              <ChevronRight size={14} className="text-muted shrink-0" />
            </button>
          ))}
        </div>

        <button onClick={() => answer(null)} className="btn btn-ghost btn-sm mt-4 ds-focus">
          Skip this one
        </button>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Quiz"
        sub="Grammar, vocabulary and error-spotting under a clock — three minutes, ten items. For the days a full speaking drill is not going to happen."
      />

      {error && <div className="mb-4"><ErrorNote message={error} /></div>}

      <Section className="mb-4">
        <EmptyState
          icon={Zap}
          title="Ten items, about three minutes"
          desc="Anything you get wrong goes into your mistake bank and comes back later, spaced out, until you have it."
          action={<button onClick={start} className="btn btn-primary ds-focus">Start</button>}
        />
      </Section>

      <div className="ds-card p-4 text-xs text-muted leading-relaxed">
        Quiz XP is capped as a share of your week. That is deliberate: quizzes are
        a way to keep going on a bad day, not a way to level up without ever
        speaking. Your first quiz each week always counts in full.
      </div>
    </>
  );
}

function Marked({ result, onAgain }: { result: QuizResult; onAgain: () => void }) {
  return (
    <>
      <PageHeader
        title={`${result.correct} of ${result.total} correct`}
        sub={`${Math.round(result.accuracy * 100)}% this round`}
        action={
          <button onClick={onAgain} className="btn btn-primary btn-sm ds-focus">
            <RotateCcw size={13} /> Another
          </button>
        }
      />

      <div className="grid sm:grid-cols-3 gap-3 mb-4">
        <div className="ds-card p-4">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-muted">
            XP earned
          </div>
          <div className="text-2xl font-bold mt-2" style={{ color: "var(--primary)" }}>
            {result.xp_awarded}
          </div>
          {result.xp_capped && (
            <div className="text-[11px] mt-1.5" style={{ color: "var(--rag-amber)" }}>
              {result.cap_note}
            </div>
          )}
        </div>
        <div className="ds-card p-4 sm:col-span-2">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-muted">
            Today&rsquo;s quest
          </div>
          <div className="flex items-center gap-2 mt-2">
            <div className="flex-1 ds-track">
              <div className="ds-fill" style={{
                width: `${Math.min(100, (result.quest_progress / Math.max(1, result.quest_target)) * 100)}%`,
              }} />
            </div>
            <span className="text-[11px] text-muted whitespace-nowrap">
              {result.quest_progress}/{result.quest_target}
            </span>
          </div>
          <div className="text-[11px] text-muted mt-1.5">
            {result.quest_completed
              ? "Quest complete — your streak is safe for today."
              : "A quiz moves the quest along. A full simulation completes it outright."}
          </div>
        </div>
      </div>

      <Section title="Every item, with the reasoning">
        <div className="space-y-2">
          {result.items.map((row) => (
            <div key={row.item_id} className="ds-inset p-3">
              <div className="flex items-start gap-2">
                {row.is_correct
                  ? <Check size={14} className="shrink-0 mt-0.5" style={{ color: "var(--rag-green)" }} />
                  : <X size={14} className="shrink-0 mt-0.5" style={{ color: "var(--rag-red)" }} />}
                <div className="flex-1">
                  <div className="text-xs font-medium">{row.stem}</div>
                  <div className="text-[11px] mt-1.5">
                    {row.selected_index == null ? (
                      <span className="text-muted">You ran out of time.</span>
                    ) : row.is_correct ? (
                      <span style={{ color: "var(--rag-green)" }}>
                        {row.options[row.selected_index]}
                      </span>
                    ) : (
                      <>
                        <span style={{ color: "var(--rag-red)" }}>
                          {row.options[row.selected_index]}
                        </span>
                        <span className="text-muted"> → </span>
                        <span style={{ color: "var(--rag-green)" }}>
                          {row.options[row.correct_index]}
                        </span>
                      </>
                    )}
                  </div>
                  {!row.is_correct && row.explanation && (
                    <p className="text-[11px] text-muted mt-1.5 leading-relaxed">
                      {row.explanation}
                    </p>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      </Section>

      <div className="ds-card p-4 mt-4 flex items-start gap-2">
        <AlertCircle size={14} className="text-muted shrink-0 mt-0.5" />
        <p className="text-xs text-muted leading-relaxed">
          Anything you got wrong is now in your mistake bank. It comes back tomorrow,
          then in three days, then in a week — and retires once you have had it right
          three times running.
        </p>
      </div>
    </>
  );
}

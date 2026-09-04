"use client";
import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle, Check, ChevronRight, Loader2, RotateCcw, Zap,
} from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { useToast } from "@/components/Toast";
import {
  ErrorNote, PageHeader, Section,
} from "@/components/ui";
import {
  ApiError, practiceApi, type QuizItem, type QuizResult,
} from "@/lib/api";
import { FullscreenPrompt } from "@/components/FullscreenPrompt";
import { ExamSidebar, type ExamQuestionStatus } from "@/components/ExamSidebar";
import { ReviewCard } from "@/components/ReviewCard";
import { useProctoring } from "@/lib/proctoring";
import { markAttempted } from "@/lib/setTracker";
import { setExamMode } from "@/lib/examMode";
import ProctorCamera from "@/app/proctoring/ProctorCamera";

export default function QuizPage() {
  return (
    <RequireAuth roles={["student"]}>
      <Quiz />
    </RequireAuth>
  );
}

type Stage = "intro" | "select" | "idle" | "loading" | "playing" | "marked";

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
  const [showInstructions, setShowInstructions] = useState(false);
  const [difficulty, setDifficulty] = useState<string>("");

  const item = items[index];

  const progress = useMemo(
    () => (items.length ? (index / items.length) * 100 : 0), [index, items.length]);

  const questionStatuses: ExamQuestionStatus[] = useMemo(() =>
    items.map((q, i) => ({
      id: q.id, index: i + 1, answered: answers[q.id] != null, selectedOption: answers[q.id] ?? null,
    })),
    [items, answers]
  );

  async function autoStart() {
    setStage("loading");
    setError("");
    setResult(null);
    setAnswers({});
    setIndex(0);
    try {
      // Fetch 10 random quiz items with optional difficulty filter
      const next = await practiceApi.nextQuiz(10, "", difficulty || undefined);
      if (!next.length) {
        setError("No quiz items have been published for your institution yet.");
        setStage("intro");
        return;
      }
      setItems(next);
      setSeconds(next[0].seconds_allowed);
      setExamMode(true);
      setStage("playing");
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : "Could not load a quiz";
      setError(msg);
      toast("error", msg);
      setStage("intro");
    }
  }

  // Auto-start quiz after fullscreen prompt
  useEffect(() => {
    if (stage === "idle") {
      void autoStart();
    }
  }, [stage]); // eslint-disable-line react-hooks/exhaustive-deps

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

  if (stage === "intro") {
    return <FullscreenPrompt onStart={() => setStage("idle")} />;
  }

  // Difficulty selection screen
  if (stage === "select") {
    return (
      <>
        <PageHeader
          title="Quiz"
          sub="Grammar, vocabulary and error-spotting — 10 items at a time."
        />
        {error && <div className="mb-4"><ErrorNote message={error} /></div>}
        <div className="ds-card p-6 mb-4">
          <div className="text-sm font-bold mb-3">Choose difficulty level</div>
          <div className="flex gap-3 mb-4">
            {[{"value": "", "label": "All Levels", "color": "var(--primary)"},
              {"value": "easy", "label": "Easy", "color": "var(--rag-green)"},
              {"value": "medium", "label": "Medium", "color": "var(--rag-amber)"},
              {"value": "hard", "label": "Hard", "color": "var(--rag-red)"}
            ].map((d) => (
              <button key={d.value} onClick={() => setDifficulty(d.value)}
                className={`px-4 py-2 text-sm font-semibold rounded-lg transition-colors ds-focus ${difficulty === d.value ? "text-white" : "text-muted hover:text-text"}`}
                style={{ background: difficulty === d.value ? d.color : "var(--surface-2)" }}>
                {d.label}
              </button>
            ))}
          </div>
          <div className="text-xs text-muted mb-4">
            10 questions · about 3 minutes · timer per question
          </div>
          <div className="flex gap-3">
            <button onClick={() => void autoStart()}
              className="btn btn-primary ds-focus flex-1">
              Start Quiz
            </button>
            <button onClick={() => setShowInstructions(!showInstructions)}
              className="btn btn-ghost ds-focus">
              Instructions
            </button>
          </div>
        </div>
        {showInstructions && (
          <div className="ds-card p-4 text-xs text-muted leading-relaxed">
            <ul className="space-y-1.5">
              <li>• Limited time per question (shown in the timer)</li>
              <li>• Select one option (A, B, C, D) to answer</li>
              <li>• Once you answer, you cannot go back</li>
              <li>• Skipping counts as unanswered</li>
              <li>• Score shown at the end with explanations</li>
            </ul>
          </div>
        )}
      </>
    );
  }

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

  function navigateForward(newIndex: number) {
    if (newIndex > index && newIndex < items.length) {
      setIndex(newIndex);
      setSeconds(items[newIndex].seconds_allowed);
    }
  }

  async function submit(final: Record<string, number | null>) {
    setStage("loading");
    try {
      setResult(await practiceApi.submitQuiz(
        items.map((i) => ({ item_id: i.id, selected_index: final[i.id] ?? null }))));
      // Mark all items as attempted to prevent duplicates
      for (const i of items) {
        markAttempted("quiz", i.id);
      }
      toast("success", "Quiz submitted successfully");
      proctoring.stopCamera();
      setExamMode(false);
      setStage("marked");
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : "Could not mark the quiz";
      setError(msg);
      toast("error", msg);
      setStage("intro");
    }
  }

  if (stage === "loading") {
    return (
      <>
        <PageHeader title="Quiz" />
        <div className="ds-card p-8 flex items-center justify-center gap-3">
          <Loader2 size={18} className="animate-spin text-muted" />
          <span className="text-xs text-muted">Loading questions…</span>
        </div>
      </>
    );
  }

  if (stage === "marked" && result) {
    return <Marked result={result} onAgain={autoStart} />;
  }

  if (stage === "playing" && item) {
    const isCompany = item.company && item.company.length > 0;
    const companyLabel = isCompany ? `Company: ${item.company}` : "General";

    return (
      <>
        <ProctorCamera
          sessionId={items[0]?.id ?? "quiz-session"}
          enabled
          onViolation={() => {}}
          examCompleted={false}
          onAutoEnd={() => submit(answers)}
        />

        {/* Question header */}
        <div className="flex items-center gap-3 mb-4">
          <span className="text-[11px] font-bold uppercase tracking-wider text-muted">
            Question {index + 1} of {items.length}
          </span>
          <span className="text-[11px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full"
                style={{
                  background: isCompany
                    ? "color-mix(in srgb, var(--secondary) 14%, transparent)"
                    : "color-mix(in srgb, var(--primary) 14%, transparent)",
                  color: isCompany ? "var(--secondary)" : "var(--primary)",
                }}>
            {item.category.replace(/_/g, " ")}
          </span>
          {item.is_review && <span className="text-[10px] px-2 py-0.5 rounded-full" style={{ background: "color-mix(in srgb, var(--secondary) 14%, transparent)", color: "var(--secondary)" }}>from your mistakes</span>}
          <div className="flex-1" />
          <span className={`text-sm font-bold tabular-nums ${
            seconds <= 5 ? "countdown-critical" : seconds <= 10 ? "countdown-warn" : ""}`}>
            {seconds}s
          </span>
        </div>

        {/* Progress bar */}
        <div className="ds-track mb-5">
          <div className="ds-fill" style={{ width: `${progress}%` }} />
        </div>

        {/* Question content */}
        <Section className="mb-4">
          <p className="text-base font-semibold leading-relaxed">{item.stem}</p>
        </Section>

        {/* Answer options */}
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

        {/* Navigation buttons */}
        <div className="flex items-center justify-between mt-6 pt-4 border-t border-border">
          <button onClick={() => answer(null)} className="btn btn-ghost btn-sm ds-focus">
            Skip this one
          </button>
          <div className="text-[10px] text-muted">
            {index + 1 < items.length
              ? "Answer to proceed to next question"
              : "Answer to submit quiz"}
          </div>
        </div>
      </>
    );
  }

  return null;
}

function Marked({ result, onAgain }: { result: QuizResult; onAgain: () => void }) {
  return (
    <>
      <PageHeader
        title={`${result.correct} of ${result.total} correct`}
        sub={`${Math.round(result.accuracy * 100)}% this round`}
        action={
          <button onClick={onAgain} className="btn btn-primary btn-sm ds-focus">
            <RotateCcw size={13} /> Another quiz
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
                  : <AlertCircle size={14} className="shrink-0 mt-0.5" style={{ color: "var(--rag-red)" }} />}
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

      {/* Review & Rating Card */}
      <ReviewCard attemptId={undefined} label="quiz" onNext={onAgain} onBack={onAgain} nextLabel="Another quiz →" />
    </>
  );
}

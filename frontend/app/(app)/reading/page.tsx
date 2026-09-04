"use client";
import { useEffect, useRef, useState } from "react";
import { BookOpen, Check, Flame, Gauge, Loader2, X, Zap } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { useToast } from "@/components/Toast";
import {
  ErrorNote, GapMeter, PageHeader, Section,
} from "@/components/ui";
import {
  ApiError, readingApi,
  type ReadingQuestion,
  type ReadingResult, type ReadingStart,
} from "@/lib/api";
import { FullscreenPrompt } from "@/components/FullscreenPrompt";
import { FullscreenGuard } from "@/components/FullscreenGuard";
import { CameraPreview } from "@/components/proctoring/CameraPreview";
import { ExamSidebar, type ExamQuestionStatus } from "@/components/ExamSidebar";
import { ReviewCard } from "@/components/ReviewCard";
import { LevelSelect, type DifficultyLevel } from "@/components/LevelSelect";
import { useProctoring } from "@/lib/proctoring";
import { useData } from "@/lib/useData";
import { markAttempted } from "@/lib/setTracker";
import { setExamMode } from "@/lib/examMode";
import ProctorCamera from "@/app/proctoring/ProctorCamera";

export default function ReadingPage() {
  return (
    <RequireAuth roles={["student"]}>
      <Reading />
    </RequireAuth>
  );
}

type Stage = "intro" | "select" | "loading" | "read" | "answer" | "marked" | "browse";

const KIND_LABEL: Record<string, string> = {
  email: "Email", notice: "Notice", report: "Report",
  article: "Article", instructions: "Instructions", general: "General",
  TCS: "TCS", Infosys: "Infosys", Wipro: "Wipro",
  Accenture: "Accenture", Cognizant: "Cognizant", HCL: "HCL",
  "Tech Mahindra": "Tech Mahindra", Capgemini: "Capgemini",
};

function Reading() {
  const { toast } = useToast();
  const proctoring = useProctoring();
  const { data, loading, error, reload } = useData(() => readingApi.passages());

  const [stage, setStage] = useState<Stage>("intro");
  const [session, setSession] = useState<ReadingStart | null>(null);
  const [questions, setQuestions] = useState<ReadingQuestion[]>([]);
  const [answers, setAnswers] = useState<Record<string, number | null>>({});
  const [result, setResult] = useState<ReadingResult | null>(null);
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0);
  const [showInstructions, setShowInstructions] = useState(false);
  const [answerSeconds, setAnswerSeconds] = useState(0);
  const [difficulty, setDifficulty] = useState<DifficultyLevel>("");

  const openedAt = useRef<number>(0);
  const readMs = useRef<number>(0);

  // Auto-start: fetch a random passage with questions and begin immediately
  async function autoStart() {
    setStage("loading");
    setBusy(true);
    try {
      const started = await readingApi.random();
      // Mark this passage as attempted so it won't appear again today
      markAttempted("reading", started.passage_id);
      setSession(started);
      setQuestions([]);
      setAnswers({});
      setResult(null);
      setCurrentQuestionIndex(0);
      setAnswerSeconds(0);
      openedAt.current = Date.now();
      setExamMode(true);
      setStage("read");
    } catch (err) {
      setProblem(err instanceof ApiError ? err.detail : "No reading passages with questions available yet. Please try again later.");
      toast("error", err instanceof ApiError ? err.detail : "No passages available");
      setStage("intro");
    } finally {
      setBusy(false);
    }
  }

  async function finishedReading() {
    if (!session) return;
    readMs.current = Date.now() - openedAt.current;
    setBusy(true);
    try {
      setQuestions(await readingApi.questions(session.attempt_id));
      setStage("answer");
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : "Could not load the questions";
      setProblem(msg);
      toast("error", msg);
    } finally {
      setBusy(false);
    }
  }

  async function submit() {
    if (!session) return;
    setBusy(true);
    try {
      setResult(await readingApi.submit(session.attempt_id, {
        answers: questions.map((q) => ({
          item_id: q.id, selected_index: answers[q.id] ?? null,
        })),
        read_ms: readMs.current,
      }));
      toast("success", "Answers submitted successfully");
      proctoring.stopCamera();
      setExamMode(false);
      setStage("marked");
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : "Could not submit";
      setProblem(msg);
      toast("error", msg);
    } finally {
      setBusy(false);
    }
  }

  function begin(_passage: any) {
    void autoStart();
  }

  // Auto-start with a random passage after fullscreen prompt
  useEffect(() => {
    if (data && data.length > 0 && stage === "browse" && !session && !busy) {
      setBusy(true);
      void autoStart();
    }
  }, [data, stage, session, busy]); // eslint-disable-line react-hooks/exhaustive-deps

  if (stage === "intro") {
    return <LevelSelect skill="reading" onSelect={(level) => { setDifficulty(level); setStage("select"); }} />;
  }

  if (stage === "select") {
    return <FullscreenPrompt onStart={autoStart} />;
  }

  if (stage === "loading") {
    return (
      <>
        <PageHeader title="Reading" sub="Loading passage…" />
        <div className="ds-card p-8 flex items-center justify-center gap-3">
          <Loader2 size={18} className="animate-spin text-muted" />
          <span className="text-xs text-muted">Selecting a random passage…</span>
        </div>
      </>
    );
  }

  // ------------------------------------------------------------------ read --
  if (stage === "read" && session) {
    return (
      <FullscreenGuard>
        <CameraPreview
          videoRef={proctoring.videoRef}
          faceCount={proctoring.state.faceCount}
          strikes={proctoring.state.strikes}
          isFocused={proctoring.state.isFocused}
        />
        <PageHeader
          title={session.title}
          sub={`${KIND_LABEL[session.kind] ?? session.kind} · ${session.word_count} words · ${session.question_count} questions afterwards`}
        />
        <div className="ds-card p-3 mb-3 text-[11px] text-muted leading-relaxed">
          Read it once, at your normal pace. The passage is taken away before
          the questions — you are not meant to look things up, and the time you
          spend here is measured.
        </div>
        <Section>
          <div className="text-sm leading-loose whitespace-pre-line max-w-[65ch]">
            {session.body}
          </div>
        </Section>
        {problem && <div className="mt-4"><ErrorNote message={problem} /></div>}
        <button onClick={finishedReading} disabled={busy}
                className="btn btn-primary w-full ds-focus mt-4">
          {busy ? "Loading…" : "I have finished reading — show the questions"}
        </button>
      </FullscreenGuard>
    );
  }

  // ---------------------------------------------------------------- answer --
  if (stage === "answer" && session) {
    const answered = questions.filter((q) => answers[q.id] != null).length;
    const currentQuestion = questions[currentQuestionIndex];
    const isCompany = session.kind !== "general" && session.kind !== "article" && session.kind !== "email" && session.kind !== "notice" && session.kind !== "report";
    const companyLabel = isCompany ? `${session.kind} Round` : "General";

    const questionStatuses: ExamQuestionStatus[] = questions.map((q, i) => ({
      id: q.id, index: i + 1, answered: answers[q.id] != null, selectedOption: answers[q.id] ?? null,
    }));

    const navigateForward = (newIndex: number) => {
      if (newIndex > currentQuestionIndex && newIndex < questions.length) {
        setCurrentQuestionIndex(newIndex);
      }
    };

    const answerQuestion = (choice: number | null) => {
      if (!currentQuestion) return;
      const updated = { ...answers, [currentQuestion.id]: choice };
      setAnswers(updated);
      if (currentQuestionIndex + 1 < questions.length) {
        setCurrentQuestionIndex(currentQuestionIndex + 1);
      }
    };

    const totalAnswerTime = 600;
    const remainingSeconds = Math.max(0, totalAnswerTime - answerSeconds);
    const remainingMinutes = Math.floor(remainingSeconds / 60);
    const remainingSecs = remainingSeconds % 60;

    return (
      <>
        <ProctorCamera
          sessionId={session.attempt_id}
          enabled
          onViolation={() => {}}
          examCompleted={false}
          onAutoEnd={submit}
        />

        <PageHeader title={session.title}
                    sub="Choose one answer for each question. The passage is no longer available." />

        <div className="flex items-center gap-3 mb-4">
          <span className="text-[11px] font-bold uppercase tracking-wider text-muted">
            Question {currentQuestionIndex + 1} of {questions.length}
          </span>
          <div className="flex-1" />
          <span className="text-xs text-muted">
            {answered} of {questions.length} answered
          </span>
        </div>

        {currentQuestion && (
          <Section>
            <div className="flex items-start gap-2 mb-3">
              <span className="shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-[11px] font-bold mt-0.5"
                    style={answers[currentQuestion.id] != null
                      ? { background: "var(--rag-green)", color: "#fff" }
                      : { background: "var(--surface-2)", color: "var(--muted)" }}>
                {answers[currentQuestion.id] != null ? <Check size={12} /> : currentQuestionIndex + 1}
              </span>
              <div className="text-sm font-semibold">{currentQuestion.stem}</div>
            </div>
            <div className="space-y-2">
              {currentQuestion.options.map((opt, i) => (
                <button
                  key={i}
                  onClick={() => answerQuestion(i)}
                  className="w-full flex items-center gap-3 text-left p-3 rounded-lg ds-focus transition-colors"
                  style={{
                    border: `1.5px solid ${answers[currentQuestion.id] === i ? "var(--primary)" : "var(--border)"}`,
                    background: answers[currentQuestion.id] === i
                      ? "color-mix(in srgb, var(--primary) 14%, var(--surface))"
                      : "var(--surface)",
                  }}
                >
                  <span className="shrink-0 rounded-full flex items-center justify-center"
                        style={{
                          width: 18, height: 18,
                          border: `2px solid ${answers[currentQuestion.id] === i ? "var(--primary)" : "var(--muted)"}`,
                        }}>
                    {answers[currentQuestion.id] === i && (
                      <span className="rounded-full" style={{ width: 8, height: 8, background: "var(--primary)" }} />
                    )}
                  </span>
                  <span className="text-sm leading-snug"
                        style={{ color: answers[currentQuestion.id] === i ? "var(--text)" : "var(--fg)",
                                 fontWeight: answers[currentQuestion.id] === i ? 600 : 400 }}>
                    <span className="text-muted mr-1.5">{String.fromCharCode(65 + i)}.</span>
                    {opt}
                  </span>
                </button>
              ))}
            </div>
          </Section>
        )}

        <div className="flex items-center justify-between mt-6 pt-4 border-t border-border">
          <button onClick={() => answerQuestion(null)} className="btn btn-ghost btn-sm ds-focus">
            Skip this one
          </button>
          {currentQuestionIndex + 1 === questions.length ? (
            <button onClick={submit} disabled={busy || answered === 0}
                    className="btn btn-primary ds-focus">
              {busy ? "Marking…"
                    : answered < questions.length
                      ? `Submit — ${questions.length - answered} still unanswered`
                      : "Submit answers"}
            </button>
          ) : (
            <div className="text-[10px] text-muted">
              Answer to proceed to next question
            </div>
          )}
        </div>
      </>
    );
  }

  // ---------------------------------------------------------------- marked --
  if (stage === "marked" && result) {
    return (
      <>
        <PageHeader
          title={`${result.correct} of ${result.total} correct`}
          sub={result.title}
          action={
            <button onClick={() => autoStart()}
                    className="btn btn-primary btn-sm ds-focus">
              Another passage
            </button>
          }
        />

        <div className="grid sm:grid-cols-2 gap-3 mb-4">
          <div className="ds-card p-4">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-muted">
              Comprehension
            </div>
            <div className="text-2xl font-bold mt-2" style={{ color: "var(--primary)" }}>
              {result.score}
            </div>
            <div className="text-[11px] text-muted mt-1">out of 100 · {result.band}</div>
          </div>
          <div className="ds-card p-4">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-muted flex items-center gap-1.5">
              <Gauge size={11} /> Reading rate
            </div>
            <div className="text-2xl font-bold mt-2" style={{ color: "var(--secondary)" }}>
              {result.words_per_minute ?? "—"}
              {result.words_per_minute != null && (
                <span className="text-xs font-normal text-muted ml-1">wpm</span>
              )}
            </div>
            <div className="text-[11px] text-muted mt-1">
              {result.word_count} words
            </div>
          </div>
        </div>

        <div className="ds-card p-3 mb-4 text-xs leading-relaxed">
          {result.rate_note}
        </div>

        <div className="ds-card p-4 mb-4 flex items-center gap-4 flex-wrap">
          <span className="flex items-center gap-1.5 text-sm font-bold"
                style={{ color: "var(--primary)" }}>
            <Zap size={15} /> +{result.xp_awarded} XP
          </span>
          {result.day_counted_now ? (
            <span className="flex items-center gap-1.5 text-sm font-bold"
                  style={{ color: "var(--rag-green)" }}>
              <Flame size={15} /> Day {result.streak_current} — today is counted
            </span>
          ) : result.streak_current > 0 && (
            <span className="flex items-center gap-1.5 text-xs text-muted">
              <Flame size={13} /> {result.streak_current}-day streak
            </span>
          )}
        </div>

        {/* Review & Rating Card */}
        <ReviewCard attemptId={session?.attempt_id} label="reading" onNext={autoStart} onBack={() => { proctoring.stopCamera(); setStage("intro"); }} nextLabel="Next set →" />

        <Section title="Every question, with the reasoning" className="mb-4">
          <div className="space-y-2">
            {result.items.map((row) => (
              <div key={row.item_id} className="ds-inset p-3">
                <div className="flex items-start gap-2">
                  {row.is_correct
                    ? <Check size={13} className="shrink-0 mt-0.5" style={{ color: "var(--rag-green)" }} />
                    : <X size={13} className="shrink-0 mt-0.5" style={{ color: "var(--rag-red)" }} />}
                  <div className="flex-1">
                    <div className="text-xs font-semibold">{row.stem}</div>
                    {!row.is_correct && (
                      <div className="text-[11px] text-muted mt-1">
                        You chose:{" "}
                        {row.selected_index != null ? row.options[row.selected_index] : "nothing"}
                        {". "}Answer: {row.options[row.correct_index]}
                      </div>
                    )}
                    <p className="text-[11px] text-muted mt-1.5 leading-relaxed">
                      {row.explanation}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Section>

        <Section title="The passage again">
          <div className="text-xs text-muted leading-loose whitespace-pre-line max-w-[65ch]">
            {result.body}
          </div>
        </Section>
      </>
    );
  }

  return null;
}

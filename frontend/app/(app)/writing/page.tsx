"use client";
import { useEffect, useRef, useState } from "react";
import { Flame, PenLine, Target, Zap, Loader2 } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { useToast } from "@/components/Toast";
import {
  ErrorNote, GapMeter, PageHeader, Section, Skeleton,
} from "@/components/ui";
import {
  ApiError, writingApi,
  type WritingPromptRow, type WritingResult,
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

export default function WritingPage() {
  return (
    <RequireAuth roles={["student"]}>
      <Writing />
    </RequireAuth>
  );
}

type Stage = "intro" | "select" | "loading" | "write" | "marked" | "review";

const KIND_LABEL: Record<string, string> = {
  email: "Email", report: "Report", essay: "Essay",
  summary: "Summary", complaint: "Complaint",
};

const MEASURE_LABEL: Record<string, string> = {
  task_response: "Task response",
  coherence: "Coherence",
  lexical_range: "Lexical range",
  grammatical_accuracy: "Grammatical accuracy",
  mechanics: "Mechanics",
};

function Writing() {
  const { toast } = useToast();
  const proctoring = useProctoring();
  const { data, loading, error, reload } = useData(() => writingApi.prompts());

  const [stage, setStage] = useState<Stage>("intro");
  const [prompts, setPrompts] = useState<WritingPromptRow[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [text, setText] = useState("");
  const [taskRating, setTaskRating] = useState(0);
  const [result, setResult] = useState<WritingResult | null>(null);
  const [results, setResults] = useState<WritingResult[]>([]);
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);
  const [showInstructions, setShowInstructions] = useState(false);
  const [writeSeconds, setWriteSeconds] = useState(0);
  const [difficulty, setDifficulty] = useState<DifficultyLevel>("");
  const openedAt = useRef<number>(0);

  const prompt = prompts[currentIndex] ?? null;

  // Draft survives accidental navigation
  useEffect(() => {
    if (stage !== "write" || !prompt) return;
    const key = `writing-draft-${prompt.id}`;
    const saved = window.localStorage.getItem(key);
    if (saved && !text) setText(saved);
    const timer = window.setInterval(() => {
      window.localStorage.setItem(key, text);
    }, 2_000);
    return () => window.clearInterval(timer);
  }, [stage, prompt, text]);

  const words = text.trim() ? text.trim().split(/\s+/).length : 0;

  // Auto-start: pick 10 random general prompts
  async function autoStart() {
    setStage("loading");
    setProblem("");
    try {
      // Fetch all prompts, filter to general, pick 10 random
      const allPrompts = await writingApi.prompts();
      const general = allPrompts.filter(
        (p) => !p.company || p.company === "" || p.company === "General"
      );
      const pool = general.length > 0 ? general : allPrompts;
      // Shuffle and take 10
      const shuffled = [...pool].sort(() => Math.random() - 0.5);
      const selected = shuffled.slice(0, Math.min(10, shuffled.length));
      if (selected.length === 0) {
        setProblem("No writing prompts available yet.");
        setStage("intro");
        return;
      }
      // Mark all selected prompts as attempted
      for (const p of selected) {
        markAttempted("writing", p.id);
      }
      setPrompts(selected);
      setCurrentIndex(0);
      setText("");
      setResult(null);
      openedAt.current = Date.now();
      setWriteSeconds(0);
      setStage("write");
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : "Could not load writing prompts";
      setProblem(msg);
      toast("error", msg);
      setStage("intro");
    }
  }

  async function submit() {
    if (!prompt) return;
    setBusy(true);
    setProblem("");
    try {
      const marked = await writingApi.submit(prompt.id, {
        text,
        minutes_spent: Math.round((Date.now() - openedAt.current) / 60_000),
      });
      setResult(marked);
      setResults((prev) => [...prev, marked]);
      window.localStorage.removeItem(`writing-draft-${prompt.id}`);
      setStage("marked");
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : "Could not submit";
      setProblem(msg);
      toast("error", msg);
    } finally {
      setBusy(false);
    }
  }

  function nextPrompt() {
    if (currentIndex + 1 < prompts.length) {
      setCurrentIndex(currentIndex + 1);
      setText("");
      setResult(null);
      setWriteSeconds(0);
      openedAt.current = Date.now();
      setStage("write");
    } else {
      // All done — show review with camera stopped
      proctoring.stopCamera();
      setExamMode(false);
      setStage("review");
    }
  }

  if (stage === "intro") {
    return <LevelSelect skill="writing" onSelect={(level) => { setDifficulty(level); setStage("select"); }} />;
  }

  if (stage === "select") {
    return <FullscreenPrompt onStart={autoStart} />;
  }

  if (stage === "loading") {
    return (
      <>
        <PageHeader title="Writing" sub="Loading tasks…" />
        <div className="ds-card p-8 flex items-center justify-center gap-3">
          <Loader2 size={18} className="animate-spin text-muted" />
          <span className="text-xs text-muted">Preparing writing tasks…</span>
        </div>
      </>
    );
  }

  // ----------------------------------------------------------------- write --
  if (stage === "write" && prompt) {
    const short = words < prompt.min_words;
    const isCompany = prompt.company && prompt.company !== "" && prompt.company !== "General";
    const companyLabel = isCompany ? "Company Round" : "General";

    // Build question statuses for all prompts in the set
    const questionStatuses: ExamQuestionStatus[] = prompts.map((p, i) => ({
      id: p.id,
      index: i + 1,
      answered: i < currentIndex || (i === currentIndex && text.trim().length > 0),
      selectedOption: null,
    }));

    const totalWriteTime = 1200; // 20 minutes
    const remainingSeconds = Math.max(0, totalWriteTime - writeSeconds);
    const remainingMinutes = Math.floor(remainingSeconds / 60);
    const remainingSecs = remainingSeconds % 60;

    return (
      <>
        <ProctorCamera
          sessionId={prompt.id}
          enabled
          onViolation={() => {}}
          examCompleted={false}
          onAutoEnd={submit}
        />

        {/* Question header */}
        <div className="flex items-center gap-3 mb-4">
          <span className="text-[11px] font-bold uppercase tracking-wider text-muted">
            Task {currentIndex + 1} of {prompts.length}
          </span>
          <div className="flex-1" />
          <span className="text-xs text-muted">
            {currentIndex} of {prompts.length} completed
          </span>
        </div>

        <PageHeader
          title={prompt.title}
          sub={`${KIND_LABEL[prompt.kind] ?? prompt.kind} · about ${prompt.suggested_minutes} minutes · at least ${prompt.min_words} words`}
        />

        <Section title="The situation" className="mb-3">
          <p className="text-xs leading-relaxed">{prompt.scenario}</p>
          <p className="text-sm font-semibold mt-3">{prompt.prompt}</p>
        </Section>

        <Section title="A good answer covers" className="mb-3">
          <ul className="space-y-1.5">
            {prompt.key_points.map((point) => (
              <li key={point} className="flex items-start gap-2 text-xs text-muted">
                <Target size={11} className="shrink-0 mt-0.5" style={{ color: "var(--primary)" }} />
                {point}
              </li>
            ))}
          </ul>
        </Section>

        <Section>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={16}
            placeholder="Write your answer here…"
            className="w-full bg-transparent text-sm leading-relaxed outline-none resize-y ds-focus"
            style={{ fontFamily: "inherit" }}
          />
          <div className="flex items-center gap-3 mt-2 pt-2 border-t border-border">
            <span className="text-[11px] text-muted">
              {words} word{words === 1 ? "" : "s"}
              {short && ` · ${prompt.min_words - words} short of the minimum`}
            </span>
            <span className="text-[10px] text-muted ml-auto">Draft saved automatically</span>
          </div>
        </Section>

        {problem && <div className="mt-4"><ErrorNote message={problem} /></div>}

        <div className="flex gap-2 mt-4">
          <button onClick={() => { setText(""); setStage("write"); }}
                  className="btn btn-ghost ds-focus">Clear</button>
          <button onClick={submit} disabled={busy || words === 0}
                  className="btn btn-primary flex-1 ds-focus">
            {busy ? "Marking…" : short ? "Submit anyway" : "Submit"}
          </button>
        </div>
      </>
    );
  }

  // ---------------------------------------------------------------- marked --
  if (stage === "marked" && result) {
    return (
      <>
        <PageHeader
          title={result.overall != null ? `Overall ${result.overall}` : "Not scored"}
          sub={`${result.title} · ${result.word_count} words`}
          action={
            <button onClick={nextPrompt}
                    className="btn btn-primary btn-sm ds-focus">
              {currentIndex + 1 < prompts.length ? `Next task (${currentIndex + 2}/${prompts.length})` : "Done"}
            </button>
          }
        />

        {result.too_short && (
          <div className="ds-card p-4 mb-4" style={{ borderColor: "var(--rag-amber)" }}>
            <div className="text-sm font-bold mb-1">Too short to judge</div>
            <p className="text-xs text-muted leading-relaxed">{result.notes[0]}</p>
          </div>
        )}

        {result.measures.length > 0 && (
          <div className="space-y-2 mb-4">
            {result.measures.map((m) => (
              <div key={m.name} className="ds-card p-3">
                <div className="flex items-baseline justify-between gap-2 mb-1.5">
                  <span className="text-xs font-bold">
                    {MEASURE_LABEL[m.name] ?? m.name}
                  </span>
                  <span className="text-xs font-bold"
                        style={{ color: m.confidence > 0 ? "var(--primary)" : "var(--muted)" }}>
                    {m.confidence > 0 ? m.score : "not measured"}
                  </span>
                </div>
                {m.confidence > 0 && <GapMeter percent={m.score} />}
                <p className="text-[11px] text-muted mt-1.5 leading-relaxed">{m.basis}</p>
              </div>
            ))}
          </div>
        )}

        {result.xp_awarded > 0 && (
          <div className="ds-card p-4 mb-4 flex items-center gap-4 flex-wrap">
            <span className="flex items-center gap-1.5 text-sm font-bold"
                  style={{ color: "var(--primary)" }}>
              <Zap size={15} /> +{result.xp_awarded} XP
            </span>
            {result.day_counted_now && (
              <span className="flex items-center gap-1.5 text-sm font-bold"
                    style={{ color: "var(--rag-green)" }}>
                <Flame size={15} /> Day {result.streak_current} — today is counted
              </span>
            )}
          </div>
        )}

        <Section title="What these numbers are not" className="mb-4">
          {result.notes.map((note) => (
            <p key={note} className="text-xs text-muted leading-relaxed">{note}</p>
          ))}
          <p className="text-xs text-muted leading-relaxed mt-2">
            Nothing here read your argument. A well-structured piece that says
            something wrong scores well; a blunt, correct one may not. Show it
            to a person if the content matters.
          </p>
        </Section>

        <Section title="What you wrote">
          <p className="text-xs leading-relaxed whitespace-pre-line">{result.text}</p>
        </Section>

        {/* Review & Rating Card */}
        <div className="ds-card p-5 mb-4">
          <div className="flex items-center justify-between mb-3">
            <div className="text-sm font-bold">Rate this writing task</div>
            <div className="flex gap-1">
              {[1, 2, 3, 4, 5].map((star) => (
                <button key={star}
                  onClick={() => setTaskRating(star)}
                  className="text-lg transition-colors"
                  style={{ color: star <= taskRating ? "var(--rag-amber)" : "var(--border)" }}>
                  ★
                </button>
              ))}
            </div>
          </div>
          <div className="text-xs text-muted leading-relaxed mb-3">
            How was this writing task? Your rating helps improve question quality.
          </div>
          <div className="flex items-center gap-3">
            <button onClick={nextPrompt}
                    className="btn btn-primary btn-sm ds-focus flex-1">
              {currentIndex + 1 < prompts.length ? `Next task (${currentIndex + 2}/${prompts.length})` : "Back to practice"}
            </button>
          </div>
        </div>
      </>
    );
  }

  // ---------------------------------------------------------------- review --
  if (stage === "review") {
    const completed = results.length;
    const avgScore = completed > 0
      ? (results.reduce((sum, r) => sum + (r.overall ?? 0), 0) / completed).toFixed(1)
      : "—";
    const totalWords = results.reduce((sum, r) => sum + r.word_count, 0);
    const totalXp = results.reduce((sum, r) => sum + r.xp_awarded, 0);

    return (
      <>
        <PageHeader
          title="Writing Practice — Summary"
          sub={`${completed} of ${prompts.length} tasks completed`}
          action={
            <button onClick={() => {
              setPrompts([]);
              setResults([]);
              setCurrentIndex(0);
              setResult(null);
              setStage("intro");
              toast("success", "All writing tasks completed!");
            }} className="btn btn-primary btn-sm ds-focus">
              Back to practice
            </button>
          }
        />

        {completed === 0 ? (
          <div className="ds-card p-8 text-center">
            <PenLine size={24} className="mx-auto mb-2 text-muted" />
            <p className="text-sm text-muted">No tasks were submitted.</p>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
              <div className="ds-card p-3 text-center">
                <div className="text-lg font-bold" style={{ color: "var(--primary)" }}>{completed}</div>
                <div className="text-[10px] text-muted">Tasks done</div>
              </div>
              <div className="ds-card p-3 text-center">
                <div className="text-lg font-bold" style={{ color: "var(--primary)" }}>{avgScore}</div>
                <div className="text-[10px] text-muted">Avg score</div>
              </div>
              <div className="ds-card p-3 text-center">
                <div className="text-lg font-bold" style={{ color: "var(--primary)" }}>{totalWords}</div>
                <div className="text-[10px] text-muted">Total words</div>
              </div>
              <div className="ds-card p-3 text-center">
                <div className="text-lg font-bold" style={{ color: "var(--primary)" }}>+{totalXp}</div>
                <div className="text-[10px] text-muted">XP earned</div>
              </div>
            </div>

            <Section title="Task results">
              <div className="space-y-2">
                {results.map((r, i) => (
                  <div key={r.submission_id} className="ds-card p-3 flex items-center gap-3">
                    <span className="text-xs font-bold text-muted w-6">{i + 1}</span>
                    <div className="flex-1 min-w-0">
                      <div className="text-xs font-semibold truncate">{r.title}</div>
                      <div className="text-[10px] text-muted">{r.word_count} words</div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm font-bold"
                           style={{ color: r.overall != null && r.overall >= 6 ? "var(--rag-green)" : r.overall != null && r.overall >= 4 ? "var(--rag-amber)" : "var(--rag-red)" }}>
                        {r.overall != null ? r.overall : "—"}
                      </div>
                      {r.xp_awarded > 0 && (
                        <div className="text-[9px] text-muted">+{r.xp_awarded} XP</div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </Section>

            {/* Review & Rating Card */}
            <ReviewCard attemptId={undefined} label="writing" onNext={() => setStage("intro")} onBack={() => setStage("intro")} nextLabel="Back to practice" />
          </>
        )}
      </>
    );
  }

  return null;
}

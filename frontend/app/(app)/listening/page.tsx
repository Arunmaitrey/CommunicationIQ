"use client";
import { useCallback, useEffect, useState } from "react";
import {
  Check, Ear, Flame, Loader2, Play, RotateCcw, Square, X, Zap,
} from "lucide-react";
import { AiNarrator } from "@/components/brand/AiNarrator";
import { VoicePicker } from "@/components/VoicePicker";
import { RequireAuth } from "@/components/RequireAuth";
import { useToast } from "@/components/Toast";
import {
  ChoiceOption, ErrorNote, PageHeader, Section,
} from "@/components/ui";
import { speak } from "@/lib/audio";
import {
  ApiError, API_BASE, listeningApi,
  type ListeningQuestion,
  type ListeningResult, type ListeningStart,
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

export default function ListeningPage() {
  return (
    <RequireAuth roles={["student"]}>
      <Listening />
    </RequireAuth>
  );
}

type Stage = "intro" | "select" | "loading" | "listen" | "answer" | "marked" | "browse";

const KIND_LABEL: Record<string, string> = {
  announcement: "Announcement", instructions: "Instructions",
  short_talk: "Short talk", conversation: "Conversation", voicemail: "Voicemail",
};

function Listening() {
  const { toast } = useToast();
  const proctoring = useProctoring();
  const { data, loading, error, reload } = useData(() => listeningApi.passages());

  const [stage, setStage] = useState<Stage>("intro");
  const [session, setSession] = useState<ListeningStart | null>(null);
  const [questions, setQuestions] = useState<ListeningQuestion[]>([]);
  const [answers, setAnswers] = useState<Record<string, number | null>>({});
  const [playsUsed, setPlaysUsed] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [result, setResult] = useState<ListeningResult | null>(null);
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);
  const [difficulty, setDifficulty] = useState<DifficultyLevel>("");
  const [audioEl, setAudioEl] = useState<HTMLAudioElement | null>(null);
  const [audioPlaying, setAudioPlaying] = useState(false);

  const cancelSpeech = useCallback(() => {
    if (typeof window !== "undefined" && window.speechSynthesis) {
      window.speechSynthesis.cancel();
    }
  }, []);
  useEffect(() => cancelSpeech, [cancelSpeech]);

  // Auto-start: fetch a random listening passage with questions
  async function autoStart() {
    setStage("loading");
    setBusy(true);
    try {
      const started = await listeningApi.random();
      markAttempted("listening", started.passage_id);
      setSession(started);
      setQuestions([]);
      setAnswers({});
      setPlaysUsed(0);
      setResult(null);
      setExamMode(true);
      setStage("listen");
    } catch (err) {
      setProblem(err instanceof ApiError ? err.detail : "No listening passages with questions available yet.");
      toast("error", err instanceof ApiError ? err.detail : "No passages available");
      setStage("intro");
    } finally {
      setBusy(false);
    }
  }

  async function play() {
    if (!session || playing) return;
    setPlaying(true);
    setPlaysUsed((n) => n + 1);
    if (session.audio_key) {
      const url = `${API_BASE.replace('/api/v1', '')}/media/${session.audio_key}`;
      const audio = new Audio(url);
      setAudioEl(audio);
      audio.onended = () => { setPlaying(false); setAudioPlaying(false); setAudioEl(null); };
      audio.onerror = () => { setPlaying(false); setAudioPlaying(false); setAudioEl(null); };
      audio.play().then(() => setAudioPlaying(true)).catch(() => setPlaying(false));
    } else {
      await speak(session.transcript, session.accent);
      setPlaying(false);
    }
  }

  function stopAudio() {
    if (audioEl) {
      audioEl.pause();
      audioEl.currentTime = 0;
      setAudioPlaying(false);
      setPlaying(false);
      setAudioEl(null);
    } else {
      if (typeof window !== "undefined" && window.speechSynthesis) {
        window.speechSynthesis.cancel();
      }
      setPlaying(false);
    }
  }

  async function toQuestions() {
    if (!session) return;
    cancelSpeech();
    setBusy(true);
    try {
      setQuestions(await listeningApi.questions(session.attempt_id));
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
      setResult(await listeningApi.submit(session.attempt_id, {
        answers: questions.map((q) => ({
          item_id: q.id, selected_index: answers[q.id] ?? null,
        })),
        plays_used: Math.max(1, playsUsed),
      }));
      toast("success", "Answers submitted successfully");
      proctoring.stopCamera();
      setExamMode(false);
      cancelSpeech();
      setStage("marked");
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : "Could not submit";
      setProblem(msg);
      toast("error", msg);
    } finally {
      setBusy(false);
    }
  }

  function backToList() {
    cancelSpeech();
    setStage("browse");
    setSession(null);
    setResult(null);
  }

  function begin(passage: any) {
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
    return <LevelSelect skill="listening" onSelect={(level) => { setDifficulty(level); setStage("select"); }} />;
  }

  if (stage === "select") {
    return <FullscreenPrompt onStart={autoStart} />;
  }

  if (stage === "loading") {
    return (
      <>
        <PageHeader title="Listening" sub="Loading passage…" />
        <div className="ds-card p-8 flex items-center justify-center gap-3">
          <Loader2 size={18} className="animate-spin text-muted" />
          <span className="text-xs text-muted">Selecting a random passage…</span>
        </div>
      </>
    );
  }

  // ---------------------------------------------------------------- listen --
  if (stage === "listen" && session) {
    const playsLeft = session.plays_allowed - playsUsed;
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
          sub={`${KIND_LABEL[session.kind] ?? session.kind} · ${session.question_count} questions after the audio`}
        />
        <Section>
          <div className="text-center py-6">
            {session.audio_key ? (
              <span className="rounded-full p-4 inline-flex mb-4"
                    style={{ background: "color-mix(in srgb, var(--primary) 12%, transparent)" }}>
                <Ear size={28} style={{ color: "var(--primary)" }} />
              </span>
            ) : (
              <AiNarrator speaking={playing} />
            )}
            <p className="text-xs text-muted max-w-md mx-auto leading-relaxed mb-1">
              You will hear this {playsLeft === session.plays_allowed ? "once" : "again"}.
              The questions come afterwards — listen for what it is about, not just for names and numbers.
            </p>
            <p className="text-[11px] text-muted max-w-md mx-auto leading-relaxed mb-5">
              {session.audio_key
                ? "Recorded by a person."
                : "Read by your device's built-in voice."}
            </p>

            <div className="flex gap-2 justify-center">
              <button onClick={play} disabled={playing || playsUsed >= session.plays_allowed}
                      className="btn btn-primary ds-focus">
                {playsUsed === 0 ? <><Play size={15} /> Play the passage</>
                         : <><RotateCcw size={15} /> Play again</>}
              </button>
              {playing && (
                <button onClick={stopAudio}
                        className="btn btn-ghost ds-focus flex items-center gap-1">
                  <Square size={13} /> Stop
                </button>
              )}
            </div>

            <div className="text-[11px] text-muted mt-3">
              {playsUsed === 0
                ? `${session.plays_allowed} play${session.plays_allowed > 1 ? "s" : ""} allowed`
                : playsLeft > 0
                  ? `${playsLeft} play${playsLeft > 1 ? "s" : ""} left`
                  : "No plays left"}
            </div>

            {!session.audio_key && playsUsed === 0 && (
              <div className="mt-4">
                <VoicePicker accent={session.accent} />
              </div>
            )}

            {playsUsed > 0 && !playing && (
              <div className="mt-6">
                <button onClick={toQuestions} disabled={busy}
                        className="btn btn-primary ds-focus">
                  I have listened — show the questions
                </button>
                <p className="text-[10px] text-muted mt-2">
                  You cannot come back to the audio after this.
                </p>
              </div>
            )}
          </div>
        </Section>
        {problem && <div className="mt-4"><ErrorNote message={problem} /></div>}
      </FullscreenGuard>
    );
  }

  // ---------------------------------------------------------------- answer --
  if (stage === "answer" && session) {
    const answered = questions.filter((q) => answers[q.id] != null).length;
    const questionStatuses: ExamQuestionStatus[] = questions.map((q, i) => ({
      id: q.id, index: i + 1, answered: answers[q.id] != null, selectedOption: answers[q.id] ?? null,
    }));
    return (
      <ExamSidebar
        questions={questionStatuses}
        currentIndex={questions.findIndex(q => answers[q.id] == null) ?? 0}
        totalQuestions={questions.length}
        sectionTitle="Listening Comprehension"
        companyLabel={session.kind && !['general', 'announcement', 'instruction', 'talk', 'voicemail', 'conversation'].includes(session.kind) ? `${session.kind} Round` : "General"}
        onEndExam={() => {
          if (confirm("Are you sure you want to end this practice?")) {
            void submit();
          }
        }}
        onNavigate={() => {}}
      >
        <CameraPreview
          videoRef={proctoring.videoRef}
          faceCount={proctoring.state.faceCount}
          strikes={proctoring.state.strikes}
          isFocused={proctoring.state.isFocused}
        />
        <PageHeader title={session.title}
                    sub="Choose one answer for each question, then submit." />
        <div className="ds-card p-3 mb-4 flex items-center gap-3">
          <div className="flex gap-1.5">
            {questions.map((q) => (
              <span key={q.id} className="rounded-full" style={{
                width: 9, height: 9,
                background: answers[q.id] != null ? "var(--primary)" : "var(--surface-2)",
                border: answers[q.id] != null ? "none" : "1.5px solid var(--border)",
              }} />
            ))}
          </div>
          <span className="text-xs font-semibold">
            {answered} of {questions.length} answered
          </span>
        </div>

        <div className="space-y-3">
          {questions.map((q, n) => {
            const done = answers[q.id] != null;
            return (
              <Section key={q.id}>
                <div className="flex items-start gap-2 mb-3">
                  <span className="shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-[11px] font-bold mt-0.5"
                        style={done ? { background: "var(--primary)", color: "var(--on-primary, #fff)" }
                                    : { background: "var(--surface-2)", color: "var(--muted)" }}>
                    {done ? <Check size={12} /> : n + 1}
                  </span>
                  <div className="text-sm font-semibold">{q.stem}</div>
                </div>
                <div className="space-y-2">
                  {q.options.map((opt, i) => (
                    <ChoiceOption key={i} label={opt} index={i}
                                  selected={answers[q.id] === i}
                                  onSelect={() => setAnswers((a) => ({ ...a, [q.id]: i }))} />
                  ))}
                </div>
              </Section>
            );
          })}
        </div>
        {problem && <div className="mt-4"><ErrorNote message={problem} /></div>}
        <button onClick={submit} disabled={busy || answered === 0}
                className="btn btn-primary w-full ds-focus mt-4">
          {busy ? "Marking…"
                : answered < questions.length
                  ? `Submit — ${questions.length - answered} still unanswered`
                  : "Submit answers"}
        </button>
      </ExamSidebar>
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
            <button onClick={autoStart} className="btn btn-primary btn-sm ds-focus">
              Another passage
            </button>
          }
        />

        <div className="grid sm:grid-cols-3 gap-3 mb-4">
          <div className="ds-card p-4">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-muted">
              Listening score
            </div>
            <div className="text-2xl font-bold mt-2" style={{ color: "var(--primary)" }}>
              {result.score}
            </div>
            <div className="text-[11px] text-muted mt-1">
              out of 100 · {result.band}
            </div>
          </div>
          <div className="ds-card p-4 sm:col-span-2 flex items-center gap-4 flex-wrap">
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
        </div>

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
                        {" · "}Answer: {row.options[row.correct_index]}
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

        <Section title="What was said">
          <p className="text-xs text-muted leading-relaxed whitespace-pre-line">
            {result.transcript}
          </p>
        </Section>

        {/* Review & Rating Card */}
        <ReviewCard attemptId={session?.attempt_id} label="listening" onNext={autoStart} onBack={() => { proctoring.stopCamera(); setStage("intro"); }} nextLabel="Another passage →" />
      </>
    );
  }

  return null;
}


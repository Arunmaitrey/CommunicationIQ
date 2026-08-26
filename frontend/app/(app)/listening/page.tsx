"use client";
import { useCallback, useEffect, useState } from "react";
import {
  Check, Ear, Flame, Play, RotateCcw, Volume2, X, Zap,
} from "lucide-react";
import { AiNarrator } from "@/components/brand/AiNarrator";
import { VoicePicker } from "@/components/VoicePicker";
import { RequireAuth } from "@/components/RequireAuth";
import { StepGuide } from "@/components/StepGuide";
import { ChoiceOption,
  Badge, EmptyState, ErrorNote, GapMeter, PageHeader, Section, Skeleton,
} from "@/components/ui";
import { speak } from "@/lib/audio";
import {
  ApiError, listeningApi,
  type ListeningPassageRow, type ListeningQuestion,
  type ListeningResult, type ListeningStart,
} from "@/lib/api";
import { useData } from "@/lib/useData";

export default function ListeningPage() {
  return (
    <RequireAuth roles={["student"]}>
      <Listening />
    </RequireAuth>
  );
}

type Stage = "browse" | "listen" | "answer" | "marked";

const KIND_LABEL: Record<string, string> = {
  announcement: "Announcement",
  instructions: "Instructions",
  short_talk: "Short talk",
  conversation: "Conversation",
  voicemail: "Voicemail",
};

/** Listening practice.
 *
 *  The order is the design: audio first, questions afterwards. Showing the
 *  questions during playback would let a student listen for four specific
 *  facts instead of following the passage, which measures scanning rather
 *  than comprehension — and it is not what any real round does.
 */
function Listening() {
  const { data, loading, error, reload } = useData(() => listeningApi.passages());

  const [stage, setStage] = useState<Stage>("browse");
  const [session, setSession] = useState<ListeningStart | null>(null);
  const [questions, setQuestions] = useState<ListeningQuestion[]>([]);
  const [answers, setAnswers] = useState<Record<string, number | null>>({});
  const [playsUsed, setPlaysUsed] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [result, setResult] = useState<ListeningResult | null>(null);
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);

  // Speech synthesis keeps talking after a route change unless it is stopped.
  const cancelSpeech = useCallback(() => {
    if (typeof window !== "undefined" && window.speechSynthesis) {
      window.speechSynthesis.cancel();
    }
  }, []);
  useEffect(() => cancelSpeech, [cancelSpeech]);

  async function begin(passage: ListeningPassageRow) {
    setProblem("");
    setBusy(true);
    try {
      const started = await listeningApi.start(passage.id);
      setSession(started);
      setQuestions([]);
      setAnswers({});
      setPlaysUsed(0);
      setResult(null);
      setStage("listen");
    } catch (err) {
      setProblem(err instanceof ApiError ? err.detail : "Could not start that passage");
    } finally {
      setBusy(false);
    }
  }

  async function play() {
    if (!session || playing) return;
    setPlaying(true);
    setPlaysUsed((n) => n + 1);
    await speak(session.transcript, session.accent);
    setPlaying(false);
  }

  async function toQuestions() {
    if (!session) return;
    cancelSpeech();
    setBusy(true);
    try {
      setQuestions(await listeningApi.questions(session.attempt_id));
      setStage("answer");
    } catch (err) {
      setProblem(err instanceof ApiError ? err.detail : "Could not load the questions");
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
      setStage("marked");
      reload();
    } catch (err) {
      setProblem(err instanceof ApiError ? err.detail : "Could not submit");
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

  if (loading) return <Skeleton rows={5} />;
  if (error) return <ErrorNote message={error} />;

  // ---------------------------------------------------------------- listen --
  if (stage === "listen" && session) {
    const playsLeft = session.plays_allowed - playsUsed;
    return (
      <>
        <PageHeader
          title={session.title}
          sub={`${KIND_LABEL[session.kind] ?? session.kind} · ${session.question_count} questions after the audio`}
        />
        <Section>
          <div className="text-center py-6">
            {/* The AI presenter reading the passage. It comes alive while the
                audio plays and rests between plays. Only shown as the narrator
                for a device-read passage; a real recording gets the ear. */}
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
              The questions come afterwards — listen for what it is about, not
              just for names and numbers.
            </p>
            <p className="text-[11px] text-muted max-w-md mx-auto leading-relaxed mb-5">
              {session.audio_key
                ? "Recorded by a person."
                : "Read by your device's built-in voice. That is a stand-in: synthesised speech is clearer and more even than a real speaker, so this is easier than the real thing."}
            </p>

            <button onClick={play} disabled={playing || playsUsed >= session.plays_allowed}
                    className="btn btn-primary ds-focus">
              {playing ? <><Volume2 size={15} /> Playing…</>
                       : playsUsed === 0 ? <><Play size={15} /> Play the passage</>
                       : <><RotateCcw size={15} /> Play again</>}
            </button>

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
        <button onClick={backToList} className="btn btn-ghost btn-sm ds-focus mt-4">
          Leave this passage
        </button>
      </>
    );
  }

  // ---------------------------------------------------------------- answer --
  if (stage === "answer" && session) {
    const answered = questions.filter((q) => answers[q.id] != null).length;
    return (
      <>
        <PageHeader title={session.title}
                    sub="Choose one answer for each question, then submit." />

        {/* A clear progress line — a filled pip per answered question, so a
            student can see at a glance what is left before the submit button
            tells them. */}
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
            <button onClick={backToList} className="btn btn-primary btn-sm ds-focus">
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
              out of 80 · {result.band}
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
                        {row.selected_index != null
                          ? row.options[row.selected_index]
                          : "nothing"}
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

        {/* Released only now. Reading it before would have made this a reading
            test, which is why the server withholds it until submission. */}
        <Section title="What was said">
          <p className="text-xs text-muted leading-relaxed whitespace-pre-line">
            {result.transcript}
          </p>
        </Section>
      </>
    );
  }

  // ---------------------------------------------------------------- browse --
  return (
    <>
      <PageHeader
        title="Listening"
        sub="Hear a passage once, then answer questions about it — the way a placement round does it."
      />

      <StepGuide
        active={1}
        steps={[
          { label: "Pick a passage", detail: "Each one says what kind of audio it is." },
          { label: "Listen carefully", detail: "It plays a limited number of times — no pausing." },
          { label: "Answer the questions", detail: "They appear only after the audio ends." },
          { label: "See your marks", detail: "Every answer explained, right after you submit." },
        ]}
      />

      {problem && <div className="mb-4"><ErrorNote message={problem} /></div>}

      {!data || data.length === 0 ? (
        <EmptyState icon={Ear} title="No passages yet"
                    desc="The listening bank is empty for this institution." />
      ) : (
        <div className="grid md:grid-cols-2 gap-3">
          {data.map((p) => (
            <button key={p.id} onClick={() => begin(p)} disabled={busy}
                    className="ds-card p-4 text-left hover:bg-surface2 transition-colors ds-focus">
              <div className="flex items-start justify-between gap-2">
                <div className="text-sm font-bold">{p.title}</div>
                {p.best_score != null && (
                  <Badge tone="var(--rag-green)">best {p.best_score}</Badge>
                )}
              </div>
              <div className="text-[11px] text-muted mt-1">
                {KIND_LABEL[p.kind] ?? p.kind} · about {p.approx_seconds}s ·{" "}
                {p.question_count} questions ·{" "}
                {p.plays_allowed === 1 ? "one play" : `${p.plays_allowed} plays`}
              </div>
              {p.best_score != null && (
                <div className="mt-2.5"><GapMeter percent={((p.best_score - 20) / 60) * 100} /></div>
              )}
            </button>
          ))}
        </div>
      )}

      <Section title="What this measures, and what it does not" className="mt-4">
        <p className="text-xs text-muted leading-relaxed">
          Comprehension: following a passage and answering about what it meant,
          not which words appeared in it. Wrong options are drawn from the
          passage on purpose, so catching keywords without following the sense
          will not get you through.
        </p>
        <p className="text-xs text-muted leading-relaxed mt-2">
          The passages are read by your device&rsquo;s built-in voice rather than
          recorded by people. Synthesised speech is clearer, more evenly paced
          and has none of the accent variety or hesitation of a real speaker,
          so this is easier than the real thing. Treat a good score here as a
          floor, not a ceiling.
        </p>
      </Section>
    </>
  );
}

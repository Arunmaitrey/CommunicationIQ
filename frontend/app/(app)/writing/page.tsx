"use client";
import { useEffect, useRef, useState } from "react";
import { Flame, PenLine, Target, Zap } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { StepGuide } from "@/components/StepGuide";
import { useToast } from "@/components/Toast";
import {
  Badge, EmptyState, ErrorNote, GapMeter, PageHeader, Section, Skeleton,
} from "@/components/ui";
import {
  ApiError, writingApi,
  type WritingPromptRow, type WritingResult,
} from "@/lib/api";
import { useData } from "@/lib/useData";
import { FullscreenPrompt } from "@/components/FullscreenPrompt";
import { useProctoring } from "@/lib/proctoring";
import { CameraPreview } from "@/components/proctoring/CameraPreview";

export default function WritingPage() {
  return (
    <RequireAuth roles={["student"]}>
      <Writing />
    </RequireAuth>
  );
}

type Stage = "intro" | "browse" | "write" | "marked";

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
  const { data, loading, error, reload } = useData(() => writingApi.prompts());
  const proctoring = useProctoring();

  const [stage, setStage] = useState<Stage>("intro");
  const [prompt, setPrompt] = useState<WritingPromptRow | null>(null);
  const [text, setText] = useState("");
  const [result, setResult] = useState<WritingResult | null>(null);
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);
  const openedAt = useRef<number>(0);

  // Draft survives an accidental navigation. Losing four hundred words to a
  // stray back button would be the single most infuriating thing this screen
  // could do, and it costs one line to prevent.
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

  function begin(p: WritingPromptRow) {
    setPrompt(p);
    setText("");
    setResult(null);
    setProblem("");
    openedAt.current = Date.now();
    setStage("write");
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
      window.localStorage.removeItem(`writing-draft-${prompt.id}`);
      setStage("marked");
      reload();
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : "Could not submit";
      setProblem(msg);
      toast("error", msg);
    } finally {
      setBusy(false);
    }
  }

  // Auto-start with a random prompt after fullscreen prompt
  useEffect(() => {
    if (data && data.length > 0 && stage === "browse" && !prompt && !busy) {
      setBusy(true);
      const random = data[Math.floor(Math.random() * data.length)];
      begin(random);
    }
  }, [data, stage, prompt, busy]); // eslint-disable-line react-hooks/exhaustive-deps

  // Request camera when practice starts
  useEffect(() => {
    if (stage !== "intro" && !proctoring.state.cameraActive) {
      proctoring.requestCamera();
    }
  }, [stage]);

  if (stage === "intro") {
    return <FullscreenPrompt onStart={() => setStage("browse")} />;
  }

  if (loading) return <Skeleton rows={5} />;
  if (error) return <ErrorNote message={error} />;

  // ----------------------------------------------------------------- write --
  if (stage === "write" && prompt) {
    const short = words < prompt.min_words;
    return (
      <>
        <CameraPreview
          videoRef={proctoring.videoRef}
          faceCount={proctoring.state.faceCount}
          strikes={proctoring.state.strikes}
          isFocused={proctoring.state.isFocused}
        />
        <PageHeader
          title={prompt.title}
          sub={`${KIND_LABEL[prompt.kind] ?? prompt.kind} · about ${prompt.suggested_minutes} minutes · at least ${prompt.min_words} words`}
        />

        <Section title="The situation" className="mb-3">
          <p className="text-xs leading-relaxed">{prompt.scenario}</p>
          <p className="text-sm font-semibold mt-3">{prompt.prompt}</p>
        </Section>

        {/* The rubric is shown, not hidden. This is practice: a student who
            knows what a competent answer has to cover learns more than one
            guessing at it. The points say what to address, never what to
            say — the words have to be theirs. */}
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
          <button onClick={() => setStage("browse")}
                  className="btn btn-ghost ds-focus">Back</button>
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
            <button onClick={() => setStage("browse")}
                    className="btn btn-primary btn-sm ds-focus">
              Another task
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
                {m.confidence > 0 && <GapMeter percent={((m.score - 20) / 60) * 100} />}
                {/* Every number says what it counted, so an admin can
                    review it and see exactly why it came out this way. */}
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

        {/* Said plainly, under the numbers rather than buried in a footer.
            Four confident-looking scores would otherwise imply this can judge
            whether the writing is any good, which it cannot. */}
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
      </>
    );
  }

  // ---------------------------------------------------------------- browse --
  return (
    <>
      <PageHeader
        title="Writing"
        sub="Real workplace tasks — awkward emails, status reports, summaries. Scored on five measures."
      />

      <StepGuide
        active={1}
        steps={[
          { label: "Pick a task", detail: "Real workplace situations, one screen each." },
          { label: "Write your answer", detail: "Take your time — there is no clock on practice." },
          { label: "Submit it", detail: "Scored on five measures the moment you do." },
          { label: "Read the feedback", detail: "Each measure says exactly what it counted." },
        ]}
      />

      {!data || data.length === 0 ? (
        <EmptyState icon={PenLine} title="No prompts yet"
                    desc="The writing bank is empty for this institution." />
      ) : (
        <div className="grid md:grid-cols-2 gap-3">
          {data.map((p) => (
            <button key={p.id} onClick={() => begin(p)}
                    className="ds-card p-4 text-left hover:bg-surface2 transition-colors ds-focus">
              <div className="flex items-start justify-between gap-2">
                <div className="text-sm font-bold">{p.title}</div>
                {p.best_score != null && (
                  <Badge tone="var(--rag-green)">best {p.best_score}</Badge>
                )}
              </div>
              <p className="text-[11px] text-muted mt-1 leading-relaxed line-clamp-2">
                {p.scenario}
              </p>
              <div className="text-[11px] text-muted mt-2">
                {KIND_LABEL[p.kind] ?? p.kind} · {p.min_words}+ words ·{" "}
                about {p.suggested_minutes} min
              </div>
            </button>
          ))}
        </div>
      )}

      <Section title="How this is scored, and what it cannot see" className="mt-4">
        <p className="text-xs text-muted leading-relaxed">
          Five measures: whether you covered what was asked, whether the piece
          holds together, how varied your language is, a set of common grammar
          errors, and mechanics — capitals, full stops, spacing. Each one says
          what it counted, so you can disagree with it.
        </p>
        <p className="text-xs text-muted leading-relaxed mt-2">
          It is not a marker. It cannot tell whether your argument is sound,
          whether what you wrote is true, or whether anyone would enjoy reading
          it. Those need a person, and this is designed to leave room for one
          rather than to replace them.
        </p>
      </Section>
    </>
  );
}

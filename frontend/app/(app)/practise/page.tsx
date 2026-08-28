"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowRight, BookOpen, Ear, Mic, PenLine, Target,
} from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { StepGuide } from "@/components/StepGuide";
import { ErrorNote, PageHeader, Section, Skeleton } from "@/components/ui";
import {
  api, ApiError, attemptApi, practiceApi,
  type SimulationProfile, type SkillModule,
} from "@/lib/api";
import { useData } from "@/lib/useData";

export default function PractisePage() {
  return (
    <RequireAuth roles={["student"]}>
      <Practise />
    </RequireAuth>
  );
}

const ICON: Record<string, typeof Mic> = {
  speaking: Mic, listening: Ear, reading: BookOpen, writing: PenLine,
};

/** Everything you can practise, in one place.
 *
 *  This replaces four separate destinations — Four skills, Drills, Quiz and
 *  part of Today — that a student had to choose between using words we
 *  invented. "Drill", "quiz" and "simulation" describe our data model, not
 *  anything a person recognises, and the menu was effectively asking someone
 *  to understand the schema before they could practise.
 *
 *  The screen answers one question: what should I do right now. It gives an
 *  answer at the top, and the four skills underneath for anyone who wants to
 *  choose for themselves.
 *
 *  Every tile carries its own Start. Speaking used to link to /simulate —
 *  the whole assessment library — which meant "practise speaking" landed a
 *  student on a screen full of tests they never asked for. Now Start on the
 *  Speaking tile picks the right session itself and goes straight into the
 *  mic check; the other three go straight to their own practice screens.
 */
function Practise() {
  const router = useRouter();
  const home = useData(() => api.studentHome());
  const skills = useData(() => practiceApi.skills());
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState("");

  if (home.loading || skills.loading) return <Skeleton rows={6} />;
  if (home.error) return <ErrorNote message={home.error} />;
  if (skills.error) return <ErrorNote message={skills.error} />;

  const quest = home.data?.quest;
  const weakest = home.data?.mastery?.[0];
  const modules = skills.data?.modules ?? [];
  const consented = home.data?.consent_given ?? false;

  /** Start a speaking session without a detour through the library.
   *
   *  Picks for the student: the baseline first if they have not done it
   *  (everything else is measured against it), otherwise the shortest
   *  published practice test. A student who wants a specific one can still
   *  choose it on Take a test — this button is for "just let me practise".
   */
  async function startSpeaking() {
    if (starting) return;
    if (!consented) {
      // Consent is the actual first step, so go there rather than fail here.
      router.push("/consent");
      return;
    }
    setStarting(true);
    setStartError("");
    try {
      const profiles = await api.studentProfiles();
      const pick = pickSpeakingProfile(profiles.filter((x) => x.style !== "drill"), home.data?.baseline_done ?? false);
      if (!pick) {
        setStartError("No speaking session is published yet. Ask your institution admin.");
        setStarting(false);
        return;
      }
      const attempt = await attemptApi.start(pick.id, "practice");
      router.push(`/attempt/${attempt.attempt_id}/run`);
    } catch (err) {
      setStartError(err instanceof ApiError ? err.detail : "Could not start the session");
      setStarting(false);
    }
  }

  // Where "just tell me what to do" sends you. The daily goal if there is an
  // unfinished one, otherwise the weakest skill, otherwise speaking.
  const suggestion = pickSuggestion(quest?.completed ?? false, weakest?.skill, modules);
  const suggestionIsSpeaking = suggestion.href === "/simulate";

  const suggestionInner = (
    <div className="flex items-center gap-4">
      <span className="rounded-full p-3 shrink-0"
            style={{ background: "color-mix(in srgb, var(--primary) 14%, transparent)" }}>
        <suggestion.icon size={20} style={{ color: "var(--primary)" }} />
      </span>
      <div className="flex-1 min-w-0 text-left">
        <div className="text-[11px] font-bold uppercase tracking-wider"
             style={{ color: "var(--primary)" }}>
          Start here
        </div>
        <div className="text-base font-bold mt-0.5">
          {starting && suggestionIsSpeaking ? "Starting…" : suggestion.title}
        </div>
        <p className="text-xs text-muted mt-1 leading-relaxed">
          {suggestion.why}
        </p>
      </div>
      <span className="btn btn-primary btn-sm ds-focus shrink-0 pointer-events-none">
        Start <ArrowRight size={13} />
      </span>
    </div>
  );

  return (
    <>
      <PageHeader
        title="Practise"
        sub="Short sessions. Ten minutes counts."
      />

      <StepGuide
        active={1}
        steps={[
          { label: "Pick a skill", detail: "Or take the suggestion below — it already points at what pays off most." },
          { label: "Press Start", detail: "Speaking runs a quick mic check first. The rest begin straight away." },
          { label: "Practise for ten minutes", detail: "Short sessions, most days. This is where the score moves." },
          { label: "See what moved", detail: "My progress shows every session and what it changed." },
        ]}
      />

      {startError && <div className="mb-4"><ErrorNote message={startError} /></div>}

      {/* One primary action. A student who reads nothing else on this page
          should still end up doing the right thing. */}
      {suggestionIsSpeaking ? (
        <button onClick={() => void startSpeaking()} disabled={starting}
                className="ds-card p-5 mb-4 block w-full hover:bg-surface2 transition-colors ds-focus"
                style={{ borderColor: "var(--primary)", cursor: "pointer" }}>
          {suggestionInner}
        </button>
      ) : (
        <Link href={suggestion.href}
              className="ds-card p-5 mb-4 block hover:bg-surface2 transition-colors ds-focus"
              style={{ borderColor: "var(--primary)" }}>
          {suggestionInner}
        </Link>
      )}

      <Section title="Or pick a skill">
        <div className="grid sm:grid-cols-2 gap-3">
          {modules.map((m) => (
            <SkillTile key={m.key} module={m}
                       starting={starting}
                       onStartSpeaking={() => void startSpeaking()} />
          ))}
        </div>
      </Section>

      {/* Named in plain words; the old "Drills" destination is gone --
          practice now starts from results ("What to practise next") or the
          suggestion above, both of which launch things that actually run. */}
      <Section title="Quick extras" className="mt-4">
        <div className="grid sm:grid-cols-2 gap-3">
          <Link href="/quiz"
                className="ds-card p-3 hover:bg-surface2 transition-colors ds-focus">
            <div className="flex items-center justify-between gap-2">
              <div className="text-sm font-semibold">Grammar &amp; vocabulary</div>
              <span className="text-[11px] font-bold ds-focus flex items-center gap-1"
                    style={{ color: "var(--primary)" }}>
                Start <ArrowRight size={11} />
              </span>
            </div>
            <p className="text-[11px] text-muted mt-0.5 leading-relaxed">
              Multiple-choice questions. No microphone needed.
            </p>
          </Link>
        </div>
      </Section>
    </>
  );
}

/** Which speaking test "just start" means.
 *
 *  Baseline first when it is still owed, because every later number is
 *  measured against it. After that, the shortest non-company practice test:
 *  practice is meant to fit in ten spare minutes, and a company round is
 *  something you sit deliberately, not something a quick-start should pick
 *  for you.
 */
function pickSpeakingProfile(profiles: SimulationProfile[],
                             baselineDone: boolean): SimulationProfile | undefined {
  if (!baselineDone) {
    const b = profiles.find((p) => p.is_baseline);
    if (b) return b;
  }
  const practice = profiles.filter((p) => !p.is_baseline && !p.company);
  const pool = practice.length > 0 ? practice : profiles;
  return [...pool].sort((a, b) => a.estimated_minutes - b.estimated_minutes)[0];
}

function SkillTile({ module: m, starting, onStartSpeaking }: {
  module: SkillModule; starting: boolean; onStartSpeaking: () => void;
}) {
  const Icon = ICON[m.key] ?? Mic;
  const ready = m.status === "live";
  const direct = m.key === "speaking";

  const body = (
    <>
      <div className="flex items-center gap-2.5">
        <Icon size={16} style={{ color: ready ? "var(--primary)" : "var(--muted)" }} />
        <span className="text-sm font-bold">{m.label}</span>
        {!ready && (
          <span className="text-[10px] text-muted ml-auto">not ready yet</span>
        )}
      </div>
      <p className="text-[11px] text-muted mt-1.5 leading-relaxed">{m.summary}</p>
    </>
  );

  if (!m.href) return <div className="ds-card p-3 opacity-70">{body}</div>;

  // Speaking starts its session right here — no trip through the assessment
  // library. The other three link to their own practice screens, where the
  // first thing on screen is the thing to do.
  if (direct) {
    return (
      <div className="ds-card p-3 flex flex-col">
        {body}
        <div className="flex items-center justify-between gap-2 mt-2.5 pt-2.5 border-t border-border">
          <span className="text-[10px] text-muted">Quick mic check, then you speak.</span>
          <button className="btn btn-primary btn-sm ds-focus shrink-0"
                  disabled={starting} onClick={onStartSpeaking}>
            {starting ? "Starting…" : "Start"}
          </button>
        </div>
      </div>
    );
  }

  return (
    <Link href={m.href}
          className="ds-card p-3 hover:bg-surface2 transition-colors ds-focus flex flex-col">
      {body}
      <div className="flex items-center justify-between gap-2 mt-2.5 pt-2.5 border-t border-border">
        <span className="text-[10px] text-muted">Begins straight away.</span>
        <span className="btn btn-primary btn-sm shrink-0 pointer-events-none">
          Start <ArrowRight size={13} />
        </span>
      </div>
    </Link>
  );
}

/** What to do next, in one decision.
 *
 *  Deliberately simple and deliberately explained on screen. A suggestion a
 *  student cannot see the reason for is indistinguishable from a random pick,
 *  and they stop trusting it.
 */
function pickSuggestion(questDone: boolean, weakestSkill: string | undefined,
                        modules: SkillModule[]) {
  const live = modules.filter((m) => m.status === "live" && m.href);

  if (!questDone) {
    return {
      title: "Today's goal",
      why: "Finishing it counts today towards your streak. About ten minutes.",
      href: "/simulate",
      icon: Target,
    };
  }

  // Weakest skill, if we have one and it is practisable.
  const bySkill: Record<string, string> = {
    pronunciation: "speaking", fluency: "speaking", response_latency: "speaking",
    listening: "listening", vocabulary: "reading", grammar: "writing",
    content_recall: "speaking",
  };
  const target = weakestSkill ? bySkill[weakestSkill] : undefined;
  const match = live.find((m) => m.key === target);
  if (match) {
    return {
      title: match.label,
      why: "This is your weakest area right now, so it is where practice pays off most.",
      href: match.href,
      icon: ICON[match.key] ?? Mic,
    };
  }

  const first = live[0];
  return {
    title: first ? first.label : "Speaking",
    why: "Today's goal is done. Keep going if you have ten minutes.",
    href: first ? first.href : "/simulate",
    icon: first ? (ICON[first.key] ?? Mic) : Mic,
  };
}

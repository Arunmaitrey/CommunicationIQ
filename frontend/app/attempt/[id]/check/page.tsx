"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  AlertTriangle, ArrowRight, CheckCircle2, Headphones, Mic, Volume2,
} from "lucide-react";
import { PoweredBy } from "@/components/brand/PoweredBy";
import { RequireAuth } from "@/components/RequireAuth";
import { SITTING_ROLES } from "@/lib/nav";
import { attemptApi, ApiError, type Capability } from "@/lib/api";
import {
  levelToFraction, MicPermissionError, MicRecorder, beep, speak,
} from "@/lib/audio";

export default function CheckPage() {
  return (
    <RequireAuth roles={SITTING_ROLES}>
      <EnvironmentCheck />
    </RequireAuth>
  );
}

type Stage = "intro" | "mic" | "ambient" | "playback" | "ready" | "blocked";

/** The pre-test check (SIM-04).
 *
 *  Real tests run one, and so does this — but it earns its place twice over:
 *  it stops an attempt being wasted on a dead microphone, and the ambient
 *  reading it takes is the evidence that later lets the report say "the room
 *  cost you points, not your English" (DIAG-07) only when that is true.
 */
function EnvironmentCheck() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();

  const [stage, setStage] = useState<Stage>("intro");
  const [level, setLevel] = useState(-90);
  const [peak, setPeak] = useState(-90);
  const [noise, setNoise] = useState<number | null>(null);
  const [noiseCeiling, setNoiseCeiling] = useState<number | null>(null);
  const [headphones, setHeadphones] = useState(false);
  const [playbackOk, setPlaybackOk] = useState(false);
  const [error, setError] = useState("");
  const [warning, setWarning] = useState("");
  const [busy, setBusy] = useState(false);

  const recorder = useRef<MicRecorder | null>(null);
  const [capability, setCapability] = useState<Capability | null>(null);

  useEffect(() => () => recorder.current?.close(), []);

  // What this server can measure, asked before the test rather than after.
  // A student who gives twenty minutes to a simulation should be told up
  // front that pronunciation cannot be scored here -- finding four blanks on
  // the results page instead reads as a broken product, and wastes the
  // twenty minutes either way. Failure is silent on purpose: if the check
  // cannot be made, the test still starts.
  useEffect(() => {
    let live = true;
    attemptApi.capability()
      .then((c) => { if (live) setCapability(c); })
      .catch(() => {});
    return () => { live = false; };
  }, []);

  // Escape closes a dialog by convention. Not this one -- there is nothing
  // behind it to go back to, and dismissing it mid-check leaves an attempt
  // half-started.
  useEffect(() => {
    const swallow = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
      }
    };
    window.addEventListener("keydown", swallow, true);
    return () => window.removeEventListener("keydown", swallow, true);
  }, []);

  const openMic = useCallback(async () => {
    setError("");
    try {
      recorder.current = await MicRecorder.open({
        onLevel: (dbfs) => {
          setLevel(dbfs);
          setPeak((p) => Math.max(p, dbfs));
        },
      });
      setStage("mic");
    } catch (err) {
      setStage("blocked");
      setError(err instanceof MicPermissionError
        ? "Your browser blocked the microphone. Allow it in the address bar, then try again."
        : "No microphone was found. Plug one in or switch device, then try again.");
    }
  }, []);

  const measureRoom = useCallback(async () => {
    if (!recorder.current) return;
    setStage("ambient");
    const reading = await recorder.current.measureAmbient(2000);
    setNoise(reading.noiseDbfs);
    setNoiseCeiling(reading.noiseCeilingDbfs);
    setStage("playback");
  }, []);

  const testPlayback = useCallback(async () => {
    await beep();
    await speak("If you can hear this clearly, your audio is working.");
    setPlaybackOk(true);
    setStage("ready");
  }, []);

  async function begin() {
    setBusy(true);
    try {
      const res = await attemptApi.envCheck(id, {
        mic_ok: peak > -55,
        playback_ok: playbackOk,
        headphones,
        noise_dbfs: noise,
        noise_ceiling_dbfs: noiseCeiling,
        input_peak_dbfs: peak,
        device_label: recorder.current?.deviceLabel ?? "",
        user_agent: navigator.userAgent,
        diagnostics: recorder.current?.diagnostics() ?? {},
      });
      if (res.warning) {
        setWarning(res.warning);
        setBusy(false);
        return;
      }
      proceed();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not start the attempt");
      setBusy(false);
    }
  }

  /** The only exit. Closes the microphone before leaving, because an
   *  AudioContext surviving a route change is how you end up with two. */
  function quit() {
    recorder.current?.close();
    recorder.current = null;
    router.push("/simulate");
  }

  function proceed() {
    // The recorder is closed here and reopened by the runner: carrying a live
    // AudioContext across a route change is how you end up with two of them.
    recorder.current?.close();
    recorder.current = null;
    router.replace(`/attempt/${id}/run`);
  }

  const heard = peak > -55;
  const quiet = noise != null && noise <= -45;

  return (
    <div className="modal-page">
      {/* Strictly modal. No click-outside, no Escape, no back button: the
          check is the last chance to catch a dead microphone before it costs
          an attempt, and a tester who can dismiss it by tapping slightly off
          target will dismiss it. Quit is the one way out, and it says so. */}
      <div className="modal-scrim" role="presentation"
           onMouseDown={(e) => e.preventDefault()}>
        <div className="modal-panel" role="dialog" aria-modal="true"
             aria-labelledby="check-title"
             onMouseDown={(e) => e.stopPropagation()}>
          <div className="text-left">
          <div className="text-[11px] font-bold uppercase tracking-wider text-muted mb-1">
            Before you start
          </div>
          <h1 id="check-title" className="text-xl font-bold mb-1">Check your setup</h1>
          <p className="text-xs text-muted mb-6 leading-relaxed">
            The same check a real test runs. It takes about thirty seconds, and it
            means a bad microphone cannot quietly cost you a score.
          </p>

          {/* Checked before the tester presses anything. On a phone reaching a
              laptop by IP this is the failure, and it is not a product bug. */}
          {typeof window !== "undefined" && !window.isSecureContext && (
            <div className="ds-card p-3 mb-4 text-xs flex items-start gap-2"
                 style={{ borderColor: "var(--rag-red)" }}>
              <AlertTriangle size={14} className="shrink-0 mt-0.5"
                             style={{ color: "var(--rag-red)" }} />
              <span>
                This page is not on a secure connection. Browsers only offer the
                microphone over HTTPS or on localhost, so the check below will
                fail here whatever your device does.
              </span>
            </div>
          )}

          <div className="space-y-2 mb-6">
            <Step done={stage !== "intro" && stage !== "blocked"} icon={Mic}
                  title="Microphone" note={
                    stage === "blocked" ? "blocked" :
                    stage === "intro" ? "not checked yet" :
                    heard ? "hearing you clearly" : "speak up — nothing is reaching us yet"
                  } />
            <Step done={noise != null} icon={Volume2} title="Background noise"
                  note={noise == null ? "not measured yet"
                        : quiet ? `quiet enough (${noise} dBFS)`
                        : `noisy (${noise} dBFS)`} />
            <Step done={playbackOk} icon={Headphones} title="Playback"
                  note={playbackOk ? "you heard the test tone" : "not checked yet"} />
            {recorder.current && (
              <div className="text-[10px] text-muted pl-6 pt-1">
                {recorder.current.captureMode} · {recorder.current.sampleRate} Hz
                {recorder.current.deviceLabel && ` · ${recorder.current.deviceLabel}`}
              </div>
            )}
          </div>

          {capability && !capability.full_scoring && (
            <div className="ds-card p-3 mb-3 text-[11px] leading-relaxed"
                 style={{ borderColor: "var(--rag-amber)" }}>
              <div className="font-bold mb-1" style={{ color: "var(--rag-amber)" }}>
                Limited scoring on this server
              </div>
              <p className="text-muted">{capability.note}</p>
            </div>
          )}

          {stage === "intro" && (
            <button onClick={openMic} className="btn btn-primary w-full ds-focus">
              <Mic size={15} /> Allow microphone
            </button>
          )}

          {stage === "blocked" && (
            <div className="space-y-3">
              <div className="ds-card p-3 text-xs" style={{ borderColor: "var(--rag-red)" }}>
                {error}
              </div>
              <button onClick={openMic} className="btn btn-ghost w-full ds-focus">
                Try again
              </button>
            </div>
          )}

          {stage === "mic" && (
            <div className="space-y-4">
              <div className="ds-inset p-4">
                <div className="text-xs font-semibold mb-3">
                  Say your name and your branch out loud.
                </div>
                <LevelMeter level={level} />
                <div className="text-[11px] text-muted mt-2">
                  {heard ? "Good — that is a usable level."
                         : "Nothing yet. Check you are not muted, and speak normally."}
                </div>
              </div>
              <button onClick={measureRoom} disabled={!heard}
                      className="btn btn-primary w-full ds-focus">
                <ArrowRight size={15} /> Next: measure the room
              </button>
            </div>
          )}

          {stage === "ambient" && (
            <div className="ds-inset p-4 text-center">
              <div className="text-xs font-semibold mb-2">Listening to the room…</div>
              <p className="text-[11px] text-muted mb-3">Stay quiet for two seconds.</p>
              <LevelMeter level={level} />
            </div>
          )}

          {stage === "playback" && (
            <div className="space-y-4">
              {!quiet && (
                <div className="ds-card p-3 text-xs flex items-start gap-2"
                     style={{ borderColor: "var(--rag-amber)" }}>
                  <AlertTriangle size={14} className="shrink-0 mt-0.5"
                                 style={{ color: "var(--rag-amber)" }} />
                  <span>
                    It is noisy where you are. You can still take the test — the
                    report will separate the room from your English — but a
                    quieter spot gives a truer reading.
                  </span>
                </div>
              )}
              <button onClick={testPlayback} className="btn btn-primary w-full ds-focus">
                <Volume2 size={15} /> Play the test sound
              </button>
            </div>
          )}

          {stage === "ready" && (
            <div className="space-y-4">
              <label className="ds-inset p-3 flex items-center gap-3 cursor-pointer text-xs">
                <input type="checkbox" checked={headphones}
                       onChange={(e) => setHeadphones(e.target.checked)}
                       style={{ accentColor: "var(--primary)", width: 16, height: 16 }} />
                <span>I am wearing headphones</span>
              </label>

              <div className="ds-card p-3 text-[11px] text-muted leading-relaxed">
                Once you begin: prompts play once, timers do not pause, and you
                cannot go back to a question. That is deliberate — it is how the
                real test works.
              </div>

              {warning && (
                <div className="ds-card p-3 text-xs" style={{ borderColor: "var(--rag-amber)" }}>
                  {warning}
                  <button onClick={proceed} className="btn btn-primary btn-sm w-full mt-3 ds-focus">
                    Start anyway
                  </button>
                </div>
              )}

              {!warning && (
                <button onClick={begin} disabled={busy}
                        className="btn btn-primary w-full ds-focus">
                  {busy ? "Starting…" : "Start the simulation"}
                </button>
              )}

              {error && (
                <div className="text-xs" style={{ color: "var(--rag-red)" }}>{error}</div>
              )}
            </div>
          )}

            <button onClick={quit} className="modal-quit ds-focus">
              Quit and go back
            </button>

            <div className="mt-3 pt-3 flex justify-center"
                 style={{ borderTop: "1px solid var(--border)" }}>
              <PoweredBy />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Step({ done, icon: Icon, title, note }: {
  done: boolean; icon: typeof Mic; title: string; note: string;
}) {
  return (
    <div className="flex items-center gap-3 text-xs">
      {done
        ? <CheckCircle2 size={15} style={{ color: "var(--rag-green)" }} className="shrink-0" />
        : <Icon size={15} className="text-muted shrink-0" />}
      <span className="font-semibold w-32">{title}</span>
      <span className="text-muted flex-1">{note}</span>
    </div>
  );
}

/** Twenty bars, because a number is not something you can glance at while speaking. */
function LevelMeter({ level }: { level: number }) {
  const fraction = levelToFraction(level);
  const bars = 20;
  const lit = Math.round(fraction * bars);
  return (
    <div className="level-meter">
      {Array.from({ length: bars }).map((_, i) => (
        <span
          key={i}
          className="level-bar"
          style={{
            height: `${20 + (i / bars) * 80}%`,
            opacity: i < lit ? 1 : 0.15,
            background: i > bars * 0.85 ? "var(--rag-red)"
              : i > bars * 0.65 ? "var(--rag-amber)" : "var(--primary)",
          }}
        />
      ))}
    </div>
  );
}

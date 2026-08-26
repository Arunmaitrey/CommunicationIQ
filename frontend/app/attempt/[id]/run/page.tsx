"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Headphones, Loader2, Mic, Square } from "lucide-react";
import { AiNarrator } from "@/components/brand/AiNarrator";
import { RequireAuth } from "@/components/RequireAuth";
import { useRole } from "@/components/RoleProvider";
import { SITTING_ROLES } from "@/lib/nav";
import { answerLine, taskLabel, whatToExpect } from "@/lib/tasks";
import { usePresence } from "@/components/shell/usePresence";
import { ApiError, attemptApi, type RunnerItem, type RunnerPayload } from "@/lib/api";
import { deliverRecordingInBackground, drainPending, owedFor } from "@/lib/delivery";
import { DataUsageIndicator } from "@/components/DataUsageIndicator";
import { firstOpenIndex, nextStep } from "@/lib/sequence";
import { sectionBudget, sectionMood, sectionRemaining } from "@/lib/timing";
import { groupNumbering, remainingSeconds, sectionExpiry } from "@/lib/sectionClock";
import { FRESH, advanceReason, inspect, observe, shouldAdvance, speechFloorFor, windowFor, type TalkState } from "@/lib/speech";
import {
  beep, levelToFraction, MicPermissionError, MicRecorder, MicUnavailableError,
  playAudioUrl, primeSpeech, speak, TARGET_SAMPLE_RATE,
} from "@/lib/audio";

export default function RunPage() {
  return (
    <RequireAuth roles={SITTING_ROLES}>
      <Runner />
    </RequireAuth>
  );
}

type Phase =
  | "loading" | "section" | "prep" | "prompt" | "answer"
  // Manual gates (section flags): "armed" waits for Start Recording,
  // "listen" waits for Play Audio before a heard passage, "ack" waits for the
  // typed "Okay" after a clip (clip-level acknowledgement).
  | "armed" | "listen" | "ack"
  // Everything is answered but this browser is still holding a recording the
  // server has never seen. Submitting here would discard a real answer.
  | "owed"
  // `respond` is the non-speaking counterpart of `answer`: the runner is
  // waiting for a choice or a paragraph rather than for a countdown.
  | "respond"
  | "saving" | "submitting" | "failed";

/** How each format announces itself inside the runner.
 *
 *  Practising a specific test is only worth anything if it feels like that
 *  test while you are sitting it. Before this, every format collapsed into
 *  one identical screen the moment you started -- the choice on the
 *  simulations page changed the questions and nothing else, which is what
 *  makes the product feel thinner than it is.
 *
 *  The tint is the same value the theme uses for that family elsewhere, so a
 *  student who picked SVAR-style on the list sees the same colour carried
 *  into the test rather than arriving somewhere unrelated.
 */
const FORMAT: Record<string, { label: string; tint: string; sectionWord: string }> = {
  versant_style:  { label: "Versant-style",  tint: "var(--primary)",   sectionWord: "Part" },
  svar_style:     { label: "SVAR-style",     tint: "var(--secondary)", sectionWord: "Section" },
  speechx_style:  { label: "SpeechX-style",  tint: "var(--secondary)", sectionWord: "Section" },
  // sectionWord "Section", not "Round": every researched company assessment
  // labels its parts "Section A/B/C...", and the skinned banner prints this
  // word. "Round" described the whole sitting, not its parts.
  company_round:  { label: "Company round",  tint: "var(--accent)",    sectionWord: "Section" },
  diagnostic:     { label: "Diagnostic",     tint: "var(--primary)",   sectionWord: "Part" },
};

const DEFAULT_FORMAT = FORMAT.diagnostic;

/** The vendor-exact skins.
 *
 *  One assessment shell, four looks. The shell is the markup the SVAR rebuild
 *  introduced -- slim top bar, whole-test count, section banner, question bar,
 *  mic tile, recording circle, manual Start/Play gates. Which styles use that
 *  shell, and which palette each wears, is configuration; the recording
 *  engine, timers and one-shot guarantees never branch on it.
 *
 *  `theme` is a CSS class next to `.svar` in globals.css that retints the
 *  shared tokens. SVAR keeps the plain `.svar` class it always had.
 */
const SKIN: Record<string, { theme: string }> = {
  svar_style:    { theme: "svar" },
  company_round: { theme: "svar skin-ion" },     // TCS/Infosys/Wipro: iON blue
  speechx_style: { theme: "svar skin-mettl" },   // Mercer|Mettl dark navy/gold
  versant_style: { theme: "svar skin-versant" }, // Pearson teal/halftone
};

/** Which skin a run wears. Style decides the family; a company can override
 *  within it -- the researched Cognizant assessment is SVAR-shaped and navy,
 *  while its style stays company_round so the result presents as a round
 *  verdict rather than a vendor scale. */
function skinFor(style: string, company: string): { theme: string } | undefined {
  if (style === "company_round" && company === "Cognizant") return SKIN.svar_style;
  return SKIN[style];
}

/** The test itself.
 *
 *  Outside the app shell on purpose: no nav rail, no sign-out button, no way
 *  to wander off mid-answer. The three things that make this a simulation
 *  rather than a quiz — prompts that play once, timers that do not pause, and
 *  no going back — are all enforced by the server as well as by this screen,
 *  because a screen is only a suggestion.
 */
function Runner() {
  const { user } = useRole();
  const { id } = useParams<{ id: string }>();
  const router = useRouter();

  const [payload, setPayload] = useState<RunnerPayload | null>(null);
  const [index, setIndex] = useState(0);
  const [phase, setPhase] = useState<Phase>("loading");
  const [seconds, setSeconds] = useState(0);
  const [level, setLevel] = useState(-90);
  const [notice, setNotice] = useState("");
  const [rescheduling, setRescheduling] = useState(false);
  const [error, setError] = useState("");

  const recorder = useRef<MicRecorder | null>(null);
  // Answers in flight for the two non-speaking modes.
  const [choice, setChoice] = useState<number | null>(null);
  const [written, setWritten] = useState("");
  // Seconds a reconstruction passage has left on screen. Null means there is
  // nothing to take away, which is every other written task.
  const [stimulusLeft, setStimulusLeft] = useState<number | null>(null);
  // Set while an item is waiting for a typed or chosen answer; the Submit
  // button calls it, which unblocks runItem.
  const answerResolver = useRef<
    ((given: { index: number | null; text: string }) => void) | null>(null);
  // SVAR manual gates — resolved by the Start Recording / Play Audio buttons.
  const startResolver = useRef<(() => void) | null>(null);
  const playResolver = useRef<(() => void) | null>(null);
  const stopEarly = useRef(false);
  // Why the CURRENT recording stopped. Reset to "window_expired" as each
  // answer countdown starts (natural expiry and the sitting clock need no
  // handler); the finish buttons overwrite it with "user_ended" and the
  // silence advance with "auto_advance". Sent with the upload, because the
  // report may only say "ran out of time" when the window truly expired --
  // the audio alone cannot tell a timeout from a Stop pressed mid-sentence.
  const endReason = useRef("window_expired");
  const started = useRef(false);
  // Adaptive advancement reads this every ~20 ms from the level meter. A ref
  // rather than state: it changes fifty times a second and none of those
  // changes should re-render anything.
  const talk = useRef<TalkState>(FRESH);
  const listenFor = useRef<number>(0);
  // The trailing-silence window for the item being recorded — scripted items
  // advance briskly, composed speech gets thinking room. Set alongside
  // listenFor whenever recording arms; harmless before then (listenFor is 0,
  // so nothing can advance).
  const trailingFor = useRef<number>(3000);
  // A listening event is one passage then its questions. The server groups the
  // questions by `passage_ref` and orders them together; here we pick the one
  // item per passage that owns the playback -- the first to carry each ref.
  // Every other item in the group answers on what was already heard and never
  // plays the audio again, so the state machine (not a hidden button) enforces
  // "one play per passage": a 4-passage / 12-question section plays 4 times.
  const firstOfPassage = useMemo(() => {
    const seen = new Set<string>();
    const owners = new Set<string>();
    for (const it of payload?.items ?? []) {
      if (!it.passage_ref) continue;
      if (!seen.has(it.passage_ref)) {
        seen.add(it.passage_ref);
        owners.add(it.response_id);
      }
    }
    return owners;
  }, [payload]);
  // Recordings this browser is still holding. Submitting with a non-zero
  // count would throw away an answer the candidate gave.
  const [owed, setOwed] = useState(0);
  const [okayText, setOkayText] = useState("");
  const [uploadNote, setUploadNote] = useState("");
  // Seconds left in the whole sitting, or null before it has started. Counted
  // against the server's clock, not the device's.
  const [sittingLeft, setSittingLeft] = useState<number | null>(null);
  // Seconds spent in the current section. Advisory only -- see lib/timing.ts:
  // this clock warns and never ends an item, because the item timer already
  // bounds every recording and two authorities over one recording is how
  // answers get cut in half.
  const [sectionElapsed, setSectionElapsed] = useState(0);
  // Set once, when the sitting's clock reaches zero. A ref because `advance`
  // reads it after an await, where a state value would be the one captured
  // when the item started.
  const expired = useRef(false);
  // SVAR-style Speak on the Topic: the candidate chose to skip this topic.
  // Semantics are ours (the reference shows the button, not what it does):
  // the topic is passed over with no spoken response, and they are told.
  const skipTopic = useRef(false);
  // Clip-level "Okay" acknowledgement (Mettl D): resolved by the Next button
  // once the candidate has typed Okay.
  const ackResolver = useRef<(() => void) | null>(null);
  // Reloaded with every item already answered: nothing to run, submit.
  const resumeToSubmit = useRef(false);
  // A lettered section's budget ran out while this item was still waiting
  // at a gate (Play Audio / Start Recording / thinking). The item is passed
  // over without a response -- "section time is over" means over.
  const skipCurrent = useRef(false);
  // The room's speech floor, from the setup check (D1).
  const floor = useRef(speechFloorFor(null));
  // A carried message (topic skipped, section over) shown on the screens
  // that follow, until the candidate starts answering again.
  const [banner, setBanner] = useState("");
  // A lettered section's budget ran out. The item in progress finishes; the
  // rest of that section is passed over.
  const groupExpired = useRef(false);
  const [groupElapsed, setGroupElapsed] = useState(0);

  const item: RunnerItem | undefined = payload?.items[index];
  const total = payload?.items.length ?? 0;

  // Leaving mid-attempt loses the attempt. Say so, rather than letting a
  // stray back-swipe on a phone throw away twenty minutes.
  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => {
      if (phase === "loading" || phase === "submitting") return;
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [phase]);

  useEffect(() => () => recorder.current?.close(), []);

  /** Send anything this browser is still holding for this attempt. */
  const drainQueue = useCallback(async () => {
    const { owed: left } = await drainPending(
      id, (rid, blob, kind, endReason) => kind === "answer"
        ? attemptApi.answerStatus(id, rid, blob)
        : attemptApi.uploadAudioStatus(id, rid, blob, endReason));
    setOwed(left);
    return left;
  }, [id]);

  /** A reload found every item answered: drain what this browser still
   *  holds and submit, rather than replaying a finished test. */
  const finishResumed = useCallback(async () => {
    const stillOwed = await drainQueue();
    if (stillOwed > 0) {
      setUploadNote(
        `${stillOwed} of your answers ${stillOwed === 1 ? "has" : "have"} not `
        + `reached us. They are saved on this device. Try again, or finish `
        + `without them — they will not be scored if you do.`);
      setPhase("owed");
      return;
    }
    recorder.current?.close();
    recorder.current = null;
    try {
      await attemptApi.submit(id);
      router.replace(`/results/${id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Scoring failed.");
      setPhase("failed");
    }
  }, [drainQueue, id, router]);

  // Count the passage down while it is on screen. Stops at zero rather than
  // going negative, and clears itself if the candidate leaves the phase.
  useEffect(() => {
    if (phase !== "respond" || stimulusLeft === null || stimulusLeft <= 0) return;
    const timer = setTimeout(
      () => setStimulusLeft((left) => (left === null ? null : left - 1)), 1000);
    return () => clearTimeout(timer);
  }, [phase, stimulusLeft]);

  // Only while the candidate is actually answering. Watching during loading
  // would fire on the navigation that gets here, and during submitting the
  // work is already done -- interrupting someone who has finished and gone to
  // make tea would be nagging, not proctoring.
  const watching = (
    phase !== "loading" && phase !== "submitting" && phase !== "failed" && !error
  );
  const { away, events, resume } = usePresence(watching);

  // -- boot ---------------------------------------------------------------

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    (async () => {
      try {
        const data = await attemptApi.runner(id);
        if (!data.items.length) {
          setError("This simulation has no items configured.");
          setPhase("failed");
          return;
        }
        // The runner is never the place to discover a dead microphone. If the
        // check has not been done — or somebody deep-linked past it — go back
        // and do it, rather than starting a clock the student cannot answer.
        // A test with nothing spoken in it needs neither the environment
        // check nor the microphone. Demanding both would make a reading
        // comprehension paper refuse to start on a machine with no mic --
        // and would train candidates to click through a permission prompt
        // they did not need, which is how the prompt stops meaning anything.
        const needsMic = data.items.some((x) => x.response_mode === "speak");

        if (needsMic && !data.env_check_done) {
          router.replace(`/attempt/${id}/check`);
          return;
        }
        setPayload(data);
        floor.current = speechFloorFor(data.noise_dbfs, data.noise_ceiling_dbfs);
        console.debug("[runner] speech floor " + JSON.stringify({ noise: data.noise_dbfs,
          ceiling: data.noise_ceiling_dbfs, floorDbfs: floor.current }));
        // Resume where the server's record ends, not at item 1 (D7). With
        // everything already answered there is nothing left to run: go
        // straight to submission.
        const open = firstOpenIndex(data.items);
        if (open < 0) {
          resumeToSubmit.current = true;
        } else {
          setIndex(open);
        }
        if (needsMic) {
          recorder.current = await MicRecorder.open({ onLevel: (dbfs, frameMs) => {
            setLevel(dbfs);
            // Adaptive advancement. Armed only while an item is recording,
            // so nothing here can end a prep phase or a playback. `frameMs` is
            // the frame's REAL duration -- a fixed 20 ms made this clock race
            // ~7x too fast on the AudioWorklet path (128 samples ≈ 2.7 ms),
            // ending every recording in a few seconds regardless of the timer.
            if (!listenFor.current) return;
            talk.current = observe(talk.current, dbfs, frameMs, floor.current);
            if (shouldAdvance(talk.current, listenFor.current, trailingFor.current)) {
              // The same lever the "I'm done" button pulls. The countdown
              // remains the ceiling; this reaches it early only once the
              // candidate has spoken and then stopped.
              // Which branch fired decides what the report may claim:
              // reaching the ceiling IS the window expiring (this callback
              // beats the wall-clock countdown to it by a frame), and only
              // a silence advance before the ceiling is an early finish.
              endReason.current = advanceReason(talk.current, listenFor.current);
              listenFor.current = 0;
              stopEarly.current = true;
            }
          } });
        }
        setPhase(resumeToSubmit.current ? "submitting" : "section");
        if (resumeToSubmit.current) void finishResumed();
      } catch (err) {
        // A microphone failure and an API failure need different words: one is
        // fixable by the student in ten seconds, the other is not.
        if (err instanceof MicPermissionError) {
          setError("Microphone access was withdrawn. Allow it in the address bar and start again.");
        } else if (err instanceof MicUnavailableError) {
          setError("The microphone is no longer available. Reconnect it and start again.");
        } else {
          setError(err instanceof ApiError ? err.detail : "Could not open the simulation.");
        }
        setPhase("failed");
      }
    })();
  }, [id, router, finishResumed]);

  // -- the clock ----------------------------------------------------------

  const countdown = useCallback(async (total: number): Promise<void> => {
    stopEarly.current = false;
    // Anchored to the wall clock, not to the number of sleeps. A hidden tab
    // has its timers throttled (hardware UAT, D4: one tick every ten
    // seconds), which used to stretch a 90-second think to fifteen minutes
    // while the server's deadline kept true time. Remaining time is now
    // computed from Date.now() on every wake, so throttling only affects
    // how often the display refreshes, never how long the window lasts.
    const endAt = Date.now() + total * 1000;
    let shown = -1;
    while (true) {
      if (stopEarly.current) { setSeconds(0); return; }
      const remaining = remainingSeconds(endAt, Date.now());
      if (remaining <= 0) break;
      if (remaining !== shown) { setSeconds(remaining); shown = remaining; }
      await sleep(100);
    }
    setSeconds(0);
  }, []);

  // The section clock. Restarted whenever the section changes, ticking only
  // while the candidate is actually working through it.
  const sectionBase = useRef(0);
  useEffect(() => {
    setSectionElapsed(0);
    sectionBase.current = 0;
  }, [item?.section_id]);

  // The lettered-section clock (SVAR-style Section A 10 min, C 15 min, D 10
  // min). Restarts on a new letter, ticks whenever the section clock does.
  const groupLetter = item ? svarSectionBanner(item.section_title).letter : "";
  const groupBase = useRef(0);
  useEffect(() => {
    setGroupElapsed(0);
    groupBase.current = 0;
    groupExpired.current = false;
  }, [groupLetter]);

  // Both clocks accumulate wall-clock time while the candidate is working
  // (not on a section card). Elapsed = time banked before this phase + time
  // since it began, read from Date.now() on every tick -- so a throttled tab
  // shows a stale number for a moment and then the right one, rather than a
  // clock that runs slow (D4).
  useEffect(() => {
    if (phase === "loading" || phase === "submitting" || phase === "failed"
        || phase === "owed" || phase === "section") return;
    const since = Date.now();
    const g0 = groupBase.current, s0 = sectionBase.current;
    const tick = () => {
      const dt = Math.floor((Date.now() - since) / 1000);
      setGroupElapsed(g0 + dt);
      setSectionElapsed(s0 + dt);
    };
    const timer = setInterval(tick, 1000);
    return () => {
      clearInterval(timer);
      const dt = Math.floor((Date.now() - since) / 1000);
      groupBase.current = g0 + dt;
      sectionBase.current = s0 + dt;
    };
  }, [phase]);

  // Section budget expiry. Marks the group expired, and -- if the current
  // item is still waiting at a gate rather than recording -- releases the
  // gate so runItem can pass the item over. A recording in progress is
  // never touched (hardware UAT, D3: Q16 sat at "Play Audio" on a dead clock).
  useEffect(() => {
    if (!item || !payload) return;
    const letter = svarSectionBanner(item.section_title).letter;
    const members = payload.items.filter(
      (i) => svarSectionBanner(i.section_title).letter === letter);
    const budget = Math.max(0, ...members.map((i) => i.section_budget_seconds || 0));
    const decision = sectionExpiry({ budgetSeconds: budget, elapsedSeconds: groupElapsed,
                                     alreadyExpired: groupExpired.current, phase });
    if (!decision.expired) return;
    groupExpired.current = true;
    if (decision.releaseGate) {
      skipCurrent.current = true;
      stopEarly.current = true;          // ends a think countdown
      playResolver.current?.();          // releases Play Audio
      startResolver.current?.();         // releases Start Recording
      ackResolver.current?.();           // releases a typed-Okay gate
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groupElapsed]);

  // The carried banner clears once the candidate is answering again.
  useEffect(() => {
    if (phase === "answer" || phase === "respond") setBanner("");
  }, [phase]);

  // -- the whole-sitting clock ---------------------------------------------
  //
  // Counted from the server's deadline and the server's idea of now, taken
  // once. A countdown run off the device clock expires early on a laptop
  // whose time is wrong, and a sleeping tab would resume counting as though
  // no time had passed.
  useEffect(() => {
    if (!payload?.deadline_at || !payload.server_now) return;
    const skewMs = Date.parse(payload.server_now) - Date.now();
    const deadline = Date.parse(payload.deadline_at);
    const tick = () => setSittingLeft(
      Math.max(0, Math.round((deadline - (Date.now() + skewMs)) / 1000)));
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [payload?.deadline_at, payload?.server_now]);

  // Out of time: submit what exists. Never discard it, and never mark the
  // unreached items as refusals -- the candidate did not get to them, which
  // is a different fact from declining to answer.
  useEffect(() => {
    if (sittingLeft !== 0) return;
    if (phase === "loading" || phase === "submitting" || phase === "failed") return;
    setNotice("Time is up. Submitting everything you answered.");
    // Both, and the first is the one that was missing. `stopEarly` ends the
    // item in progress; `expired` ends the sequence. Without it the runner
    // finished the current item and moved to the next, and every answer
    // after the bell was refused while the candidate kept working.
    expired.current = true;
    stopEarly.current = true;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sittingLeft]);

  // -- getting a recording to the server ----------------------------------

  /** Ask whether to record again. Resolves false if they would rather move on. */
  const retakeResolver = useRef<((again: boolean) => void) | null>(null);
  const [retakePeak, setRetakePeak] = useState<number | null>(null);

  const offerRetake = useCallback((peakDbfs: number): Promise<boolean> => {
    setRetakePeak(peakDbfs);
    return new Promise<boolean>((resolve) => { retakeResolver.current = resolve; })
      .then((answer) => { setRetakePeak(null); retakeResolver.current = null; return answer; });
  }, []);

  /**
   *  Keep it, then try to send it. In that order, always.
   *
   *  The recording goes into IndexedDB before the first POST, so a crash, a
   *  reload or a closed lid between here and the acknowledgement loses
   *  nothing. It is removed only when the server confirms it has it -- and a
   *  409 counts as confirmation, because the server refuses a second upload
   *  for a response it already holds.
   *
   *  What this deliberately does not do on failure is call `skip`. That was
   *  the old behaviour and it wrote a false statement about a person into a
   *  result they are judged on: a dropped Wi-Fi frame became "did not
   *  answer". The item stays owed, visibly, and submission is blocked until
   *  it is delivered or the candidate consciously abandons it.
   */
  const store = useCallback(async (responseId: string, payload: Blob,
                                   kind: "audio" | "answer" = "audio",
                                   endedBy = "") => {
    // Persist-first, deliver-in-background. Awaiting the whole upload here
    // put its retry backoff inside the candidate's Next click — one transient
    // failure and they stared at a stalled screen for seconds. The answer is
    // on disk (~2 ms) before this resolves; the send, its retries and the
    // failure messaging continue behind the next item, and submission still
    // refuses to proceed while anything is owed.
    const { owed: inFlight } = await deliverRecordingInBackground({
      attemptId: id, responseId, blob: payload, kind, endedBy,
      send: (rid, blob, k, endReason) => k === "answer"
        ? attemptApi.answerStatus(id, rid, blob)
        : attemptApi.uploadAudioStatus(id, rid, blob, endReason),
      onRetry: (attempt, waitMs) =>
        setUploadNote(`Saving an answer in the background — retry ${attempt} in ${Math.round(waitMs / 1000)}s.`),
    }, (result) => {
      setUploadNote("");
      setOwed(result.owed);
      if (result.ok) return;
      setNotice(result.outcome.reason === "terminal"
        ? "That answer could not be accepted. It is kept on this device; you "
          + "will be asked about it before you finish."
        : "Your answer is saved on this device but has not reached us yet. "
          + "It will be retried before you finish.");
    });
    setOwed(inFlight);
  }, [id]);

  // On arrival, and whenever the network comes back. A reload mid-attempt is
  // the case this exists for: the audio is in IndexedDB and the server has
  // never seen it.
  useEffect(() => {
    // What this browser was already holding when the page opened, shown
    // before the first drain finishes so a reloading candidate is not told
    // "0 to send" about answers that exist.
    void owedFor(id).then(setOwed);
    void drainQueue();
    const back = () => { void drainQueue(); };
    window.addEventListener("online", back);
    return () => window.removeEventListener("online", back);
  }, [drainQueue, id]);

  // -- one item -----------------------------------------------------------

  /** If the section's budget ran out while this item was waiting at a gate,
   *  report it unanswered and tell the candidate. Returns true when the item
   *  was passed over. */
  const passOverIfSectionOver = useCallback(async (current: RunnerItem): Promise<boolean> => {
    if (!skipCurrent.current) return false;
    skipCurrent.current = false;
    try { await attemptApi.skip(id, current.response_id); } catch { /* best effort */ }
    setBanner("Section time is over. Moving to the next section.");
    return true;
  }, [id]);

  const runItem = useCallback(async (current: RunnerItem) => {
    setNotice("");
    // Skinned (vendor-exact) runs use manual Start Recording / Play Audio
    // gates; unskinned formats keep the original auto-start flow untouched.
    const svar = !!skinFor(payload?.style ?? "", payload?.company ?? "");

    // Answered by choosing or typing rather than speaking.
    //
    // The three modes share one attempt lifecycle deliberately: same items,
    // same section order, same timing, same submission guarantees. Only the
    // shape of "give your answer" differs, so only that part branches.
    if (current.response_mode !== "speak") {
      // The audio plays once per passage, not once per question. An item that
      // belongs to a passage group only plays if it owns that group's
      // playback (the first question of the passage); the other questions in
      // the group skip straight to answering on what was already heard. An
      // ungrouped item (no passage_ref) always plays its own prompt.
      const grouped = current.passage_ref !== "";
      const playsAudio = current.prompt_plays_allowed > 0
        && (!grouped || firstOfPassage.has(current.response_id));
      if (playsAudio) {
        // SVAR: the candidate presses Play Audio; it plays once, then the
        // questions appear. Every other format auto-plays as before.
        if (svar) {
          setPhase("listen");
          await new Promise<void>((resolve) => { playResolver.current = resolve; });
          playResolver.current = null;
        }
        setPhase("prompt");
        try {
          const prompt = await attemptApi.prompt(id, current.response_id);
          // Prefer the server-rendered clip (deterministic, verifiable); fall
          // back to the browser voice only if it did not play.
          const played = prompt.audio_url
            ? await playAudioUrl(prompt.audio_url) : false;
          if (!played) await speak(prompt.text, prompt.accent);
        } catch (err) {
          setNotice(err instanceof ApiError && err.status === 409
            ? "This passage was already played and cannot be replayed. Answer as best you can."
            : "The passage could not be played. Answer as best you can.");
        }
        if (current.ack_gate === "clip") {
          // Mettl D: the clip screen is its own numbered item, and the
          // questions appear only after a typed "Okay". No replay.
          setOkayText("");
          setPhase("ack");
          await new Promise<void>((resolve) => { ackResolver.current = resolve; });
          ackResolver.current = null;
          if (await passOverIfSectionOver(current)) return;
        }
      }
      setChoice(null);
      setWritten("");
      // A reconstruction passage is readable for a fixed time and then gone.
      // Holding it is the whole task, so the clock starts the moment it is
      // shown rather than when the candidate starts typing.
      setStimulusLeft(current.stimulus_seconds > 0
        ? current.stimulus_seconds : null);
      setPhase("respond");

      // Wait here until the student answers.
      //
      // Returning early instead would hand control straight back to
      // `advance`, which would move to the next item before the question had
      // been read. Blocking keeps one sequence for all three modes: the
      // recorded path waits on a countdown, this one waits on a person.
      const given = await new Promise<{ index: number | null; text: string }>(
        (resolve) => { answerResolver.current = resolve; });
      answerResolver.current = null;

      setPhase("saving");

      // Kept first, sent second -- the same order as a recording, and for the
      // same reason.
      //
      // This used to POST once and call `skip` on any failure, so a candidate
      // who wrote three paragraphs and hit a dropped connection was recorded
      // as not having answered. Phase 7 fixed that for audio and left it here,
      // on the grounds that a typed answer is small and re-enterable. It is
      // not re-enterable: the runner has already moved on, and one-shot means
      // they never see the question again.
      // `composed_at` travels inside the queued body rather than being
      // stamped at send time, because the moment that matters is this one --
      // when the candidate set the answer down -- and a retry an hour from
      // now must still carry it. It is what lets the server accept a late
      // delivery of an answer given in time without also accepting an answer
      // given late.
      await store(current.response_id,
                  new Blob([JSON.stringify({
                    ...(current.response_mode === "select"
                      ? { selected_index: given.index }
                      : { text: given.text }),
                    composed_at: new Date().toISOString(),
                  })], { type: "application/json" }),
                  "answer");
      return;
    }

    if (current.prep_seconds > 0) {
      setPhase("prep");
      await countdown(current.prep_seconds);
    }

    if (current.prompt_plays_allowed > 0) {
      // SVAR Listen & Repeat: the candidate presses Play Audio, it plays once,
      // and only then does Start Recording become available (the armed gate
      // below). Every other format auto-plays as before. The server's
      // one-play-per-response guard is untouched -- this only defers the single
      // play to a click.
      if (svar) {
        setPhase("listen");
        await new Promise<void>((resolve) => { playResolver.current = resolve; });
        playResolver.current = null;
        if (await passOverIfSectionOver(current)) return;
      }
      setPhase("prompt");
      try {
        const prompt = await attemptApi.prompt(id, current.response_id);
        await speak(prompt.text, prompt.accent);
      } catch (err) {
        // A prompt that will not play must not cost the student the item —
        // but they do need to know why they heard silence.
        setNotice(err instanceof ApiError && err.status === 409
          ? "This prompt was already played and cannot be replayed. Answer as best you can."
          : "The prompt could not be played. Answer as best you can.");
      }
    }

    // SVAR manual start: read-aloud and repeat items wait for the candidate
    // to press Start Recording. Thinking-time items (prep>0, e.g. Speak on a
    // Topic) auto-start when the countdown ends, so they skip this gate. Only
    // SVAR-style runs use this gate; other formats auto-start as before.
    if (svar && current.prep_seconds === 0) {
      setPhase("armed");
      await new Promise<void>((resolve) => { startResolver.current = resolve; });
      startResolver.current = null;
      if (await passOverIfSectionOver(current)) return;
    }
    if (await passOverIfSectionOver(current)) return;

    if (skipTopic.current) {
      // Skip pressed during thinking time. No recording is made; the item
      // is reported as unanswered, honestly, and the candidate moves on.
      skipTopic.current = false;
      try { await attemptApi.skip(id, current.response_id); } catch { /* best effort */ }
      setBanner("Topic skipped — no response was recorded for it.");
      return;
    }

    await beep();

    setPhase("answer");
    // Adaptive advancement. The countdown is still the ceiling; this only
    // declines to sit through trailing silence once the candidate has
    // actually finished. `listenFor` non-zero is what arms it, so nothing
    // changes for prep, playback or the other two response modes.
    talk.current = FRESH;
    listenFor.current = current.response_seconds * 1000;
    trailingFor.current = windowFor(current);
    endReason.current = "window_expired";
    recorder.current?.start();
    await countdown(current.response_seconds);
    listenFor.current = 0;

    let wav = recorder.current?.stop();
    let samples = recorder.current?.lastCapture ?? new Float32Array(0);
    setPhase("saving");

    // Was anything recorded at all?
    //
    // A gate, not a measurement. It decides whether to offer one re-record
    // before the item is committed; it never scores, never touches a
    // dimension, and never alters a byte of what is uploaded. The server's
    // own VAD runs on exactly these samples and remains the only authority
    // over the result.
    const heard = inspect(samples, TARGET_SAMPLE_RATE, floor.current);
    // UAT instrumentation: what the silence gate saw. Debug level only.
    console.debug("[runner] silence-check " + JSON.stringify({
      item: current.response_id, floorDbfs: floor.current, samples: samples.length,
      heardSomething: heard.heardSomething, speechMs: heard.speechMs, peakDbfs: heard.peakDbfs,
      talk: talk.current,
    }));
    if (!heard.heardSomething && current.response_seconds > 0) {
      const retake = await offerRetake(heard.peakDbfs);
      if (retake) {
        await beep();
        setPhase("answer");
        talk.current = FRESH;
        listenFor.current = current.response_seconds * 1000;
        trailingFor.current = windowFor(current);
        endReason.current = "window_expired";
        recorder.current?.start();
        await countdown(current.response_seconds);
        listenFor.current = 0;
        wav = recorder.current?.stop();
        samples = recorder.current?.lastCapture ?? new Float32Array(0);
        setPhase("saving");
        // A second silent take goes through. Telling somebody twice that
        // they said nothing, when they may be sitting in front of a broken
        // microphone, helps nobody -- and the server reports it honestly.
      }
    }

    if (!wav || wav.size <= 1000) {
      // Genuinely nothing captured. This is the one path where `skip` is the
      // truth: there is no audio to lose.
      try { await attemptApi.skip(id, current.response_id); } catch { /* best effort */ }
      return;
    }

    await store(current.response_id, wav, "audio", endReason.current);
  }, [countdown, id, offerRetake, store, payload?.style, firstOfPassage, passOverIfSectionOver, payload?.company]);

  // -- the sequence -------------------------------------------------------

  useEffect(() => {
    if (phase !== "section" || !item || !payload) return;
    const prev = index > 0 ? payload.items[index - 1] : null;
    const svar = !!skinFor(payload.style, payload.company ?? "");
    // A card is shown, and the sequence waits for acknowledgement, on a new
    // section -- or for a skinned format, on a new *letter*, so subsections
    // (A1->A2->A3, C1->C2) flow straight through under one introduction
    // rather than interrupting three times.
    const gate = svar
      ? index === 0
        || svarSectionBanner(prev?.section_title ?? "").letter !== svarSectionBanner(item.section_title).letter
      : index === 0 || prev?.section_id !== item.section_id;
    if (gate) return;   // wait for the student to acknowledge
    void advance();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, index]);

  async function advance() {
    if (!payload || !item) return;
    await runItem(item);

    // A lettered section whose budget has run out: everything left in it is
    // passed over (reported unanswered, never marked as a refusal) and the
    // sequence resumes at the next letter. The item that was in progress was
    // allowed to finish -- a section clock warns and stops progression; it
    // never cuts into a recording.
    let next = index + 1;
    if (groupExpired.current) {
      const letter = svarSectionBanner(item.section_title).letter;
      while (next < payload.items.length
             && svarSectionBanner(payload.items[next].section_title).letter === letter) {
        try { await attemptApi.skip(id, payload.items[next].response_id); } catch { /* best effort */ }
        next += 1;
      }
      if (next > index + 1) {
        setBanner("Section time is over. Moving to the next section.");
      }
    }

    if (nextStep({ index, total: payload.items.length,
                   expired: expired.current }) === "next" && next < payload.items.length) {
      setIndex(next);
      setPhase("section");
      return;
    }

    setPhase("submitting");

    // One last go at anything this browser is still holding, before the
    // recorder is closed and the page navigates away. Submitting with
    // recordings still queued would throw away answers the candidate gave --
    // so if any remain, the attempt is not submitted silently; they are told
    // and asked.
    const stillOwed = await drainQueue();
    if (stillOwed > 0) {
      setUploadNote(
        `${stillOwed} of your answers ${stillOwed === 1 ? "has" : "have"} not `
        + `reached us. They are saved on this device. Try again, or finish `
        + `without them — they will not be scored if you do.`);
      setPhase("owed");
      return;
    }

    recorder.current?.close();
    recorder.current = null;
    try {
      await attemptApi.submit(id);
      router.replace(`/results/${id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Scoring failed.");
      setPhase("failed");
    }
  }

  /** Finish without the queued answers, having been told what that costs. */
  async function finishAnyway() {
    setPhase("submitting");
    recorder.current?.close();
    recorder.current = null;
    try {
      await attemptApi.submit(id);
      router.replace(`/results/${id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Scoring failed.");
      setPhase("failed");
    }
  }

  // -- rendering ----------------------------------------------------------

  if (phase === "loading") {
    return <Centered><Loader2 size={22} className="animate-spin text-muted" /></Centered>;
  }

  if (phase === "failed") {
    // Where "try again" actually leads depends on who stopped.
    //
    // A student can walk away and start another simulation whenever they
    // like. An invited candidate cannot: an invitation is one sitting, the
    // server refuses a second attempt, and /simulate is a student page that
    // would eject them to a login screen they have no account for. What they
    // need is the environment check for *this* attempt -- it resumes the same
    // one, and everything already recorded is already uploaded.
    const candidate = user?.role === "candidate";
    return (
      <Centered>
        <div className="max-w-sm text-center">
          <div className="text-sm font-bold mb-2">This attempt stopped</div>
          <p className="text-xs text-muted mb-4">{error}</p>
          {candidate && (
            <p className="text-[11px] text-muted mb-4 leading-relaxed">
              Nothing you have already answered is lost. Check your microphone
              and carry on from where you stopped.
            </p>
          )}
          <button
            onClick={() => router.push(candidate ? `/attempt/${id}/check` : "/simulate")}
            className="btn btn-primary ds-focus">
            {candidate ? "Check the microphone and carry on" : "Back to simulations"}
          </button>
        </div>
      </Centered>
    );
  }

  if (!item || !payload) return null;

  const format = FORMAT[payload.style] ?? DEFAULT_FORMAT;
  // Which vendor-exact skin this style wears, if any. `isSvar` is kept as the
  // name for "uses the assessment shell" -- the shell was born with the SVAR
  // rebuild and every skinned style shares it.
  const skin = skinFor(payload.style, payload.company ?? "");
  const isSvar = !!skin;
  const svarBanner = svarSectionBanner(item.section_title);
  // The introduction gate. Every format shows a card when the section changes;
  // SVAR groups its subsections under one letter, so A1->A2->A3 flow straight
  // through and only a new letter (A, B, C, D) shows a fresh "SECTION A"
  // introduction -- one per part, as the reference does, not one per
  // subsection. The item sequence and counts are unchanged; only whether a
  // card is shown differs.
  const prevItem = index > 0 ? payload.items[index - 1] : null;
  const newSection = index === 0 || prevItem?.section_id !== item.section_id;
  const newLetter = index === 0
    || (!!prevItem && svarSectionBanner(prevItem.section_title).letter !== svarBanner.letter);
  const introGate = isSvar ? newLetter : newSection;
  const showSectionCard = phase === "section" && introGate;

  // Where you are across the whole sitting, for SVAR's continuous count. The
  // per-section position the app header shows is more actionable for the other
  // formats, so they keep it -- see the header below.
  const overallNo = index + 1;
  const overallTotal = payload.items.length;
  // Section position, derived rather than sent: the payload already lists
  // every item in order, so counting distinct sections here avoids another
  // field that could disagree with the items beside it.
  const sectionIds = payload.items.map((i) => i.section_id)
    .filter((id, n, all) => all.indexOf(id) === n);
  const sectionNo = sectionIds.indexOf(item.section_id) + 1;
  const sectionTotal = sectionIds.length;
  const itemsInSection = payload.items.filter((i) => i.section_id === item.section_id);
  const itemNoInSection =
    itemsInSection.findIndex((i) => i.response_id === item.response_id) + 1;

  const budget = sectionBudget(payload.items, item.section_id);
  const sectionLeft = sectionRemaining(budget, sectionElapsed);
  const sectionTone = sectionMood(sectionLeft, budget);

  // SVAR-style: questions are numbered continuously through a lettered
  // section (the reference shows Q9 as the first paragraph and Q11 as the
  // first audio item, and "1/34" across the whole grammar section), and the
  // section's budget is one clock for the letter.
  const svarLetter = svarSectionBanner(item.section_title).letter;
  const groupItems = payload.items.filter(
    (i) => svarSectionBanner(i.section_title).letter === svarLetter);
  // Numbering through the group. In a clip-gated section (Mettl D) each
  // clip's own screen is a numbered item -- "Q.1 Listen ... Type 'Okay'" --
  // so four clips of three questions count 1..16, not 1..12.
  const numbering = groupNumbering(groupItems, item.response_id, firstOfPassage);
  const itemNoInGroup = numbering.no;
  const groupBudget = Math.max(0, ...groupItems.map((i) => i.section_budget_seconds || 0));
  const groupLeft = groupBudget > 0 ? Math.max(0, groupBudget - groupElapsed) : null;
  // On a clip's own screen (play / listening / Okay) the clip is the
  // numbered item, one before its first question.
  const onClipScreen = item.ack_gate === "clip" && firstOfPassage.has(item.response_id)
    && (phase === "listen" || phase === "prompt" || phase === "ack");
  const qNo = item.continuous_numbering ? (onClipScreen ? itemNoInGroup - 1 : itemNoInGroup) : itemNoInSection;
  const qTotal = item.continuous_numbering ? numbering.total : itemsInSection.length;

  return (
    <div className={`runner${skin ? ` ${skin.theme}` : ""}`}>
      {isSvar ? (
        // The reference header is minimal: a continuous whole-test count and
        // the sitting timer. The blue section banner below carries the "which
        // part" the app chrome would otherwise duplicate.
        <header className="svar-topbar">
          <span className="svar-count">{qNo} / {qTotal}</span>
          {groupLeft != null && (
            <span
              data-testid="section-clock"
              className="svar-timer"
              style={{ marginLeft: "1rem",
                       color: groupLeft <= 60 ? "var(--rag-red)"
                         : groupLeft <= 180 ? "var(--rag-amber)" : "var(--svar-navy)" }}
              title="Time left for this section. When it runs out, the rest of the section is passed over; a recording in progress is never cut off."
            >
              Section {Math.floor(groupLeft / 60)}:{String(groupLeft % 60).padStart(2, "0")}
            </span>
          )}
          <div className="flex-1" />
          {owed > 0 && (
            <span className="svar-owed"
                  title="Answers saved on this device that have not reached us yet. They are retried automatically.">
              {owed} to send
            </span>
          )}
          {sittingLeft != null && (
            <span
              data-testid="sitting-clock"
              className="svar-timer"
              style={{ color: sittingLeft <= 120 ? "var(--rag-red)"
                       : sittingLeft <= 300 ? "var(--rag-amber)" : "var(--svar-navy)" }}
              title="Time left for the whole assessment. When it runs out, everything you have answered is submitted and scored."
            >
              {Math.floor(sittingLeft / 60)}:{String(sittingLeft % 60).padStart(2, "0")}
            </span>
          )}
        </header>
      ) : (
      <header className="flex items-center gap-3 px-4 h-12 border-b border-border shrink-0">
        {/* Which test, then where you are in it. Position within the section
            matters more to a candidate than position overall -- "two left in
            this part" is actionable, "item 19 of 26" is not. */}
        <span className="chip shrink-0" style={{
          background: "color-mix(in srgb, " + format.tint + " 16%, transparent)",
          color: format.tint, fontWeight: 700,
        }}>
          {payload.company || format.label}
        </span>
        <span className="text-[11px] font-bold uppercase tracking-wider text-muted truncate">
          {format.sectionWord} {sectionNo}/{sectionTotal} · {item.section_title}
        </span>
        <span className="text-[11px] text-muted shrink-0">
          {itemNoInSection}/{itemsInSection.length}
        </span>
        <div className="flex-1" />
        {/* Two clocks, both advisory here. The section one warns and never
            interrupts -- the item timer already bounds every recording, and a
            second authority over the same recording is how answers get cut in
            half. The sitting one is the hard stop, and the server enforces it
            whatever this display says. */}
        <span
          data-testid="section-clock"
          className="text-[11px] shrink-0 hidden sm:inline tabular-nums"
          style={{ color: sectionTone === "over" ? "var(--rag-amber)"
                   : sectionTone === "warn" ? "var(--rag-amber)"
                   : "var(--muted)" }}
          title="Roughly how long this part should take. It is a guide — it will never cut an answer short."
        >
          {sectionTone === "over"
            ? `${format.sectionWord} running long`
            : `${Math.floor(sectionLeft / 60)}:${String(sectionLeft % 60).padStart(2, "0")} left in this ${format.sectionWord.toLowerCase()}`}
        </span>
        {sittingLeft != null && (
          <span
            data-testid="sitting-clock"
            className="text-[11px] font-bold tabular-nums shrink-0"
            style={{ color: sittingLeft <= 120 ? "var(--rag-red)"
                     : sittingLeft <= 300 ? "var(--rag-amber)" : "var(--muted)" }}
            title="Time left for the whole assessment. When it runs out, everything you have answered is submitted and scored."
          >
            {Math.floor(sittingLeft / 60)}:{String(sittingLeft % 60).padStart(2, "0")}
          </span>
        )}
        {owed > 0 && (
          <span className="text-[11px] font-bold shrink-0"
                style={{ color: "var(--rag-amber)" }}
                title="Answers saved on this device that have not reached us yet. They are retried automatically.">
            {owed} to send
          </span>
        )}
        <span
          data-testid="mic-state"
          className={
            phase === "answer" ? "mic-dot mic-recording"
            : phase === "prompt" ? "mic-dot mic-armed"
            : phase === "saving" ? "mic-dot mic-done" : "mic-dot mic-idle"
          }
        />
        <span className="text-[11px] text-muted">
          {phase === "answer" ? "Recording"
            : phase === "prompt" ? "Listen"
            : phase === "prep" ? "Get ready"
            : phase === "saving" ? "Saving" : "Ready"}
        </span>
      </header>
      )}

      {/* Progress. SVAR shows one continuous fill over the whole sitting to
          match its running count; every other format keeps the per-section
          segment strip -- "how many parts left" is what its header speaks to. */}
      {isSvar ? (
        <div className="svar-progressbar">
          <span style={{ width: `${(overallNo / overallTotal) * 100}%` }} />
        </div>
      ) : (
      <div className="flex gap-1 px-4 py-1.5 shrink-0 border-b border-border">
        {sectionIds.map((id, n) => (
          <span
            key={id}
            className="flex-1 rounded-full"
            style={{
              height: 3,
              background: n < sectionNo - 1 ? format.tint
                : n === sectionNo - 1 ? "color-mix(in srgb, " + format.tint + " 45%, transparent)"
                : "var(--border)",
            }}
          />
        ))}
      </div>
      )}

      {/* Left the screen.
          Not a disqualification. A real test would fail you for this; a
          practice tool that copies that teaches nothing and punishes the
          student whose hostel wifi dropped. It pauses, says what it saw, and
          asks whether now is still a good time -- and records the
          interruption either way, so a trainer sees a disturbed attempt
          rather than an unexplained dip. */}
      {away && (
        <div className="modal-scrim" role="presentation"
             onMouseDown={(e) => e.preventDefault()}>
          <div className="modal-panel" role="dialog" aria-modal="true"
               aria-labelledby="away-title"
               onMouseDown={(e) => e.stopPropagation()}>
            {!rescheduling ? (
              <>
                <div className="text-[11px] font-bold uppercase tracking-wider text-muted mb-1">
                  Paused
                </div>
                <h2 id="away-title" className="text-xl font-bold mb-2">
                  Still there?
                </h2>
                <p className="text-xs text-muted leading-relaxed mb-1">
                  You moved away from the test{" "}
                  {events.length > 1 ? `${events.length} times` : "for a moment"}.
                  The timer kept running, because it does on the day too.
                </p>
                <p className="text-xs text-muted leading-relaxed mb-4">
                  If this is a bad moment, stop now and come back when you have
                  a clear stretch — a distracted attempt tells you less than no
                  attempt at all.
                </p>
                <div className="space-y-2">
                  <button onClick={resume} className="btn btn-primary w-full ds-focus">
                    I am ready — carry on
                  </button>
                  <button onClick={() => setRescheduling(true)}
                          className="btn btn-ghost w-full ds-focus">
                    Take this another time
                  </button>
                </div>
              </>
            ) : (
              <>
                <div className="text-[11px] font-bold uppercase tracking-wider text-muted mb-1">
                  Before you go
                </div>
                <h2 className="text-xl font-bold mb-2">Leave this attempt?</h2>
                <p className="text-xs text-muted leading-relaxed mb-4">
                  What you have answered so far is saved and will be scored.
                  Prompts play once, so the items you have already heard cannot
                  be replayed if you come back to this attempt — starting fresh
                  later gives you a cleaner reading.
                </p>
                <div className="space-y-2">
                  <button onClick={() => router.push("/simulate")}
                          className="btn btn-primary w-full ds-focus">
                    Leave and come back later
                  </button>
                  <button onClick={() => setRescheduling(false)}
                          className="btn btn-ghost w-full ds-focus">
                    Actually, keep going
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      <div className="runner-body">
        {isSvar && !showSectionCard && phase !== "submitting" && phase !== "owed" && (
          <div className="svar-section-banner w-full self-stretch -mt-2 mb-4">
            <h1>{format.sectionWord.toUpperCase()} {svarBanner.letter}: {svarBanner.name}</h1>
          </div>
        )}
        {/* What just happened, carried onto the next screen: a skipped topic
            or a section that ran out of time (UAT D3/D5: the message was set
            but never shown where the candidate could read it). */}
        {isSvar && banner && phase !== "answer" && phase !== "respond" && (
          <p data-testid="carried-banner" className="w-full max-w-3xl self-stretch text-center mb-3"
             style={{ color: "var(--rag-amber)", fontWeight: 600 }}>{banner}</p>
        )}
        {/* The per-question task line (Cognizant reference: every numbered
            question carries its own "Task:" instruction, and the sub-tasks
            inside a lettered section change without a divider). Flagged per
            section, so SVAR's frozen one-card-per-part presentation is
            untouched. This is what tells a candidate entering Word Lists or
            Listen & Repeat what to do now. */}
        {isSvar && item.show_instruction && !showSectionCard && item.instructions
          && phase !== "saving" && (
          <p data-testid="task-line"
             className="w-full max-w-3xl self-stretch text-left mb-3"
             style={{ color: "var(--svar-navy)" }}>
            <b>Task:</b> {item.instructions}
          </p>
        )}
        {showSectionCard && isSvar && (
          <div className="w-full max-w-3xl self-stretch text-left">
            <div className="svar-section-banner mb-6" style={{ marginTop: "-0.5rem" }}>
              <h1>{format.sectionWord.toUpperCase()} {svarBanner.letter}: {svarBanner.name}</h1>
            </div>
            {banner && (
              <p data-testid="carried-banner" className="mb-3"
                 style={{ color: "var(--rag-amber)", fontWeight: 600 }}>{banner}</p>
            )}
            <p className="mb-2"><b>Instructions:</b> {item.instructions}</p>
            <div className="svar-note mt-6 mb-8">
              <div style={{ fontWeight: 700, marginBottom: 6 }}>Note:</div>
              <ul style={{ listStyle: "disc", paddingLeft: "1.2rem" }}>
                <li>Ensure the room is quiet and free from background noise.</li>
                {item.response_mode === "speak" && (
                  <li>You can only record each response once.</li>
                )}
                {item.prompt_plays_allowed > 0 && (
                  <li>Audio plays once and cannot be paused or replayed.</li>
                )}
                {item.response_seconds > 0 && item.response_mode === "speak" && (
                  <li>Your response submits automatically when the time is up.</li>
                )}
              </ul>
            </div>
            {item.ack_gate === "section" ? (
              // Directly evidenced: the reference's comprehension instructions
              // end with "Type 'Okay' in the box below to proceed to the
              // questions". The gate is the acknowledgement, nothing more.
              <div className="text-center space-y-3">
                <div className="text-[13px]">Type <b>&lsquo;Okay&rsquo;</b> in the box below to proceed to the questions.</div>
                <input className="svar-input mx-auto" style={{ maxWidth: "14rem", textAlign: "center" }}
                       value={okayText} onChange={(e) => setOkayText(e.target.value)}
                       placeholder="Okay" aria-label="Type Okay to proceed" />
                <div>
                  <button onClick={() => void advance()} className="svar-btn"
                          disabled={okayText.trim().toLowerCase() !== "okay"}>Next</button>
                </div>
              </div>
            ) : (
              <div className="text-center">
                <button onClick={() => void advance()} className="svar-btn">Next</button>
              </div>
            )}
          </div>
        )}
        {showSectionCard && !isSvar && (
          <div className="max-w-md">
            <div className="text-[11px] font-bold uppercase tracking-wider mb-2"
                 style={{ color: format.tint }}>
              {payload.company || format.label} · {format.sectionWord} {sectionNo} of {sectionTotal}
            </div>
            <h2 className="text-2xl font-bold mb-3">{item.section_title}</h2>
            <p className="runner-instruction mb-2">
              {item.instructions || taskLabel(item.task_type)}
            </p>
            <p className="runner-instruction mb-6">
              {whatToExpect(item.response_mode, item.prep_seconds,
                            item.response_seconds, item.prompt_plays_allowed)}
            </p>
            <button onClick={() => void advance()} className="btn btn-primary ds-focus">
              I am ready
            </button>
          </div>
        )}

        {phase === "armed" && (
          isSvar ? (
            <div className="w-full max-w-3xl self-stretch text-center space-y-5">
              <p className="svar-instruct">{armedLine(item.task_type)}</p>
              {item.prompt_text && (
                <div className="svar-qbar text-left">
                  <b className="svar-qnum">Question&nbsp;#&nbsp;{qNo}:</b> {item.prompt_text}
                </div>
              )}
              <div className="svar-record-head">
                <span className="svar-mic-tile"><Mic size={26} /></span>
                <div className="text-left">
                  <div style={{ fontWeight: 700, fontSize: "1.05rem" }}>Record your response</div>
                  <div style={{ color: "var(--svar-navy)" }}>
                    Recording Time: {item.response_seconds} Sec
                  </div>
                </div>
              </div>
              <p className="svar-hint mx-auto">
                Press &lsquo;Start Recording&rsquo; to record your response when you are
                ready. You can only record it once.
              </p>
              <div className="svar-circle svar-circle--record">
                <span className="lbl">Recording Time</span>
                <span className="n">{item.response_seconds}</span>
                <span className="lbl">Sec</span>
              </div>
              <button className="svar-btn" onClick={() => startResolver.current?.()}>
                Start Recording
              </button>
            </div>
          ) : (
            <>
              {item.prompt_text && <p className="runner-prompt">{item.prompt_text}</p>}
              <p className="runner-instruction">When you are ready, start recording.</p>
              <button className="btn btn-primary ds-focus" onClick={() => startResolver.current?.()}>
                Start recording
              </button>
            </>
          )
        )}

        {phase === "ack" && (
          <div className="w-full max-w-3xl self-stretch text-center space-y-5">
            <p className="svar-instruct">Listen to the given audio carefully. The next three questions are based on the audio.</p>
            <div className="svar-note text-left mx-auto" style={{ maxWidth: "40rem" }}>
              <ul style={{ listStyle: "disc", paddingLeft: "1.2rem" }}>
                <li>You were allowed to listen to the audio only once.</li>
                <li>You will not be able to listen to the audio again once you move on.</li>
              </ul>
            </div>
            <div className="text-[13px]">Type <b>&lsquo;Okay&rsquo;</b> in the box below to proceed to the questions.</div>
            <input className="svar-input mx-auto" style={{ maxWidth: "14rem", textAlign: "center" }}
                   value={okayText} onChange={(e) => setOkayText(e.target.value)}
                   placeholder="Okay" aria-label="Type Okay to proceed" autoFocus />
            <div>
              <button className="svar-btn" data-testid="ack-next"
                      disabled={okayText.trim().toLowerCase() !== "okay"}
                      onClick={() => ackResolver.current?.()}>Next</button>
            </div>
          </div>
        )}
        {phase === "listen" && (
          isSvar ? (
            <div className="w-full max-w-3xl self-stretch text-center space-y-5">
              <p className="svar-instruct">Listen carefully to the audio recording.</p>
              <div className="svar-wave-wrap">
                <div className="svar-wave-you">
                  <Headphones size={34} /><div style={{ fontWeight: 700, fontSize: ".8rem" }}>YOU HEAR</div>
                </div>
                <div className="svar-wave">
                  {Array.from({ length: 60 }).map((_, i) => (
                    <i key={i} style={{ height: `${20 + 60 * Math.abs(Math.sin(i * 0.7))}%` }} />
                  ))}
                </div>
              </div>
              <p className="svar-hint mx-auto">
                Press &lsquo;Play Audio&rsquo; to listen to the audio clip. You can only
                listen to the audio once.
              </p>
              <button className="svar-btn" onClick={() => { primeSpeech(); playResolver.current?.(); }}>
                Play Audio
              </button>
            </div>
          ) : (
            <>
              <AiNarrator speaking={false} />
              <p className="runner-prompt">Play the audio when ready</p>
              <button className="btn btn-primary ds-focus" onClick={() => { primeSpeech(); playResolver.current?.(); }}>
                Play audio
              </button>
            </>
          )
        )}

        {phase === "prep" && (
          isSvar ? (
            <div className="w-full max-w-3xl self-stretch text-center space-y-5">
              <p className="svar-instruct">{prepLine(item.task_type)}</p>
              {/* Speak on a Topic: the topic is the prompt text. It must be
                  shown -- you speak about it -- unlike Repeat Sentence, whose
                  prompt is withheld and heard. `question` is empty here. */}
              {(item.prompt_text || item.question) && (
                <div className="svar-qbar text-left">{item.prompt_text || item.question}</div>
              )}
              {item.key_points.length > 0 && (
                <div className="text-left mx-auto" style={{ maxWidth: "40rem" }}>
                  <div className="text-[11px] font-bold uppercase tracking-wide"
                       style={{ color: "var(--svar-navy)" }}>
                    Speaking points — suggestions
                  </div>
                  <ul style={{ color: "var(--svar-navy)", fontStyle: "italic" }}>
                    {item.key_points.map((k, n) => <li key={n}>{k}</li>)}
                  </ul>
                  <div className="text-[11px] text-muted">
                    These are only suggestions. You may also speak on other points related to the topic.
                  </div>
                </div>
              )}
              <div className="svar-record-head">
                <span className="svar-mic-tile"><Mic size={26} /></span>
                <div className="text-left">
                  <div style={{ fontWeight: 700 }}>Record your response</div>
                  <div style={{ color: "var(--svar-navy)" }}>
                    Recording Time: {item.response_seconds >= 60 ? `${Math.round(item.response_seconds/60)} min` : `${item.response_seconds} Sec`}
                  </div>
                </div>
              </div>
              <p className="svar-hint mx-auto">
                Your thinking time is currently running. Recording will
                automatically start once the thinking time is over.
              </p>
              <div className="svar-circle svar-circle--think">
                <span className="n">{seconds}</span>
              </div>
              {item.allow_skip && (
                <button className="svar-btn svar-btn--ghost"
                        title="Skip this topic. No response will be recorded for it."
                        onClick={() => { skipTopic.current = true; stopEarly.current = true; }}>
                  Skip
                </button>
              )}
              {item.skip_prep && (
                // Mettl: "If you prefer not to use the thinking time, you can
                // skip and start recording your response." Ends the think
                // countdown; the recording then starts as it would have.
                <button className="svar-btn svar-btn--ghost" data-testid="skip-thinking"
                        title="End the thinking time now and start recording."
                        onClick={() => { stopEarly.current = true; }}>
                  Skip thinking time — start recording
                </button>
              )}
            </div>
          ) : (
            <>
              <div className="countdown">{seconds}</div>
              <p className="runner-instruction">Read this. You will speak when the tone sounds.</p>
              {item.prompt_text && <p className="runner-prompt">{item.prompt_text}</p>}
            </>
          )
        )}

        {/* Nothing was recorded, and the item is not committed yet.
            A gate, not a judgement: the check that got here is a crude energy
            scan whose only job is to offer this. Nothing it decides reaches a
            score, and if the second take is silent too it goes through and the
            server reports it honestly. */}
        {retakePeak !== null && (
          <div className="w-full max-w-[42ch] text-center">
            <p className="runner-prompt">We did not hear anything</p>
            <p className="runner-instruction">
              {retakePeak < -75
                ? "Your microphone recorded silence. Check it is not muted, then try this one again."
                : "That recording was very quiet. Move closer to the microphone and try again."}
            </p>
            <div className="flex gap-2 justify-center mt-4">
              <button className="btn btn-primary ds-focus"
                      onClick={() => retakeResolver.current?.(true)}>
                Record it again
              </button>
              <button className="btn btn-ghost ds-focus"
                      onClick={() => retakeResolver.current?.(false)}>
                Move on
              </button>
            </div>
            <p className="text-[10px] text-muted mt-3 leading-relaxed">
              You get one retake on this item. It does not replay the prompt.
            </p>
          </div>
        )}

        {phase === "owed" && (
          <div className="w-full max-w-[46ch] text-center">
            <p className="runner-prompt">Some answers have not reached us</p>
            <p className="runner-instruction">{uploadNote}</p>
            <div className="flex gap-2 justify-center mt-4">
              <button className="btn btn-primary ds-focus"
                      onClick={() => { void (async () => {
                        const left = await drainQueue();
                        if (left === 0) { setUploadNote(""); void finishAnyway(); }
                      })(); }}>
                Try again
              </button>
              <button className="btn btn-ghost ds-focus"
                      onClick={() => void finishAnyway()}>
                Finish without them
              </button>
            </div>
            <p className="text-[10px] text-muted mt-3 leading-relaxed">
              Nothing has been deleted. If you finish now, those answers stay on
              this device and are not part of your score.
            </p>
          </div>
        )}

        {phase === "prompt" && (
          isSvar ? (
            <div className="w-full max-w-3xl self-stretch text-center space-y-4">
              <p className="svar-instruct">Listen carefully &mdash; the audio plays once.</p>
              <div className="svar-wave-wrap">
                <div className="svar-wave-you">
                  <Headphones size={34} /><div style={{ fontWeight: 700, fontSize: ".8rem" }}>YOU HEAR</div>
                </div>
                <div className="svar-wave">
                  {Array.from({ length: 60 }).map((_, i) => (
                    <i key={i} style={{ height: `${25 + 55 * Math.abs(Math.sin(i * 0.9 + seconds))}%` }} />
                  ))}
                </div>
              </div>
              <p style={{ color: "var(--svar-navy)", fontWeight: 600 }}>Playing&hellip;</p>
            </div>
          ) : (
            <>
              {/* The AI voice reading the prompt, given a face. */}
              <AiNarrator speaking />
              <p className="runner-prompt">Listen carefully</p>
              <p className="runner-instruction">
                This plays once — the same as the real test.
              </p>
            </>
          )
        )}

        {/* Answered by choosing or typing. The same section framing and the
            same one-shot rules as a spoken item -- only the way an answer is
            given differs. */}
        {phase === "respond" && (
          <div className="w-full max-w-[62ch] text-left">
            {item.stimulus_title && (
              <div className="text-[11px] font-bold uppercase tracking-wider text-muted mb-2">
                {item.stimulus_title}
              </div>
            )}

            {/* A reading passage is shown because reading it is the task. A
                listening passage is not -- it was played, and printing the
                words here would turn a listening test into a reading one.

                A reconstruction passage is shown and then taken away, which
                is the measurement rather than a flourish: what is being
                tested is whether the ideas survive without the text. */}
            {item.stimulus_text && stimulusLeft !== 0 && (
              <>
                {stimulusLeft !== null && (
                  <p className="text-xs text-muted mb-2">
                    Read this. It disappears in {stimulusLeft}s, and then you
                    write what it said.
                  </p>
                )}
                <div className="ds-inset p-3 mb-4 text-sm leading-loose whitespace-pre-line max-h-[38vh] overflow-y-auto">
                  {item.stimulus_text}
                </div>
              </>
            )}

            {stimulusLeft === 0 && (
              <p className="ds-inset p-3 mb-4 text-sm text-muted">
                The passage has gone. Write what it said, in your own words —
                you are not expected to remember the wording.
              </p>
            )}

            {item.response_mode === "select" ? (
              isSvar ? (
                <>
                  {item.instructions && (
                    <p className="svar-instruct mb-3">{item.instructions}</p>
                  )}
                  <div className="svar-qbar mb-4">{item.question}</div>
                  <div className="text-[13px] font-bold mb-2" style={{ color: "var(--svar-navy)" }}>Options:</div>
                  <div className="space-y-2">
                    {item.options.map((option, n) => (
                      <button key={n} type="button" onClick={() => setChoice(n)}
                              className={`svar-optrow${choice === n ? " is-sel" : ""}`}>
                        <span className="svar-radio">{choice === n && <span className="dot" />}</span>
                        {option}
                      </button>
                    ))}
                  </div>
                </>
              ) : (
                <>
                  <p className="text-base font-semibold mb-3">{item.question}</p>
                  <div className="space-y-2">
                    {item.options.map((option, n) => (
                      <button
                        key={n}
                        onClick={() => setChoice(n)}
                        className="w-full text-left ds-inset p-3 text-sm ds-focus transition-colors"
                        style={choice === n ? {
                          borderColor: "var(--primary)",
                          background: "color-mix(in srgb, var(--primary) 10%, transparent)",
                        } : undefined}
                      >
                        {option}
                      </button>
                    ))}
                  </div>
                </>
              )
            ) : isSvar && item.task_type === "sentence_completion" ? (
              // The one-word gap gets the reference's keyboard tile and a
              // single-line input. Only sentence completion: a dictation, an
              // email or a reconstruction is whole sentences and needs the
              // full editor below, whatever skin the format wears.
              <div className="text-center space-y-4">
                <div className="svar-type-tile mx-auto">
                  <svg width="40" height="30" viewBox="0 0 40 30" fill="none" stroke="var(--svar-navy)" strokeWidth="2"><rect x="1" y="6" width="38" height="20" rx="2"/><path d="M6 12h2M12 12h2M18 12h2M24 12h2M30 12h2M9 18h14"/></svg>
                  <span style={{ fontSize: ".8rem" }}>Type</span>
                </div>
                <p className="svar-instruct">Fill in the blank to complete the sentence.</p>
                <div className="svar-qbar text-left">{item.question || item.prompt_text}</div>
                <input className="svar-input" value={written} autoFocus
                       onChange={(e) => setWritten(e.target.value)}
                       placeholder="Type your answer" />
              </div>
            ) : (
              <>
                <p className="text-base font-semibold mb-1">{item.question || item.prompt_text}</p>
                {item.scenario && (
                  <p className="text-xs text-muted leading-relaxed mb-3">{item.scenario}</p>
                )}
                {/* What a competent answer has to contain. Shown because for
                    a composing task it is the brief -- a reconstruction sends
                    none, since there the points are the answer. */}
                {item.key_points.length > 0 && (
                  <ul className="text-xs text-muted leading-relaxed mb-3 list-disc pl-5 space-y-0.5">
                    {item.key_points.map((point, n) => <li key={n}>{point}</li>)}
                  </ul>
                )}
                <textarea
                  value={written}
                  onChange={(e) => setWritten(e.target.value)}
                  rows={10}
                  placeholder="Write your answer here…"
                  className="w-full ds-inset p-3 bg-transparent text-sm leading-relaxed outline-none resize-y ds-focus"
                />
                <div className="text-[11px] text-muted mt-1">
                  {written.trim() ? written.trim().split(/\s+/).length : 0} words
                  {item.min_words > 0 && ` · at least ${item.min_words} asked for`}
                </div>
              </>
            )}

            {notice && (
              <p className="text-xs mt-3" style={{ color: "var(--rag-amber)" }}>
                {notice}
              </p>
            )}

            <div className={isSvar ? "text-center mt-6" : ""}>
              <button
                onClick={() => answerResolver.current?.({ index: choice, text: written })}
                disabled={item.response_mode === "select"
                  ? choice === null
                  : written.trim().length === 0}
                className={isSvar ? "svar-btn" : "btn btn-primary w-full ds-focus mt-4"}
              >
                {isSvar ? "Next" : "Submit and continue"}
              </button>
            </div>
            {!isSvar && (
              <p className="text-[10px] text-muted mt-2 text-center">
                You cannot come back to this question.
              </p>
            )}
          </div>
        )}

        {phase === "answer" && (
          isSvar ? (
            <div className="w-full max-w-3xl self-stretch text-center space-y-5">
              {item.prompt_text && <div className="svar-qbar text-left">{item.prompt_text}</div>}
              {item.key_points.length > 0 && (
                <ul className="text-left mx-auto" style={{ maxWidth: "40rem", color: "var(--svar-navy)", fontStyle: "italic" }}>
                  {item.key_points.map((k, n) => <li key={n}>{k}</li>)}
                </ul>
              )}
              <div className="svar-circle svar-circle--record is-live">
                <span className="lbl">Recording</span>
                <span className="n">{seconds}</span>
                <span className="lbl">Sec left</span>
              </div>
              <Meter level={level} accent="var(--svar-navy)" />
              {notice && <p style={{ color: "var(--svar-navy)" }}>{notice}</p>}
              <button className="svar-btn svar-btn--ghost"
                      onClick={() => { endReason.current = "user_ended"; stopEarly.current = true; }}>
                <Square size={13} /> Stop &amp; submit
              </button>
            </div>
          ) : (
            <>
              <div className={`countdown ${seconds <= 3 ? "countdown-critical" : seconds <= 10 ? "countdown-warn" : ""}`}>
                {seconds}
              </div>
              {item.prompt_text
                ? <p className="runner-prompt">{item.prompt_text}</p>
                : <p className="runner-prompt" data-testid="answer-line">{answerLine(item.task_type)}</p>}
              {notice && (
                <p className="runner-instruction" style={{ color: "var(--rag-amber)" }}>
                  {notice}
                </p>
              )}
              <Meter level={level} />
              <button
                onClick={() => { endReason.current = "user_ended"; stopEarly.current = true; }}
                className="btn btn-ghost ds-focus"
              >
                <Square size={13} /> I have finished
              </button>
            </>
          )
        )}

        {phase === "saving" && (
          <>
            <Loader2 size={22} className="animate-spin text-muted" />
            <p className="runner-instruction">Saving your answer…</p>
          </>
        )}

        {phase === "submitting" && (
          <>
            <Loader2 size={22} className="animate-spin text-muted" />
            <p className="runner-prompt">Scoring your simulation</p>
            <p className="runner-instruction">This takes a few seconds.</p>
          </>
        )}
      </div>

      <footer className="px-4 py-2 border-t border-border shrink-0">
        <div className="flex items-center justify-between">
          <div className="ds-track flex-1">
            <div className="ds-fill" style={{ width: `${(index / total) * 100}%` }} />
          </div>
          <div className="ml-3 shrink-0">
            <DataUsageIndicator itemCount={total} />
          </div>
        </div>
      </footer>
    </div>
  );
}

/** The SVAR blue section banner text: which lettered section a title is in. */
/** What the Start-Recording screen asks for, by task. The old line was a
 *  binary on prompt_text and told everyone without one to "repeat the
 *  sentence exactly" -- actively wrong for a heard question, a conversation,
 *  a story, and both spoken grammar tasks. The instruction is the one thing
 *  a candidate must not have to guess. */
function armedLine(taskType: string): string {
  switch (taskType) {
    case "read_aloud":
      return "Read the following carefully and then say it out loud.";
    case "repeat_sentence":
      return "Repeat the sentence you heard, exactly.";
    case "short_answer":
      return "Answer the question you heard, out loud.";
    case "conversation_question":
    case "passage_question":
      return "Give your spoken response to what you just heard.";
    case "story_retell":
      return "Retell the story you heard, in your own words.";
    case "spoken_completion":
      return "Say the complete sentence aloud, filling in the missing word.";
    case "spoken_correction":
      return "Say the corrected sentence aloud.";
    case "open_response":
      return "Speak your answer to the question you heard.";
    default:
      return "When you are ready, start recording your answer.";
  }
}

/** The thinking-time screen's ask. "Speak on the topic" was written for
 *  SVAR's Section B and is wrong for a prepared read-aloud or a sentence
 *  build, both of which now share this screen. */
function prepLine(taskType: string): string {
  switch (taskType) {
    case "read_aloud":
      return "Read the sentence below. Recording starts when the timer ends.";
    case "sentence_build":
      return "Rearrange the word groups below into one sentence. Say it when recording starts.";
    default:
      return "Speak on the topic given below.";
  }
}

/** "Section A1 - Read & Say Aloud" -> {letter:"A", name:...}; also "Part B".
 *
 *  The letter groups subsections under one banner/introduction. A title with
 *  no letter falls back to the whole title as its own group, so two unrelated
 *  sections can never be collapsed into one blank-letter group.
 */
function svarSectionBanner(title: string): { letter: string; name: string } {
  const m = /\b(?:section|part)\s*-?\s*([a-h])(\d*)\b/i.exec(title);
  if (!m) {
    // No letter: the whole title is its own group, so two unrelated sections
    // can never be collapsed into one blank-letter group.
    return { letter: title, name: title };
  }
  const letter = m[1].toUpperCase();
  const numbered = m[2] !== "";
  const tail = title.includes("-")
    ? title.slice(title.indexOf("-") + 1).trim() : "";
  // A numbered subsection (SVAR's A1/A2/C1...) shows the stable family name,
  // so the banner does not flicker between "Read & Say Aloud (Sentence)" and
  // "(Paragraph)" mid-section. An unnumbered section shows its own tail.
  const family: Record<string, string> = {
    A: "Reading & Listening", B: "Speaking", C: "Grammar", D: "Comprehension",
  };
  const name = numbered
    ? (family[letter] ?? (tail || title))
    : (tail || family[letter] || title);
  return { letter, name };
}


function Meter({ level, accent = "var(--primary)" }: { level: number; accent?: string }) {
  const lit = Math.round(levelToFraction(level) * 24);
  return (
    <div className="level-meter" aria-hidden>
      {Array.from({ length: 24 }).map((_, i) => (
        <span key={i} className="level-bar"
              style={{
                height: `${20 + (i / 24) * 80}%`,
                opacity: i < lit ? 1 : 0.12,
                background: i > 20 ? "var(--rag-red)" : accent,
              }} />
      ))}
    </div>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return <div className="runner"><div className="runner-body">{children}</div></div>;
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

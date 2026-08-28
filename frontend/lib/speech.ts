/**
 *  Two things the browser needs to know about a candidate's own voice, and
 *  neither of them is a score.
 *
 *  There is already a VAD. It runs on the server, inside ``SCORING_PATH``,
 *  and it produces `onset_ms`, `speech_ms` and the latency and fluency
 *  measures. It is hashed for the validation study and it is the only thing
 *  whose output reaches a report.
 *
 *  **So what is this for.** Two questions the server's VAD answers too late
 *  to be useful:
 *
 *  1. *Did anything get recorded at all?* The server can only say so after
 *     the upload, by which time the item is submitted and the candidate has
 *     moved on. Asked here, a dead microphone becomes one re-record instead
 *     of a zero.
 *  2. *Have they finished speaking?* The runner waits out the full response
 *     window on every item, where the tests it imitates advance when the
 *     candidate stops. That is why SVAR-style runs eighteen minutes against a
 *     fifteen-minute target.
 *
 *  **The boundary, stated once and enforced by keeping this module free of
 *  anything that could cross it.** Nothing here produces a score, writes a
 *  dimension, or changes a single byte of what is uploaded. It gates and it
 *  paces. The audio the server receives is the same audio it would have
 *  received, minus trailing silence the candidate had already stopped filling
 *  — and the server's own VAD runs on it exactly as before. Two detectors,
 *  different jobs, and only one of them can affect a result.
 *
 *  Deliberately cruder than the server's, too: RMS energy over a frame, no
 *  model. A cheap detector that is wrong occasionally is fine for a gate that
 *  offers a re-record. It would not be fine for a measurement, which is why
 *  it is not one.
 */

/** Below this, a frame is silence.
 *
 *  −55 dBFS is well under conversational speech at a normal microphone gain
 *  (roughly −30 to −15) and above the noise floor of a quiet room (−65 and
 *  down). Deliberately generous: a false "you said nothing" shown to somebody
 *  who did speak is a worse failure than letting a genuinely silent recording
 *  through, because the second is caught by the server and reported honestly
 *  while the first calls the candidate a liar about their own answer.
 */
export const SILENCE_DBFS = -55;

/** The opening stretch of every recording that neither gate listens to.
 *  The start tone plays through the speakers a moment before the recorder
 *  starts, and on a laptop without headphones its tail (plus the stream's
 *  own start transient, -18 dBFS measured) lands in the first few hundred
 *  milliseconds of capture -- loud enough to count as "speech" and so to
 *  defeat the nothing-heard check (hardware UAT, D1). */
export const LEADING_GUARD_MS = 500;

/** How much speech makes a recording an attempt rather than a cough. */
export const MIN_SPEECH_MS = 250;

/** Frame size for the energy scan. 20 ms is the usual VAD frame. */
export const FRAME_MS = 20;

export interface SpeechCheck {
  /** True if anything above the floor lasted long enough to be speech. */
  heardSomething: boolean;
  speechMs: number;
  /** Loudest frame, for telling somebody their microphone is too quiet. */
  peakDbfs: number;
}

function frameDbfs(samples: Float32Array, from: number, to: number): number {
  let sum = 0;
  for (let i = from; i < to; i += 1) sum += samples[i] * samples[i];
  const rms = Math.sqrt(sum / Math.max(1, to - from));
  return rms > 0 ? 20 * Math.log10(rms) : -120;
}

/**
 *  Was anything said?
 *
 *  Counts frames above the floor rather than looking at overall RMS: a single
 *  loud click in three seconds of nothing has a respectable RMS and is not
 *  speech.
 */
export function inspect(samples: Float32Array, sampleRate: number,
                        floorDbfs = SILENCE_DBFS,
                        guardMs = LEADING_GUARD_MS): SpeechCheck {
  const frame = Math.max(1, Math.round((sampleRate * FRAME_MS) / 1000));
  const guard = Math.round((sampleRate * guardMs) / 1000);
  let speechFrames = 0;
  let peak = -120;

  for (let start = 0; start + frame <= samples.length; start += frame) {
    const db = frameDbfs(samples, start, start + frame);
    if (db > peak) peak = db;
    if (start >= guard && db >= floorDbfs) speechFrames += 1;
  }

  const speechMs = speechFrames * FRAME_MS;
  return {
    heardSomething: speechMs >= MIN_SPEECH_MS,
    speechMs,
    peakDbfs: Math.round(peak * 10) / 10,
  };
}

// --------------------------------------------------------------------------
// Adaptive advancement
// --------------------------------------------------------------------------

/** Trailing silence that means "finished", not "thinking".
 *
 *  Under a second cuts people off between clauses; much over four and the
 *  saving disappears. Two windows rather than one, because the tasks are not
 *  the same speech act:
 *
 *  * **Scripted** items (read a sentence, repeat it, say the corrected one) —
 *    the target is short and known; once the candidate stops they are done.
 *    Three seconds: brisk, but a 2–3-second breath mid-sentence survives it,
 *    which the UAT acceptance rule requires.
 *  * **Composed** speech (a topic, a story retold, a conversation answer) —
 *    thinking pauses are part of speaking, and ending the recording during
 *    one throws away the rest of the answer. Four and a half seconds.
 *
 *  The 1800 ms single value this replaces was a guess whose own comment
 *  admitted it; the backend's silence analysis (test_silence.py) shows a
 *  2-second pause followed by more speech at that threshold means somebody
 *  was cut off. The response window remains the absolute ceiling either way.
 */
export const TRAILING_SILENCE_MS = 3000;
export const TRAILING_SILENCE_COMPOSED_MS = 4500;

const COMPOSED_TASKS = new Set([
  "open_response", "story_retell", "conversation_question", "passage_question",
]);

/** "Never on silence": the window is a fixed maximum and only the clock or
 *  the candidate ends the item. */
export const FIXED_WINDOW_MS = Number.POSITIVE_INFINITY;

/** The trailing-silence window for a task type.
 *
 *  A section whose window must run fixed (SVAR-style Speak on the Topic: a
 *  candidate may pause, think and resume; only the clock or Stop ends it)
 *  says so with its `fixed_window` flag -- see `windowFor`. */
export function trailingMsFor(taskType: string): number {
  return COMPOSED_TASKS.has(taskType)
    ? TRAILING_SILENCE_COMPOSED_MS : TRAILING_SILENCE_MS;
}

/** The window rule for one runner item: fixed where the section says so,
 *  adaptive by task type everywhere else. */
export function windowFor(item: { task_type: string; fixed_window?: boolean }): number {
  return item.fixed_window ? FIXED_WINDOW_MS : trailingMsFor(item.task_type);
}

/** State a caller threads through frame by frame. Deliberately plain data,
 *  so the decision function is pure and every timing case is a unit test. */
export interface TalkState {
  /** True once at least MIN_SPEECH_MS of speech has been heard. Never goes
   *  back to false. Sustained, not a single frame: with a floor set just
   *  above the room, one keyboard click or cough would otherwise "start" the
   *  item and three seconds of thinking would then end it. */
  started: boolean;
  /** Milliseconds of above-floor audio heard so far. */
  speechMs: number;
  /** Milliseconds of continuous silence since the last speech frame. */
  silenceMs: number;
  /** Total elapsed since the tone. */
  elapsedMs: number;
}

export const FRESH: TalkState = { started: false, speechMs: 0, silenceMs: 0, elapsedMs: 0 };

/** Fold one frame's loudness into the state. */
export function observe(state: TalkState, dbfs: number, frameMs: number,
                        floorDbfs = SILENCE_DBFS,
                        guardMs = LEADING_GUARD_MS): TalkState {
  const speaking = dbfs >= floorDbfs && state.elapsedMs >= guardMs;
  const speechMs = speaking ? state.speechMs + frameMs : state.speechMs;
  return {
    started: state.started || speechMs >= MIN_SPEECH_MS,
    speechMs,
    silenceMs: speaking ? 0 : state.silenceMs + frameMs,
    elapsedMs: state.elapsedMs + frameMs,
  };
}

/**
 *  Should the item advance now?
 *
 *  Two rules, and the first is the one that protects the candidate:
 *
 *  * **Speech must have happened.** Silence before the first word is somebody
 *    thinking, and advancing through it would end the item before they
 *    started. This is why `started` exists rather than just watching a
 *    silence counter.
 *  * **The configured window is still the ceiling.** Nothing here shortens an
 *    item below what the admin set; it only declines to sit through trailing
 *    silence after the answer has finished.
 */
export function shouldAdvance(state: TalkState, ceilingMs: number,
                              trailingMs = TRAILING_SILENCE_MS): boolean {
  if (state.elapsedMs >= ceilingMs) return true;
  if (!state.started) return false;
  return state.silenceMs >= trailingMs;
}

/** Why shouldAdvance fired — for the truth the report tells later.
 *
 *  The ceiling branch IS the window expiring: the level callback usually
 *  crosses it a frame before the wall-clock countdown does, and labelling
 *  that "auto_advance" made every real timeout on a mic-armed item look
 *  like a deliberate finish, so no timeout was ever reported (found live,
 *  2026-08-24). Only a silence advance before the ceiling is the adaptive
 *  early finish. */
export function advanceReason(state: TalkState, ceilingMs: number)
    : "window_expired" | "auto_advance" {
  return state.elapsedMs >= ceilingMs ? "window_expired" : "auto_advance";
}

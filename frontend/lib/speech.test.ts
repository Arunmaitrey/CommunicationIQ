/**
 *  The silence gate and adaptive advancement, frame by frame.
 *
 *  Both are pure functions over synthetic audio and synthetic frames, so
 *  every timing case is exact. The one that matters most is the negative:
 *  silence *before* speech must never advance the item, because that is
 *  somebody thinking and cutting them off is worse than any amount of saved
 *  time.
 */
import { describe, expect, it } from "vitest";

import {
  advanceReason,
  FRESH, MIN_SPEECH_MS, SILENCE_DBFS, TRAILING_SILENCE_MS, inspect, observe,
  shouldAdvance,
} from "./speech";

const RATE = 16000;

/** Audio at a given loudness, in milliseconds. */
function tone(ms: number, dbfs: number, rate = RATE): Float32Array {
  const n = Math.round((rate * ms) / 1000);
  const amplitude = 10 ** (dbfs / 20);
  const out = new Float32Array(n);
  for (let i = 0; i < n; i += 1) {
    // A square wave, so every sample sits at the requested amplitude and the
    // RMS of any frame is exactly it. A sine would make the expected dBFS
    // depend on where a frame boundary happened to fall.
    out[i] = i % 2 === 0 ? amplitude : -amplitude;
  }
  return out;
}

function join(...parts: Float32Array[]): Float32Array {
  const total = parts.reduce((n, p) => n + p.length, 0);
  const out = new Float32Array(total);
  let at = 0;
  for (const p of parts) { out.set(p, at); at += p.length; }
  return out;
}

describe("did anything get recorded", () => {
  it("hears ordinary speech", async () => {
    // 2.5 s of speech; the first LEADING_GUARD_MS is not counted.
    const check = inspect(tone(2500, -20), RATE);
    expect(check.heardSomething).toBe(true);
    expect(check.speechMs).toBeGreaterThan(1500);
  });

  it("hears a very quiet speaker rather than calling them silent", () => {
    // The false positive that matters. Somebody sitting back from a laptop
    // microphone lands around -45 dBFS, and telling them they said nothing
    // when they answered in full is the worst thing this gate could do.
    const check = inspect(tone(2000, -45), RATE);
    expect(check.heardSomething).toBe(true);
  });

  it("reports a dead microphone as silence", () => {
    const check = inspect(new Float32Array(RATE * 2), RATE);
    expect(check.heardSomething).toBe(false);
    expect(check.speechMs).toBe(0);
  });

  it("reports a quiet room as silence", () => {
    // Room noise well below the floor. Nothing was said.
    const check = inspect(tone(3000, -70), RATE);
    expect(check.heardSomething).toBe(false);
  });

  it("does not mistake one click for an answer", () => {
    // A single loud sample in three seconds of nothing has a respectable
    // overall RMS. Counting frames instead of averaging is what catches this.
    const clip = new Float32Array(RATE * 3);
    clip[1000] = 0.9;
    const check = inspect(clip, RATE);
    expect(check.heardSomething).toBe(false);
  });

  it("needs more than a cough", () => {
    const brief = inspect(join(tone(100, -20), new Float32Array(RATE)), RATE);
    expect(brief.speechMs).toBeLessThan(MIN_SPEECH_MS);
    expect(brief.heardSomething).toBe(false);
  });

  it("reports the peak, so a too-quiet microphone can be named", () => {
    const check = inspect(tone(500, -40), RATE);
    expect(check.peakDbfs).toBeGreaterThan(-42);
    expect(check.peakDbfs).toBeLessThan(-38);
  });

  it("an empty buffer is silence, not a crash", () => {
    expect(inspect(new Float32Array(0), RATE).heardSomething).toBe(false);
  });
});

// --------------------------------------------------------------------------

const FRAME = 20;
const LOUD = -20;
const QUIET = -80;

/** Run a script of [loudness, milliseconds] pairs through the state fold. */
function play(script: [number, number][], ceilingMs: number,
              trailingMs = TRAILING_SILENCE_MS) {
  let state = FRESH;
  let advancedAt: number | null = null;
  for (const [dbfs, ms] of script) {
    for (let t = 0; t < ms; t += FRAME) {
      state = observe(state, dbfs, FRAME);
      if (advancedAt === null && shouldAdvance(state, ceilingMs, trailingMs)) {
        advancedAt = state.elapsedMs;
      }
    }
  }
  return { state, advancedAt };
}

describe("adaptive advancement", () => {
  it("never advances early on silence before speech", () => {
    // The rule that protects a candidate who is thinking. Ten seconds of
    // nothing, and the item runs to its ceiling rather than ending.
    const { advancedAt } = play([[QUIET, 10_000]], 20_000);
    expect(advancedAt).toBeNull();
  });

  it("advances after trailing silence once speech has happened", () => {
    const { advancedAt } = play([[LOUD, 3000], [QUIET, 4000]], 30_000);
    expect(advancedAt).toBe(3000 + TRAILING_SILENCE_MS);
  });

  it("does not advance on a pause mid-answer", () => {
    // Short pauses are how people talk. A gap under the trailing window must
    // not end the item -- the candidate has more to say.
    const { advancedAt } = play(
      [[LOUD, 1500], [QUIET, 800], [LOUD, 1500], [QUIET, 700], [LOUD, 1000]],
      30_000);
    expect(advancedAt).toBeNull();
  });

  it("advances at the ceiling when somebody talks all the way through", () => {
    const { advancedAt } = play([[LOUD, 20_000]], 15_000);
    expect(advancedAt).toBe(15_000);
  });

  it("advances at the ceiling when nothing is ever said", () => {
    // The item still ends -- on its clock, not early. A silent recording is
    // then caught by the pre-upload gate, which offers a re-record.
    const { advancedAt } = play([[QUIET, 20_000]], 15_000);
    expect(advancedAt).toBe(15_000);
  });

  it("never shortens an item below its ceiling for a candidate still talking", () => {
    // Restated as the invariant an admin cares about: the configured window
    // is a ceiling that adaptive advancement may reach early only when the
    // person has stopped, never a window it may cut into while they speak.
    for (const ceiling of [5000, 15_000, 40_000]) {
      const { advancedAt } = play([[LOUD, ceiling + 5000]], ceiling);
      expect(advancedAt).toBe(ceiling);
    }
  });

  it("silence immediately after a single word still waits the full trailing window", () => {
    // The word lands after the leading guard (the start tone's window).
    const { advancedAt } = play([[QUIET, 500], [LOUD, 300], [QUIET, 5000]], 30_000);
    expect(advancedAt).toBe(800 + TRAILING_SILENCE_MS);
  });

  it("the trailing window is configurable and honoured exactly", () => {
    const { advancedAt } = play([[LOUD, 1000], [QUIET, 3000]], 30_000, 1200);
    expect(advancedAt).toBe(2200);
  });

  it("started never goes back to false", () => {
    const { state } = play([[QUIET, 500], [LOUD, 400], [QUIET, 5000]], 30_000);
    expect(state.started).toBe(true);
  });

  it("a single click does not start the item; sustained speech does", () => {
    // One 20 ms frame above the floor is a click, not a candidate speaking.
    const click = play([[QUIET, 500], [LOUD, 20], [QUIET, 5000]], 30_000);
    expect(click.state.started).toBe(false);
    expect(click.advancedAt).toBeNull();
    const word = play([[QUIET, 500], [LOUD, MIN_SPEECH_MS], [QUIET, 5000]], 30_000);
    expect(word.state.started).toBe(true);
  });

  it("a frame exactly at the threshold counts as speech", () => {
    // Stated so a change to the comparison is deliberate rather than a
    // one-character accident that stops the gate working near the floor.
    const past = { ...FRESH, elapsedMs: 1000 };   // beyond the leading guard
    let at = observe(past, SILENCE_DBFS, FRAME);
    expect(at.silenceMs).toBe(0);
    expect(at.speechMs).toBe(FRAME);
    for (let t = FRAME; t < MIN_SPEECH_MS; t += FRAME) at = observe(at, SILENCE_DBFS, FRAME);
    expect(at.started).toBe(true);
  });
});

// --------------------------------------------------------------------------
// Regression: the pacing clock must count REAL time, not a fixed frame size.
//
// The bug: the runner called observe(state, dbfs, 20) on every onLevel, but an
// AudioWorklet delivers a 128-sample render quantum -- ~2.67 ms at 48 kHz, not
// 20 ms. So elapsedMs raced ~7.5x ahead of the clock and shouldAdvance hit the
// ceiling after ~2 s of real audio, ending every recording in a few seconds no
// matter what the on-screen timer said. The fix passes each frame's real
// duration (frame.length / sampleRate) instead of a constant.
// --------------------------------------------------------------------------
describe("pacing is frame-rate independent (worklet clock regression)", () => {
  const SR = 48_000;
  const WORKLET_QUANTUM = 128;                       // samples per render quantum
  const realFrameMs = (WORKLET_QUANTUM / SR) * 1000; // ≈ 2.667 ms

  it("reaches a 15 s ceiling at ~15 s of real audio when given real frame ms", () => {
    const ceiling = 15_000;
    const frames = Math.round(ceiling / realFrameMs) + 200;
    let state = FRESH;
    let advancedAt: number | null = null;
    for (let i = 0; i < frames; i += 1) {
      state = observe(state, LOUD, realFrameMs);     // continuous speech
      if (advancedAt === null && shouldAdvance(state, ceiling)) advancedAt = state.elapsedMs;
    }
    // Within a single frame of the true ceiling -- not 7x early.
    expect(advancedAt).toBeGreaterThanOrEqual(ceiling);
    expect(advancedAt).toBeLessThan(ceiling + realFrameMs + 0.001);
  });

  it("proves the old fixed-20 ms value ended the item in ~2 s of real audio", () => {
    // Frames still arrive every ~2.67 ms of real audio, but each is (wrongly)
    // counted as 20 ms. Assert the ceiling is hit far too early in real time.
    const ceiling = 15_000;
    const frames = Math.round(ceiling / realFrameMs);
    let state = FRESH;
    let realMsAtCeiling: number | null = null;
    for (let i = 0; i < frames; i += 1) {
      state = observe(state, LOUD, 20);              // the defect
      if (realMsAtCeiling === null && shouldAdvance(state, ceiling)) {
        realMsAtCeiling = (i + 1) * realFrameMs;     // real audio elapsed
      }
    }
    expect(realMsAtCeiling).not.toBeNull();
    expect(realMsAtCeiling as number).toBeLessThan(3_000); // "a few seconds"
  });
});

describe("task-aware trailing windows (UAT acceptance rule)", () => {
  it("a 2-3 second thinking pause never ends a recording", async () => {
    const { trailingMsFor } = await import("./speech");
    // The acceptance rule from real-candidate UAT: pausing for 2-3 seconds
    // and continuing must not terminate the recording, on any task.
    for (const task of ["read_aloud", "repeat_sentence", "spoken_completion",
                        "spoken_correction", "sentence_build", "short_answer",
                        "open_response", "story_retell",
                        "conversation_question", "passage_question"]) {
      const win = trailingMsFor(task);
      const { advancedAt } = play(
        [[LOUD, 2000], [QUIET, 2900], [LOUD, 2000]], 60_000, win);
      expect(advancedAt, `${task} cut off a 2.9s pause (window ${win}ms)`)
        .toBeNull();
    }
  });

  it("composed speech gets a longer window than scripted items", async () => {
    const { trailingMsFor, TRAILING_SILENCE_MS, TRAILING_SILENCE_COMPOSED_MS } =
      await import("./speech");
    expect(trailingMsFor("open_response")).toBe(TRAILING_SILENCE_COMPOSED_MS);
    expect(trailingMsFor("story_retell")).toBe(TRAILING_SILENCE_COMPOSED_MS);
    expect(trailingMsFor("repeat_sentence")).toBe(TRAILING_SILENCE_MS);
    expect(TRAILING_SILENCE_COMPOSED_MS).toBeGreaterThan(TRAILING_SILENCE_MS);
  });
});


describe("fixed speaking window is a section flag (SVAR-style Speak on the Topic, PM decision)", () => {
  it("never ends on silence: a 6 s pause, then more speech, then silence, reaches the ceiling", async () => {
    const { windowFor, FIXED_WINDOW_MS } = await import("./speech");
    const win = windowFor({ task_type: "open_response", fixed_window: true });
    expect(win).toBe(FIXED_WINDOW_MS);
    const { advancedAt } = play(
      [[LOUD, 5000], [QUIET, 6000], [LOUD, 5000], [QUIET, 20_000]], 60_000, win);
    // Only the clock ends it -- at 36 s of audio nothing has happened yet.
    expect(advancedAt).toBeNull();
    const full = play([[LOUD, 5000], [QUIET, 60_000]], 60_000, win);
    expect(full.advancedAt).toBe(60_000);
  });

  it("leaves every unflagged item on adaptive advancement, whatever its format", async () => {
    const { windowFor, trailingMsFor, TRAILING_SILENCE_COMPOSED_MS, TRAILING_SILENCE_MS } =
      await import("./speech");
    expect(windowFor({ task_type: "open_response" })).toBe(TRAILING_SILENCE_COMPOSED_MS);
    expect(windowFor({ task_type: "open_response", fixed_window: false })).toBe(TRAILING_SILENCE_COMPOSED_MS);
    expect(trailingMsFor("open_response")).toBe(TRAILING_SILENCE_COMPOSED_MS);
    expect(windowFor({ task_type: "read_aloud" })).toBe(TRAILING_SILENCE_MS);
    expect(windowFor({ task_type: "repeat_sentence" })).toBe(TRAILING_SILENCE_MS);
  });
});


describe("noise-relative speech floor (hardware UAT D1)", () => {
  it("sits NOISE_MARGIN_DB above the room, never below the fixed floor", async () => {
    const { speechFloorFor, SILENCE_DBFS, NOISE_MARGIN_DB } = await import("./speech");
    expect(speechFloorFor(null)).toBe(SILENCE_DBFS);
    expect(speechFloorFor(undefined)).toBe(SILENCE_DBFS);
    expect(speechFloorFor(-70)).toBe(SILENCE_DBFS);
    // The UAT room: -50.7 dBFS, called "quiet enough" by the setup check.
    expect(speechFloorFor(-50.7)).toBeCloseTo(-50.7 + NOISE_MARGIN_DB, 5);
    // With the room's ceiling known, the floor sits above *that*: the
    // quietest tenth of the room is not what a speech frame has to beat.
    expect(speechFloorFor(-50.7, -44.2)).toBeCloseTo(-44.2 + NOISE_MARGIN_DB, 5);
    expect(speechFloorFor(-50.7, null)).toBeCloseTo(-50.7 + NOISE_MARGIN_DB, 5);
  });

  it("a -50.7 dBFS room is silence with the room floor, and was speech without it", async () => {
    const { observe, inspect, speechFloorFor, FRESH } = await import("./speech");
    const room = -50.7, floor = speechFloorFor(room);
    const past = { ...FRESH, elapsedMs: 1000 };   // beyond the leading guard
    // Adaptive advance: room noise must not count as speech.
    let withRoom = past, withFixed = past;
    for (let t = 0; t < 400; t += 20) { withRoom = observe(withRoom, room + 1, 20, floor); withFixed = observe(withFixed, room + 1, 20); }
    expect(withRoom.started).toBe(false);
    expect(withFixed.started).toBe(true);
    // Silence gate: three seconds of room noise is "nothing heard".
    const noise = tone(3000, room + 1);
    expect(inspect(noise, RATE, floor).heardSomething).toBe(false);
    expect(inspect(noise, RATE).heardSomething).toBe(true);
    // Real speech well above the room still counts.
    expect(inspect(tone(2000, -30), RATE, floor).heardSomething).toBe(true);
    let talking = past;
    for (let t = 0; t < 400; t += 20) talking = observe(talking, -30, 20, floor);
    expect(talking.started).toBe(true);
  });
});


describe("leading guard: the start tone cannot count as speech (hardware UAT D1)", () => {
  it("a loud 300 ms at the very start followed by silence is 'nothing heard'", async () => {
    const { inspect, LEADING_GUARD_MS } = await import("./speech");
    const clip = join(tone(300, -18), new Float32Array(RATE * 14));
    expect(LEADING_GUARD_MS).toBeGreaterThanOrEqual(300);
    expect(inspect(clip, RATE).heardSomething).toBe(false);
    // ...but real speech after the guard is still heard.
    const spoken = join(tone(300, -18), new Float32Array(RATE), tone(1500, -25), new Float32Array(RATE * 5));
    expect(inspect(spoken, RATE).heardSomething).toBe(true);
  });

  it("adaptive advancement does not arm on the tone either", async () => {
    const { observe, shouldAdvance, FRESH, TRAILING_SILENCE_MS } = await import("./speech");
    let state = FRESH;
    for (let t = 0; t < 300; t += 20) state = observe(state, -18, 20);   // tone bleed
    expect(state.started).toBe(false);
    for (let t = 0; t < 5000; t += 20) state = observe(state, -80, 20);  // thinking
    expect(shouldAdvance(state, 15_000, TRAILING_SILENCE_MS)).toBe(false);
    for (let t = 0; t < 1000; t += 20) state = observe(state, -20, 20);  // speech
    expect(state.started).toBe(true);
    for (let t = 0; t < 3200; t += 20) state = observe(state, -80, 20);  // done
    expect(shouldAdvance(state, 15_000, TRAILING_SILENCE_MS)).toBe(true);
  });
});

describe("why the advance fired", () => {
  // Found live: the level callback crosses the ceiling a frame before the
  // wall-clock countdown, so labelling every advance "auto_advance" made
  // real timeouts unreportable. The ceiling branch is the window expiring.
  it("reaching the ceiling is a window expiry, not an early finish", () => {
    const state = { started: true, speechMs: 39000, silenceMs: 0, elapsedMs: 40001 };
    expect(shouldAdvance(state, 40000)).toBe(true);
    expect(advanceReason(state, 40000)).toBe("window_expired");
  });

  it("a silence advance before the ceiling is the adaptive early finish", () => {
    const state = { started: true, speechMs: 9000, silenceMs: 3000, elapsedMs: 12500 };
    expect(shouldAdvance(state, 40000)).toBe(true);
    expect(advanceReason(state, 40000)).toBe("auto_advance");
  });
});

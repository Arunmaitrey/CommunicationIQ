/**
 *  The recovery path, against a real server and a real IndexedDB.
 *
 *  Every other test in this directory injects the transport. This one does
 *  not: it uploads to a running API, over HTTP, using the same
 *  `deliverRecording` and `drainPending` the runner calls. It exists because
 *  a scenario is not proven by unit-testing its parts — the parts can each be
 *  right while the seam between them loses an answer.
 *
 *  **Orchestrated from pytest.** The one step this side cannot perform is
 *  winding the assessment clock past the bell, which means editing
 *  `Attempt.started_at`. `backend/tests/test_recovery_e2e.py` creates the
 *  attempt, moves the clock, runs this file with the details in the
 *  environment, and then submits and checks the score. Neither half can prove
 *  the chain alone.
 *
 *  Run without those variables — `npm test` on a laptop with no server — it
 *  skips, and says so loudly rather than passing quietly.
 */
import "fake-indexeddb/auto";

import { describe, expect, it } from "vitest";

import { deliverRecording, drainPending, owedFor } from "./delivery";
import { outstanding } from "./pending";

const API = process.env.E2E_API ?? "";
const TOKEN = process.env.E2E_TOKEN ?? "";
const ATTEMPT = process.env.E2E_ATTEMPT ?? "";
const RESPONSE = process.env.E2E_RESPONSE ?? "";
const orchestrated = Boolean(API && TOKEN && ATTEMPT && RESPONSE);

if (!orchestrated) {
  // eslint-disable-next-line no-console
  console.warn(
    "\n  [e2e] SKIPPED: no E2E_API/E2E_TOKEN/E2E_ATTEMPT/E2E_RESPONSE.\n"
    + "  This file only means anything when driven by\n"
    + "  backend/tests/test_recovery_e2e.py, which supplies a real attempt.\n");
}

/** A WAV the server will accept: 16 kHz mono PCM, three seconds of tone. */
function realWav(seconds = 3, sampleRate = 16000): Blob {
  const frames = seconds * sampleRate;
  const buffer = new ArrayBuffer(44 + frames * 2);
  const view = new DataView(buffer);
  const text = (at: number, s: string) => {
    for (let i = 0; i < s.length; i += 1) view.setUint8(at + i, s.charCodeAt(i));
  };
  text(0, "RIFF");
  view.setUint32(4, 36 + frames * 2, true);
  text(8, "WAVEfmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);          // PCM
  view.setUint16(22, 1, true);          // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  text(36, "data");
  view.setUint32(40, frames * 2, true);
  for (let i = 0; i < frames; i += 1) {
    // Audible, varying, and nothing like silence — the server's own VAD has
    // to find speech in it for the answer to score.
    const t = i / sampleRate;
    const value = Math.sin(2 * Math.PI * 180 * t)
      * (0.35 + 0.25 * Math.sin(2 * Math.PI * 3 * t));
    view.setInt16(44 + i * 2, Math.round(value * 32767 * 0.7), true);
  }
  return new Blob([buffer], { type: "audio/wav" });
}

/** The real upload, exactly as `lib/api.ts` performs it. */
async function sendToServer(responseId: string, blob: Blob): Promise<number> {
  const form = new FormData();
  form.append("file", blob, "answer.wav");
  const res = await fetch(
    `${API}/student/attempts/${ATTEMPT}/responses/${responseId}/audio`,
    { method: "POST", body: form,
      headers: { Authorization: `Bearer ${TOKEN}` } });
  return res.status;
}

/** A transport that cannot reach anything — the outage. */
async function sendNowhere(): Promise<number> {
  await fetch("http://127.0.0.1:9/dead");   // discard port; always refuses
  return 0;
}

describe.skipIf(!orchestrated)("recovery, end to end", () => {
  it("survives the bell, an outage and a reload, and is still scorable", async () => {
    const audio = realWav();

    // -- 1. The candidate answers. The clock is already past the bell:
    //       pytest moved `started_at` before starting this process, so the
    //       upload that follows is a *late delivery of audio recorded in
    //       time* -- the exact case that must never be refused.
    //
    //    The network is down.
    const failed = await deliverRecording({
      attemptId: ATTEMPT, responseId: RESPONSE, blob: audio,
      send: sendNowhere, sleep: async () => { /* no waiting */ },
      recordedAt: 1,
    });

    expect(failed.ok).toBe(false);
    expect(failed.owed).toBe(1);

    // -- 2. The page reloads. Nothing is in memory; the audio exists only
    //       because it was written to IndexedDB before the first POST.
    const restored = await outstanding(ATTEMPT);
    expect(restored).toHaveLength(1);
    expect(restored[0].responseId).toBe(RESPONSE);
    expect(restored[0].blob.size).toBe(audio.size);

    // -- 3. Connectivity returns. The queue drains to the real API, after
    //       the deadline, and the server takes it.
    const drained = await drainPending(ATTEMPT, sendToServer,
                                       { sleep: async () => { /* */ } });

    expect(drained).toEqual({ delivered: 1, owed: 0 });
    expect(await owedFor(ATTEMPT)).toBe(0);
    expect(await outstanding(ATTEMPT)).toHaveLength(0);
  }, 60_000);
});

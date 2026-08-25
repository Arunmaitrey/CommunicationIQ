/**
 *  The scenario, end to end on the client:
 *
 *      record → upload fails → page reload → retry → upload succeeds
 *
 *  Against a real IndexedDB, with the transport and the clock injected. The
 *  "reload" is genuine: every call in `pending.ts` opens its own connection
 *  and closes it, so reading the queue after the failure is the same
 *  operation a fresh page load performs. Nothing is carried in a variable
 *  across the boundary.
 *
 *  This composition used to live inside the runner component, which meant the
 *  one piece of logic whose failure loses a candidate's answer had no test
 *  around it.
 */
import "fake-indexeddb/auto";

import { beforeEach, describe, expect, it, vi } from "vitest";

import { deliverRecording, drainPending, owedFor } from "./delivery";
import { forget, outstanding, outstandingAll } from "./pending";

const ATTEMPT = "attempt-e2e";
const RESPONSE = "response-7";

const nowhere = async () => { /* no waiting in tests */ };

function wav(bytes = 4096): Blob {
  return new Blob([new Uint8Array(bytes)], { type: "audio/wav" });
}

async function clear() {
  for (const entry of await outstandingAll()) await forget(entry.responseId);
}

beforeEach(clear);

describe("the whole path", () => {
  it("record, fail, reload, retry, succeed", async () => {
    // -- the candidate answers, and the network is down ------------------
    let online = false;
    const sent: string[] = [];
    const send = async (responseId: string) => {
      sent.push(responseId);
      if (!online) throw new TypeError("Failed to fetch");
      return 201;
    };

    const first = await deliverRecording({
      attemptId: ATTEMPT, responseId: RESPONSE, blob: wav(),
      send, sleep: nowhere, recordedAt: 1000,
    });

    expect(first.ok).toBe(false);
    expect(first.outcome.reason).toBe("exhausted");
    expect(first.owed).toBe(1);

    // -- the page reloads --------------------------------------------------
    //
    // Nothing survives in memory. The only reason the answer still exists is
    // that it was written before the first POST rather than after it.
    const afterReload = await outstanding(ATTEMPT);
    expect(afterReload).toHaveLength(1);
    expect(afterReload[0].responseId).toBe(RESPONSE);
    expect(afterReload[0].blob.size).toBe(4096);
    expect(afterReload[0].tries).toBe(1);
    expect(afterReload[0].lastError).toContain("Failed to fetch");

    // -- connectivity returns, the queue drains ---------------------------
    online = true;
    const drained = await drainPending(ATTEMPT, send, { sleep: nowhere });

    expect(drained).toEqual({ delivered: 1, owed: 0 });
    expect(await owedFor(ATTEMPT)).toBe(0);

    // And the recording is gone from the queue only because the server
    // confirmed it, never because we gave up on it.
    expect(await outstanding(ATTEMPT)).toHaveLength(0);
  });

  it("the same recording reaching a server that already has it is still success", async () => {
    // The other half of the reload story: the first POST *did* land and the
    // response was lost, so the retry meets a 409. Anything other than
    // success here discards an answer the server is already holding.
    let attempt = 0;
    const send = async () => {
      attempt += 1;
      if (attempt === 1) throw new Error("connection reset");
      return 409;
    };

    const result = await deliverRecording({
      attemptId: ATTEMPT, responseId: RESPONSE, blob: wav(),
      send, sleep: nowhere,
    });

    expect(result.ok).toBe(true);
    expect(result.owed).toBe(0);
    expect(await outstanding(ATTEMPT)).toHaveLength(0);
  });

  it("stores before sending, so a crash between the two loses nothing", async () => {
    // Asserted by ordering rather than by outcome: the queue must already
    // contain the entry at the moment the transport is first called.
    let queuedWhenSent = -1;
    const send = async () => {
      queuedWhenSent = (await outstanding(ATTEMPT)).length;
      return 201;
    };

    await deliverRecording({ attemptId: ATTEMPT, responseId: RESPONSE,
                             blob: wav(), send, sleep: nowhere });

    expect(queuedWhenSent).toBe(1);
  });

  it("a permanent rejection keeps the audio rather than discarding it", async () => {
    // 415 is terminal for *retrying* -- sending it again produces the same
    // answer. It is not terminal for the recording, which is still the only
    // copy of something the candidate said and may yet be recoverable by a
    // human. Nothing here calls skip.
    const result = await deliverRecording({
      attemptId: ATTEMPT, responseId: RESPONSE, blob: wav(),
      send: async () => 415, sleep: nowhere,
    });

    expect(result.ok).toBe(false);
    expect(result.outcome.reason).toBe("terminal");
    expect(result.owed).toBe(1);
    const [kept] = await outstanding(ATTEMPT);
    expect(kept.blob.size).toBe(4096);
    expect(kept.lastError).toBe("HTTP 415");
  });

  it("does not retry a terminal rejection", async () => {
    const send = vi.fn(async () => 413);
    await deliverRecording({ attemptId: ATTEMPT, responseId: RESPONSE,
                             blob: wav(), send, sleep: nowhere });
    expect(send).toHaveBeenCalledTimes(1);
  });

  it("several answers owed after an outage all arrive, oldest first", async () => {
    let online = false;
    const sent: string[] = [];
    const send = async (responseId: string) => {
      if (!online) throw new Error("offline");
      sent.push(responseId);
      return 201;
    };

    for (const [id, at] of [["a", 100], ["b", 200], ["c", 300]] as const) {
      await deliverRecording({ attemptId: ATTEMPT, responseId: id, blob: wav(),
                               send, sleep: nowhere, recordedAt: at });
    }
    expect(await owedFor(ATTEMPT)).toBe(3);

    online = true;
    expect(await drainPending(ATTEMPT, send, { sleep: nowhere }))
      .toEqual({ delivered: 3, owed: 0 });
    expect(sent).toEqual(["a", "b", "c"]);
  });

  it("draining while still offline changes nothing and loses nothing", async () => {
    await deliverRecording({
      attemptId: ATTEMPT, responseId: RESPONSE, blob: wav(),
      send: async () => { throw new Error("offline"); }, sleep: nowhere });

    const again = await drainPending(
      ATTEMPT, async () => { throw new Error("still offline"); },
      { sleep: nowhere });

    expect(again).toEqual({ delivered: 0, owed: 1 });
    expect((await outstanding(ATTEMPT))[0].blob.size).toBe(4096);
  });

  it("one attempt's outage does not hold up another attempt", async () => {
    await deliverRecording({
      attemptId: ATTEMPT, responseId: "stuck", blob: wav(),
      send: async () => { throw new Error("offline"); }, sleep: nowhere });

    const other = await deliverRecording({
      attemptId: "attempt-other", responseId: "fine", blob: wav(),
      send: async () => 201, sleep: nowhere });

    expect(other.ok).toBe(true);
    expect(await owedFor("attempt-other")).toBe(0);
    expect(await owedFor(ATTEMPT)).toBe(1);
  });
});

describe("two drains at once", () => {
  it("the second waits for the first instead of racing it", async () => {
    // Arriving on the page, the browser coming back online, and pressing
    // submit can all start a drain within a second of each other. Two over
    // one queue is not merely wasteful: `noteFailure` reads an entry and
    // writes it back, so a failure recorded by one can resurrect an entry the
    // other has just had acknowledged and forgotten -- and the recording is
    // then uploaded twice while the owed count never reaches zero.
    await deliverRecording({
      attemptId: ATTEMPT, responseId: "a", blob: wav(),
      send: async () => { throw new Error("offline"); },
      sleep: nowhere, recordedAt: 1 });

    let inFlight = 0;
    let concurrent = 0;
    const send = async () => {
      inFlight += 1;
      concurrent = Math.max(concurrent, inFlight);
      await new Promise((r) => setTimeout(r, 10));
      inFlight -= 1;
      return 201;
    };

    const [first, second] = await Promise.all([
      drainPending(ATTEMPT, send, { sleep: nowhere }),
      drainPending(ATTEMPT, send, { sleep: nowhere }),
    ]);

    expect(concurrent).toBe(1);
    expect(first).toEqual(second);
    expect(first.owed).toBe(0);
    expect(await owedFor(ATTEMPT)).toBe(0);
  });

  it("a later drain still runs once the first has finished", async () => {
    // The lock must release. A guard that never cleared would leave a
    // browser unable to retry for the rest of the sitting.
    await deliverRecording({
      attemptId: ATTEMPT, responseId: "a", blob: wav(),
      send: async () => { throw new Error("offline"); },
      sleep: nowhere, recordedAt: 1 });

    expect(await drainPending(
      ATTEMPT, async () => { throw new Error("still offline"); },
      { sleep: nowhere })).toEqual({ delivered: 0, owed: 1 });

    expect(await drainPending(ATTEMPT, async () => 201, { sleep: nowhere }))
      .toEqual({ delivered: 1, owed: 0 });
  });
});

describe("a typed or chosen answer", () => {
  it("survives an outage and a reload, exactly as a recording does", async () => {
    // The gap Phase 7 left. A failed POST used to call `skip`, so somebody
    // who wrote three paragraphs into a dropped connection was recorded as
    // not having answered -- and one-shot means they never see the question
    // again to re-enter it.
    let online = false;
    const seen: string[] = [];
    const send = async (responseId: string, blob: Blob, kind: string) => {
      seen.push(kind);
      if (!online) throw new TypeError("Failed to fetch");
      return 201;
    };

    const written = new Blob([JSON.stringify({ text: "three paragraphs" })],
                             { type: "application/json" });

    const failed = await deliverRecording({
      attemptId: ATTEMPT, responseId: RESPONSE, blob: written, kind: "answer",
      send, sleep: nowhere, recordedAt: 5 });

    expect(failed.ok).toBe(false);
    expect(failed.owed).toBe(1);

    // Reload: the words are still there, and still marked as an answer.
    const [kept] = await outstanding(ATTEMPT);
    expect(kept.kind).toBe("answer");
    expect(JSON.parse(await kept.blob.text()).text).toBe("three paragraphs");

    online = true;
    expect(await drainPending(ATTEMPT, send, { sleep: nowhere }))
      .toEqual({ delivered: 1, owed: 0 });
    expect(seen.every((k) => k === "answer")).toBe(true);
  });

  it("a 409 on the retry counts as stored, as it does for audio", async () => {
    // The server refuses a second answer for a response it has already
    // marked, so that refusal proves the first one landed.
    let n = 0;
    const send = async () => { n += 1; return n === 1 ? 503 : 409; };

    const result = await deliverRecording({
      attemptId: ATTEMPT, responseId: RESPONSE, kind: "answer",
      blob: new Blob(["{}"], { type: "application/json" }),
      send, sleep: nowhere });

    expect(result.ok).toBe(true);
    expect(result.owed).toBe(0);
  });

  it("audio and answers queue together and drain in order", async () => {
    const kinds: string[] = [];
    const send = async (_id: string, _blob: Blob, kind: string) => {
      kinds.push(kind);
      return 201;
    };
    const offline = async () => { throw new Error("offline"); };

    await deliverRecording({ attemptId: ATTEMPT, responseId: "spoken",
                             blob: wav(), send: offline, sleep: nowhere,
                             recordedAt: 1 });
    await deliverRecording({ attemptId: ATTEMPT, responseId: "typed",
                             kind: "answer",
                             blob: new Blob(["{}"]), send: offline,
                             sleep: nowhere, recordedAt: 2 });

    expect(await drainPending(ATTEMPT, send, { sleep: nowhere }))
      .toEqual({ delivered: 2, owed: 0 });
    expect(kinds).toEqual(["audio", "answer"]);
  });

  it("an entry stored before kinds existed still delivers as audio", async () => {
    // Nothing writes such a row now, but a browser mid-attempt when this
    // shipped has one. Defaulting to audio is what it was.
    const { remember } = await import("./pending");
    await remember({ responseId: "legacy", attemptId: ATTEMPT, blob: wav(),
                     recordedAt: 1 });

    const kinds: string[] = [];
    await drainPending(ATTEMPT, async (_id, _blob, kind) => {
      kinds.push(kind);
      return 201;
    }, { sleep: nowhere });

    expect(kinds).toEqual(["audio"]);
  });
});

describe("a shut window", () => {
  it("keeps the answer and reports it rather than silently dropping it", async () => {
    // 410 is terminal, but terminal is not the same as gone. The entry stays
    // owed so the runner blocks submission on it and tells the candidate,
    // which is the difference between "we could not take this" and the
    // candidate believing they answered when the record says they did not.
    const result = await deliverRecording({
      attemptId: ATTEMPT, responseId: RESPONSE, kind: "answer",
      blob: new Blob(["{}"], { type: "application/json" }),
      send: async () => 410, sleep: nowhere });

    expect(result.ok).toBe(false);
    expect(result.owed).toBe(1);
    expect((await outstanding(ATTEMPT)).length).toBe(1);
  });
});

describe("background delivery (the Next-click path)", () => {
  it("resolves after the persist, not after the send", async () => {
    const { deliverRecordingInBackground } = await import("./delivery");
    let release!: () => void;
    const gate = new Promise<void>((r) => { release = r; });
    let sent = 0;

    const settled = new Promise<import("./delivery").DeliveryResult>((resolve) => {
      void deliverRecordingInBackground({
        attemptId: ATTEMPT, responseId: RESPONSE, blob: wav(),
        send: async () => { await gate; sent += 1; return 201; },
        sleep: nowhere,
      }, resolve).then(async ({ owed }) => {
        // Back from the call while the send is still gated: the answer is
        // already on disk and counted as owed -- the candidate can move on.
        expect(sent).toBe(0);
        expect(owed).toBe(1);
        expect(await outstanding(ATTEMPT)).toHaveLength(1);
        release();
      });
    });

    const result = await settled;
    expect(result.ok).toBe(true);
    expect(sent).toBe(1);
    // Delivered and forgotten: nothing owed once the background send lands.
    expect(result.owed).toBe(0);
    expect(await outstanding(ATTEMPT)).toHaveLength(0);
  });

  it("a failed background send stays owed for the pre-submit drain", async () => {
    const { deliverRecordingInBackground } = await import("./delivery");
    const result = await new Promise<import("./delivery").DeliveryResult>((resolve) => {
      void deliverRecordingInBackground({
        attemptId: ATTEMPT, responseId: RESPONSE, blob: wav(),
        send: async () => 500,      // the server keeps refusing
        sleep: nowhere,
      }, resolve);
    });
    expect(result.ok).toBe(false);
    expect(result.owed).toBe(1);    // kept on disk, gated at submit
    expect(await outstanding(ATTEMPT)).toHaveLength(1);
  });
});

describe("why the recording ended travels with it", () => {
  // The report may only say "ran out of time" for window_expired, so the
  // reason must reach the server with the audio — including after a reload,
  // when the retry is replayed from IndexedDB with no runner state left.
  it("passes endedBy to the transport and persists it across a reload", async () => {
    let online = false;
    const seen: (string | undefined)[] = [];
    const send = async (_rid: string, _blob: Blob, _kind: "audio" | "answer",
                        endedBy?: string) => {
      seen.push(endedBy);
      if (!online) throw new TypeError("Failed to fetch");
      return 201;
    };

    await deliverRecording({
      attemptId: ATTEMPT, responseId: "response-ended", blob: wav(),
      endedBy: "user_ended", send, sleep: nowhere,
    });
    expect(seen.at(-1)).toBe("user_ended");

    // The "reload": the queue is read back from IndexedDB, not from memory.
    const queued = await outstanding(ATTEMPT);
    expect(queued.find((e) => e.responseId === "response-ended")?.endedBy)
      .toBe("user_ended");

    online = true;
    await drainPending(ATTEMPT, send);
    expect(seen.at(-1)).toBe("user_ended");
    expect(await owedFor(ATTEMPT)).toBe(0);
  });
});

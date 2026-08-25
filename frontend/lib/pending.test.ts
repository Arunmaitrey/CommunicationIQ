/**
 *  The queue, against a real IndexedDB implementation.
 *
 *  `fake-indexeddb` is a full implementation rather than a stub, so a reload
 *  is genuinely testable: close the connection, reopen it, and see whether
 *  the audio is still there. A mocked store would only prove that the mock
 *  remembers what it was told.
 */
import "fake-indexeddb/auto";

import { beforeEach, describe, expect, it } from "vitest";

import {
  count, drain, forget, noteFailure, outstanding, outstandingAll, remember,
} from "./pending";

const ATTEMPT = "attempt-1";

function wav(bytes = 2048): Blob {
  return new Blob([new Uint8Array(bytes)], { type: "audio/wav" });
}

async function clear() {
  for (const entry of await outstandingAll()) await forget(entry.responseId);
}

beforeEach(clear);

describe("keeping a recording", () => {
  it("survives being written and read back", async () => {
    await remember({ responseId: "r1", attemptId: ATTEMPT, blob: wav(1234),
                     recordedAt: 100 });

    const [entry] = await outstanding(ATTEMPT);
    expect(entry.responseId).toBe("r1");
    expect(entry.blob.size).toBe(1234);
    expect(entry.tries).toBe(0);
  });

  it("survives a reload", async () => {
    // The whole reason this is IndexedDB and not a useRef. Every call in this
    // module opens its own connection and closes it, so a second read is a
    // genuinely fresh one -- the same thing a page reload does.
    await remember({ responseId: "r1", attemptId: ATTEMPT, blob: wav(999),
                     recordedAt: 1 });

    const afterReload = await outstanding(ATTEMPT);
    expect(afterReload).toHaveLength(1);
    expect(afterReload[0].blob.size).toBe(999);
  });

  it("comes back oldest first, so answers are delivered in the order given", async () => {
    await remember({ responseId: "c", attemptId: ATTEMPT, blob: wav(), recordedAt: 300 });
    await remember({ responseId: "a", attemptId: ATTEMPT, blob: wav(), recordedAt: 100 });
    await remember({ responseId: "b", attemptId: ATTEMPT, blob: wav(), recordedAt: 200 });

    expect((await outstanding(ATTEMPT)).map((e) => e.responseId))
      .toEqual(["a", "b", "c"]);
  });

  it("keeps one attempt's recordings out of another's", async () => {
    await remember({ responseId: "r1", attemptId: ATTEMPT, blob: wav(), recordedAt: 1 });
    await remember({ responseId: "r2", attemptId: "other", blob: wav(), recordedAt: 2 });

    expect(await count(ATTEMPT)).toBe(1);
    expect(await count("other")).toBe(1);
  });

  it("is only forgotten on an acknowledgement", async () => {
    await remember({ responseId: "r1", attemptId: ATTEMPT, blob: wav(), recordedAt: 1 });

    await noteFailure("r1", "HTTP 500");
    const [afterFailure] = await outstanding(ATTEMPT);
    expect(afterFailure.tries).toBe(1);
    expect(afterFailure.lastError).toBe("HTTP 500");
    expect(afterFailure.blob.size).toBeGreaterThan(0);

    await forget("r1");
    expect(await count(ATTEMPT)).toBe(0);
  });

  it("re-remembering the same response does not duplicate it", async () => {
    // Two tabs, or a retry that re-enqueues. The response id is the key, so
    // the second write replaces the first rather than owing the answer twice.
    await remember({ responseId: "r1", attemptId: ATTEMPT, blob: wav(), recordedAt: 1 });
    await remember({ responseId: "r1", attemptId: ATTEMPT, blob: wav(), recordedAt: 2 });

    expect(await count(ATTEMPT)).toBe(1);
  });
});

describe("draining the queue", () => {
  it("delivers everything and empties", async () => {
    for (const id of ["a", "b", "c"]) {
      await remember({ responseId: id, attemptId: ATTEMPT, blob: wav(),
                       recordedAt: id.charCodeAt(0) });
    }

    const sent: string[] = [];
    const out = await drain(ATTEMPT, async (entry) => {
      sent.push(entry.responseId);
      return { ok: true, detail: "HTTP 201" };
    });

    expect(sent).toEqual(["a", "b", "c"]);
    expect(out).toEqual({ delivered: 3, remaining: 0 });
  });

  it("a 409 counts as delivered, so a duplicate costs one request and no answer", async () => {
    await remember({ responseId: "r1", attemptId: ATTEMPT, blob: wav(), recordedAt: 1 });

    const out = await drain(ATTEMPT, async () => ({ ok: true, detail: "HTTP 409" }));

    expect(out).toEqual({ delivered: 1, remaining: 0 });
  });

  it("stops at the first failure instead of burning the budget on the rest", async () => {
    // If the connection is down the second entry fails the same way. Working
    // through all of them turns one outage into a much longer stall while the
    // candidate watches.
    for (const id of ["a", "b", "c"]) {
      await remember({ responseId: id, attemptId: ATTEMPT, blob: wav(),
                       recordedAt: id.charCodeAt(0) });
    }

    const tried: string[] = [];
    const out = await drain(ATTEMPT, async (entry) => {
      tried.push(entry.responseId);
      return { ok: entry.responseId === "a", detail: "HTTP 503" };
    });

    expect(tried).toEqual(["a", "b"]);
    expect(out).toEqual({ delivered: 1, remaining: 2 });
  });

  it("keeps the audio when delivery fails", async () => {
    await remember({ responseId: "r1", attemptId: ATTEMPT, blob: wav(4096),
                     recordedAt: 1 });

    await drain(ATTEMPT, async () => ({ ok: false, detail: "network error" }));

    const [still] = await outstanding(ATTEMPT);
    expect(still.blob.size).toBe(4096);
    expect(still.tries).toBe(1);
    expect(still.lastError).toBe("network error");
  });

  it("draining an empty queue is a no-op, not an error", async () => {
    expect(await drain(ATTEMPT, async () => ({ ok: true, detail: "" })))
      .toEqual({ delivered: 0, remaining: 0 });
  });

  it("a second drain after reconnection picks up where the first stopped", async () => {
    for (const id of ["a", "b"]) {
      await remember({ responseId: id, attemptId: ATTEMPT, blob: wav(),
                       recordedAt: id.charCodeAt(0) });
    }

    let online = false;
    const deliverOne = async () => ({ ok: online, detail: online ? "" : "offline" });

    expect((await drain(ATTEMPT, deliverOne)).remaining).toBe(2);
    online = true;
    expect(await drain(ATTEMPT, deliverOne)).toEqual({ delivered: 2, remaining: 0 });
  });
});

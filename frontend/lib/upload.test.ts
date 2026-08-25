/**
 *  Failure sequences, deterministically.
 *
 *  The transport and the clock are injected, so every case the audit names is
 *  an ordinary assertion rather than something that happens to a browser on a
 *  bad day. The one property that matters more than any individual case: a
 *  loop that ends in anything other than "stored" must say so, because the
 *  caller's next decision is whether to record a person as not having
 *  answered.
 */
import { describe, expect, it, vi } from "vitest";

import {
  BACKOFF_CAP_MS, MAX_ATTEMPTS, backoffMs, deliver, verdictFor,
} from "./upload";

/** A transport that returns a scripted sequence, then repeats the last one. */
function scripted(...steps: (number | Error)[]) {
  let n = 0;
  const calls: number[] = [];
  const send = async () => {
    const step = steps[Math.min(n, steps.length - 1)];
    n += 1;
    calls.push(n);
    if (step instanceof Error) throw step;
    return step;
  };
  return { send, get attempts() { return n; } };
}

/** A clock the test drives, so elapsed time is exact and nothing waits. */
function fakeClock() {
  let t = 0;
  return {
    now: () => t,
    sleep: async (ms: number) => { t += ms; },
    advance: (ms: number) => { t += ms; },
    get elapsed() { return t; },
  };
}

describe("reading a status", () => {
  it("treats 409 as stored, because a duplicate means the first one landed", () => {
    // The single most important line in this module. The server refuses a
    // second upload for the same response; from here that refusal is proof.
    // Reading it as a failure is how a *successful* upload becomes a skipped
    // item on the retry.
    expect(verdictFor(409)).toBe("stored");
    expect(verdictFor(201)).toBe("stored");
  });

  it("retries what might work later", () => {
    for (const status of [408, 429, 500, 502, 503, 504]) {
      expect(verdictFor(status)).toBe("retry");
    }
  });

  it("does not retry a request that is simply wrong", () => {
    // Sending a 12 MB file again produces another 413 and costs the candidate
    // the time it takes to find that out six more times.
    for (const status of [400, 401, 403, 413, 415, 422]) {
      expect(verdictFor(status)).toBe("terminal");
    }
  });
});

describe("backoff", () => {
  it("grows and then stops growing", () => {
    expect(backoffMs(1)).toBe(500);
    expect(backoffMs(2)).toBe(1000);
    expect(backoffMs(3)).toBe(2000);
    expect(backoffMs(10)).toBe(BACKOFF_CAP_MS);
  });
});

describe("delivering a recording", () => {
  it("succeeds first time without sleeping", async () => {
    const clock = fakeClock();
    const sleep = vi.fn(clock.sleep);
    const out = await deliver({ send: scripted(201).send, sleep, now: clock.now });

    expect(out).toMatchObject({ ok: true, reason: "stored", attempts: 1 });
    expect(sleep).not.toHaveBeenCalled();
  });

  it("fail then success", async () => {
    const clock = fakeClock();
    const out = await deliver({
      send: scripted(503, 201).send, sleep: clock.sleep, now: clock.now });

    expect(out).toMatchObject({ ok: true, reason: "stored", attempts: 2 });
    expect(clock.elapsed).toBe(500);
  });

  it("fail, fail, then success", async () => {
    const clock = fakeClock();
    const out = await deliver({
      send: scripted(500, 502, 201).send, sleep: clock.sleep, now: clock.now });

    expect(out).toMatchObject({ ok: true, reason: "stored", attempts: 3 });
    expect(clock.elapsed).toBe(1500);   // 500 + 1000
  });

  it("a network disconnect is retried, not treated as a rejection", async () => {
    // Nothing judged the request; it never arrived. The distinction matters:
    // a thrown error carries no status, and a status of 0 must not fall
    // through to the terminal branch.
    const clock = fakeClock();
    const out = await deliver({
      send: scripted(new TypeError("Failed to fetch"), 201).send,
      sleep: clock.sleep, now: clock.now });

    expect(out).toMatchObject({ ok: true, attempts: 2 });
  });

  it("a timeout is retried", async () => {
    const clock = fakeClock();
    const out = await deliver({
      send: scripted(408, 408, 201).send, sleep: clock.sleep, now: clock.now });
    expect(out.ok).toBe(true);
    expect(out.attempts).toBe(3);
  });

  it("a 409 on the retry counts as stored", async () => {
    // The exact shape of the bug this fixes: the first POST succeeded and the
    // response was lost, so the retry hits a server that already has the
    // recording. Anything other than success here loses a real answer.
    const clock = fakeClock();
    const out = await deliver({
      send: scripted(new Error("connection reset"), 409).send,
      sleep: clock.sleep, now: clock.now });

    expect(out).toMatchObject({ ok: true, reason: "stored", attempts: 2 });
  });

  it("a 415 stops immediately", async () => {
    const clock = fakeClock();
    const sleep = vi.fn(clock.sleep);
    const transport = scripted(415);
    const out = await deliver({ send: transport.send, sleep, now: clock.now });

    expect(out).toMatchObject({ ok: false, reason: "terminal", attempts: 1,
                                status: 415 });
    expect(sleep).not.toHaveBeenCalled();
    expect(transport.attempts).toBe(1);
  });

  it("a 413 stops immediately", async () => {
    const clock = fakeClock();
    const out = await deliver({
      send: scripted(413).send, sleep: clock.sleep, now: clock.now });
    expect(out.reason).toBe("terminal");
    expect(out.attempts).toBe(1);
  });

  it("gives up after the attempt budget rather than looping forever", async () => {
    const clock = fakeClock();
    const transport = scripted(500);
    const out = await deliver({
      send: transport.send, sleep: clock.sleep, now: clock.now });

    expect(out).toMatchObject({ ok: false, reason: "exhausted" });
    expect(out.attempts).toBe(MAX_ATTEMPTS);
    expect(transport.attempts).toBe(MAX_ATTEMPTS);
  });

  it("gives up on the time budget before starting a wait that would overrun", async () => {
    // Checked against the wait about to be taken, not against where we are
    // now -- otherwise a 3-second budget spends 8.5 seconds honouring it.
    const clock = fakeClock();
    const out = await deliver({
      send: scripted(500).send, sleep: clock.sleep, now: clock.now,
      maxAttempts: 50, maxElapsedMs: 3000 });

    expect(out.reason).toBe("exhausted");
    expect(clock.elapsed).toBeLessThanOrEqual(3000);
  });

  it("never throws, whatever the transport does", async () => {
    const clock = fakeClock();
    const out = await deliver({
      send: async () => { throw new Error("boom"); },
      sleep: clock.sleep, now: clock.now, maxAttempts: 2 });

    expect(out.ok).toBe(false);
    expect(out.reason).toBe("exhausted");
    expect(out.status).toBe(0);
  });

  it("reports each retry so the screen can say what is happening", async () => {
    const clock = fakeClock();
    const seen: number[] = [];
    await deliver({
      send: scripted(500, 500, 201).send, sleep: clock.sleep, now: clock.now,
      onRetry: (_attempt, waitMs) => seen.push(waitMs) });

    expect(seen).toEqual([500, 1000]);
  });

  it("a failure is never reported as a success", async () => {
    // The invariant, asserted directly: the caller decides whether to record
    // somebody as not having answered, and it may only do that on ok.
    for (const script of [[500], [415], [new Error("x")], [403]]) {
      const clock = fakeClock();
      const out = await deliver({
        send: scripted(...script).send, sleep: clock.sleep, now: clock.now,
        maxAttempts: 2 });
      expect(out.ok).toBe(false);
    }
  });
});

describe("410 versus 409", () => {
  it("reads 409 as stored and 410 as terminal", () => {
    // The server answers a duplicate with 409 and a shut window with 410.
    // Collapsing them would make the runner delete a queued answer the
    // server never accepted -- silent loss through the machinery built to
    // prevent it.
    expect(verdictFor(409)).toBe("stored");
    expect(verdictFor(410)).toBe("terminal");
  });

  it("never treats a shut window as something to keep retrying", () => {
    // Retrying past the recovery window spends the candidate's remaining
    // seconds on a request that cannot succeed.
    expect(verdictFor(410)).not.toBe("retry");
  });
});

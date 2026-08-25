/**
 *  Getting a recording to the server, or knowing that it did not go.
 *
 *  The invariant, and everything here exists to hold it:
 *
 *      A transient upload failure must never silently become a skipped
 *      answer.
 *
 *  What it did instead: one POST, and on any error the runner called `skip`
 *  and moved on. A dropped Wi-Fi frame between two items therefore recorded
 *  the candidate as not having answered — a false statement about a person,
 *  written into a result they are judged on, with nothing on the screen to
 *  say it happened. That is the highest-severity reliability gap in the audit
 *  and it is the one this module closes.
 *
 *  **Why the logic is here and not in the component.** A retry loop tangled
 *  into a React effect can only be tested by driving a browser. Pulled out,
 *  with the transport and the clock injected, every failure sequence the
 *  audit asks about is an ordinary unit test: fail-fail-succeed, budget
 *  exhausted, 409 on the retry, 415, a socket that never answers.
 */

/** What the server said, reduced to what the client should do about it. */
export type Verdict =
  /** It is on the server. Includes 409: a duplicate means the first one landed. */
  | "stored"
  /** Might work later. Network, timeout, 5xx, 408, 429. */
  | "retry"
  /** Will never work. Wrong file, too big, not allowed, not signed in. */
  | "terminal";

/**
 *  Read an HTTP status as one of the three.
 *
 *  409 is the interesting one. `upload_response_audio` refuses a second
 *  upload for the same response, because accepting one would quietly undo the
 *  one-shot rule. From the client's side that refusal is *proof the recording
 *  is already there* — which is exactly what a retry after a lost response
 *  needs to hear. Treating it as a failure is how a successful upload becomes
 *  a skipped item on the retry.
 */
export function verdictFor(status: number): Verdict {
  if (status === 201 || status === 200) return "stored";
  // 409 is the server saying it already has an answer for this response, so
  // the delivery that got there first counts as this one landing.
  if (status === 409) return "stored";
  // 410 is the server saying the window shut. Distinct from 409 on purpose:
  // reading "too late" as "already stored" would delete the only copy of
  // something the server never took. Terminal, but the candidate is told and
  // the entry stays owed, which is the whole point of the distinction.
  if (status === 410) return "terminal";
  if (status === 408 || status === 429) return "retry";
  if (status >= 500) return "retry";
  // 400, 401, 403, 413, 415, 422 — the request itself is wrong. Sending it
  // again produces the same answer and burns the candidate's time.
  return "terminal";
}

/**
 *  How long to wait before attempt n (1-based), in milliseconds.
 *
 *  Exponential from a small base, capped, and deterministic — no jitter. The
 *  usual reason for jitter is a thundering herd of clients retrying in
 *  lockstep, and one candidate's browser retrying one upload is not that. A
 *  fixed schedule is testable, and testable matters more here.
 */
export const BACKOFF_BASE_MS = 500;
export const BACKOFF_CAP_MS = 8000;

export function backoffMs(attempt: number): number {
  return Math.min(BACKOFF_CAP_MS, BACKOFF_BASE_MS * 2 ** Math.max(0, attempt - 1));
}

/** The budget. Both bounds are hard: whichever runs out first stops the loop.
 *
 *  A retry loop with no ceiling can hold an assessment open forever, which is
 *  a worse failure than the one it is fixing — the candidate sits watching a
 *  spinner while the clock they are being timed against runs down. Six
 *  attempts across roughly half a minute is enough to ride out a lift, a
 *  handover between access points, or a server restart, and short enough that
 *  a genuinely dead connection is admitted rather than waited out.
 */
export const MAX_ATTEMPTS = 6;
export const MAX_ELAPSED_MS = 45_000;

export interface Outcome {
  ok: boolean;
  /** "stored" | "terminal" | "exhausted" — why the loop finished. */
  reason: "stored" | "terminal" | "exhausted";
  attempts: number;
  /** The last status seen, or 0 when every attempt failed at the socket. */
  status: number;
  detail: string;
}

export interface DeliverOptions {
  /** Resolves with an HTTP status; throws for a network-level failure. */
  send: () => Promise<number>;
  /** Injected so tests do not wait. Defaults to a real timer. */
  sleep?: (ms: number) => Promise<void>;
  /** Injected so tests control elapsed time. Defaults to Date.now. */
  now?: () => number;
  maxAttempts?: number;
  maxElapsedMs?: number;
  /** Called before each wait, so the UI can say what is happening. */
  onRetry?: (attempt: number, waitMs: number, status: number) => void;
}

const realSleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

/**
 *  Try until it is stored, provably hopeless, or out of budget.
 *
 *  Never throws. The caller gets an Outcome and decides — and the one thing
 *  it must not decide, on anything other than `stored`, is to mark the item
 *  skipped.
 */
export async function deliver(options: DeliverOptions): Promise<Outcome> {
  const sleep = options.sleep ?? realSleep;
  const now = options.now ?? (() => Date.now());
  const maxAttempts = options.maxAttempts ?? MAX_ATTEMPTS;
  const maxElapsed = options.maxElapsedMs ?? MAX_ELAPSED_MS;

  const started = now();
  let attempts = 0;
  let lastStatus = 0;
  let lastDetail = "";

  while (attempts < maxAttempts) {
    attempts += 1;
    let verdict: Verdict;
    try {
      lastStatus = await options.send();
      verdict = verdictFor(lastStatus);
      lastDetail = `HTTP ${lastStatus}`;
    } catch (err) {
      // A thrown error is the network: DNS, refused, reset, aborted. Always
      // worth another go — the request never reached anything that could
      // judge it.
      lastStatus = 0;
      lastDetail = err instanceof Error ? err.message : "network error";
      verdict = "retry";
    }

    if (verdict === "stored") {
      return { ok: true, reason: "stored", attempts, status: lastStatus,
               detail: lastDetail };
    }
    if (verdict === "terminal") {
      return { ok: false, reason: "terminal", attempts, status: lastStatus,
               detail: lastDetail };
    }

    if (attempts >= maxAttempts) break;

    const wait = backoffMs(attempts);
    // Check the time budget against the wait we are about to take, not
    // against where we are now. Starting a sleep we know will overrun is how
    // a "45 second" budget becomes 53.
    if (now() - started + wait > maxElapsed) break;

    options.onRetry?.(attempts, wait, lastStatus);
    await sleep(wait);
  }

  return { ok: false, reason: "exhausted", attempts, status: lastStatus,
           detail: lastDetail };
}

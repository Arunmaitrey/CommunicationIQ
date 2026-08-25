/**
 *  Keeping a recording and getting it there — the two halves joined.
 *
 *  `upload.ts` knows how to retry. `pending.ts` knows how to survive a
 *  reload. Neither knows the order they have to happen in, and the order is
 *  the part that carries the invariant:
 *
 *      keep it first, send it second, forget it only when the server says it
 *      has it.
 *
 *  That sequence lived inside the runner component, which meant the one piece
 *  of logic whose failure loses a candidate's answer was the one piece with
 *  no test around it. It is here now, with the transport injected, so the
 *  whole scenario — record, fail, reload, retry, succeed — is an ordinary
 *  assertion.
 */
import * as pending from "./pending";
import { deliver, type Outcome } from "./upload";

/** Sends one owed answer and returns the HTTP status. Throws on a network
 *  failure -- the distinction `deliver` needs, since a thrown error never
 *  reached anything that could judge it. */
export type Send = (responseId: string, blob: Blob,
                    kind: pending.Kind, endedBy?: string) => Promise<number>;

export interface DeliveryResult {
  ok: boolean;
  /** How many recordings this attempt is still holding afterwards. */
  owed: number;
  outcome: Outcome;
}

export interface DeliveryOptions {
  attemptId: string;
  responseId: string;
  blob: Blob;
  /** Defaults to audio, which is what every caller meant before typed
   *  answers were protected too. */
  kind?: pending.Kind;
  send: Send;
  /** Injected in tests so nothing waits. */
  sleep?: (ms: number) => Promise<void>;
  now?: () => number;
  recordedAt?: number;
  /** Why the recording stopped; persisted with the blob and sent with it. */
  endedBy?: string;
  onRetry?: (attempt: number, waitMs: number, status: number) => void;
}

/**
 *  Store, then send.
 *
 *  Storing first is the whole point. If the tab dies between the two, the
 *  audio is in IndexedDB and the next load finds it; if it were the other way
 *  round there would be a window in which the only copy lived in a variable.
 *
 *  A browser that cannot store still gets to try the upload — degraded, but
 *  better than refusing to send an answer because we could not also file it.
 */
export async function deliverRecording(
  options: DeliveryOptions,
): Promise<DeliveryResult> {
  const { attemptId, responseId, blob } = options;
  const kind = options.kind ?? "audio";
  const storable = pending.available();

  if (storable) {
    try {
      await pending.remember({
        responseId, attemptId, blob, kind,
        recordedAt: options.recordedAt ?? Date.now(),
        endedBy: options.endedBy ?? "",
      });
    } catch {
      /* keep going: an upload that works needs no queue */
    }
  }

  const outcome = await deliver({
    send: () => options.send(responseId, blob, kind, options.endedBy ?? ""),
    sleep: options.sleep,
    now: options.now,
    onRetry: options.onRetry,
  });

  if (!storable) {
    return { ok: outcome.ok, owed: 0, outcome };
  }

  if (outcome.ok) {
    try { await pending.forget(responseId); } catch { /* already gone */ }
  } else {
    // Kept, and the reason recorded. Never `skip` — that would write "did not
    // answer" about somebody whose answer is sitting on their own disk.
    try { await pending.noteFailure(responseId, outcome.detail); } catch { /* */ }
  }

  return { ok: outcome.ok, owed: await pending.count(attemptId), outcome };
}

/**
 *  Persist now, deliver in the background — the Next-click path.
 *
 *  The runner used to await the whole of `deliverRecording` before showing
 *  the next item, which put the retry machinery *inside the candidate's
 *  click*: one transient failure and the backoff (1.6 s, 3.2 s, …, capped at
 *  45 s of attempts) was spent staring at a stalled screen. The measured
 *  persist cost is ~2 ms; the network is the slow, retryable part — and the
 *  queue was designed for exactly this: keep it first, send it whenever.
 *
 *  So this resolves as soon as the answer is safe on disk (or, where storage
 *  is unavailable, immediately — degraded exactly as `deliverRecording` is),
 *  and the send continues in the background. Integrity is unchanged:
 *  `owed`/`drainPending` still gate submission, and a duplicate send is
 *  already treated as stored (409-as-confirmation).
 *
 *  Returns the owed count *including* the just-persisted answer, so the
 *  header is truthful while the upload is in flight. `onSettled` fires with
 *  the ordinary DeliveryResult when the background send concludes.
 */
export async function deliverRecordingInBackground(
  options: DeliveryOptions,
  onSettled?: (result: DeliveryResult) => void,
): Promise<{ owed: number }> {
  const { attemptId, responseId, blob } = options;
  const kind = options.kind ?? "audio";
  const storable = pending.available();

  if (storable) {
    try {
      await pending.remember({
        responseId, attemptId, blob, kind,
        recordedAt: options.recordedAt ?? Date.now(),
        endedBy: options.endedBy ?? "",
      });
    } catch { /* keep going: an upload that works needs no queue */ }
  }

  void (async () => {
    const outcome = await deliver({
      send: () => options.send(responseId, blob, kind, options.endedBy ?? ""),
      sleep: options.sleep,
      now: options.now,
      onRetry: options.onRetry,
    });
    if (storable) {
      if (outcome.ok) {
        try { await pending.forget(responseId); } catch { /* already gone */ }
      } else {
        try { await pending.noteFailure(responseId, outcome.detail); } catch { /* */ }
      }
    }
    onSettled?.({ ok: outcome.ok,
                  owed: storable ? await pending.count(attemptId) : 0,
                  outcome });
  })();

  return { owed: storable ? await pending.count(attemptId) : 0 };
}

/**
 *  Send everything this browser is still holding for an attempt.
 *
 *  The path a reload takes: nothing in memory, everything in IndexedDB, and
 *  no knowledge of which uploads previously failed. It reads the queue and
 *  works through it oldest first.
 */
/** Drains already running, one per attempt.
 *
 *  Three things start a drain: arriving on the page, the browser reporting
 *  that it is back online, and pressing submit. Two of them can happen within
 *  a second of each other, and two concurrent drains over one queue is not
 *  merely wasteful -- `noteFailure` reads an entry and writes it back, so a
 *  failure recorded by one drain can resurrect an entry the other has just
 *  had acknowledged and forgotten. The recording would then be uploaded a
 *  second time and the count of what is owed would never reach zero.
 *
 *  A promise per attempt, so the second caller waits for the first's answer
 *  rather than starting again.
 */
const draining = new Map<string, Promise<{ delivered: number; owed: number }>>();

export async function drainPending(
  attemptId: string, send: Send,
  options: { sleep?: (ms: number) => Promise<void>; now?: () => number } = {},
): Promise<{ delivered: number; owed: number }> {
  const already = draining.get(attemptId);
  if (already) return already;

  const run = drainOnce(attemptId, send, options)
    .finally(() => { draining.delete(attemptId); });
  draining.set(attemptId, run);
  return run;
}

async function drainOnce(
  attemptId: string, send: Send,
  options: { sleep?: (ms: number) => Promise<void>; now?: () => number },
): Promise<{ delivered: number; owed: number }> {
  if (!pending.available()) return { delivered: 0, owed: 0 };

  const { delivered, remaining } = await pending.drain(attemptId, async (entry) => {
    const outcome = await deliver({
      send: () => send(entry.responseId, entry.blob, entry.kind ?? "audio",
                       entry.endedBy ?? ""),
      sleep: options.sleep,
      now: options.now,
    });
    return { ok: outcome.ok, detail: outcome.detail };
  });
  return { delivered, owed: remaining };
}

/** How many answers this browser still owes for an attempt. */
export async function owedFor(attemptId: string): Promise<number> {
  if (!pending.available()) return 0;
  return pending.count(attemptId);
}

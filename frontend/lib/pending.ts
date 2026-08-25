/**
 *  Recordings that have not reached the server yet, kept where a reload
 *  cannot lose them.
 *
 *  Retrying in memory covers a blip. It does not cover the laptop lid, the
 *  browser crash, the accidental refresh, or the phone deciding to reclaim
 *  the tab — and in every one of those the audio is the only copy of
 *  something the candidate cannot be asked to say again. So the WAV goes into
 *  IndexedDB the moment recording stops, before the first upload attempt, and
 *  comes out only when the server has acknowledged it.
 *
 *  **Keyed by response_id, which is the idempotency key.** The server already
 *  refuses a second upload for a given response, so re-delivering an entry
 *  that did land is safe: it comes back 409, which `upload.verdictFor` reads
 *  as stored. Duplicate delivery is therefore not a thing to prevent; it is a
 *  thing that costs one wasted request.
 *
 *  **What this is not.** It is not a general offline mode. An attempt is a
 *  timed assessment and cannot be finished next Tuesday. The queue exists so
 *  that a failure inside one sitting is recoverable, and so that a candidate
 *  who does lose something is told rather than quietly marked absent.
 */

const DB_NAME = "fluenzee-uploads";
const DB_VERSION = 1;
const STORE = "pending";

/** What kind of answer is owed.
 *
 *  Audio was the only one that needed protecting when this was written --
 *  it is the only irreplaceable thing here, because nobody can be asked to
 *  say it again. A typed or chosen answer is small and re-enterable, which is
 *  why it went unprotected for six phases, and it was still wrong: a failed
 *  POST called `skip`, and the candidate who wrote three paragraphs was
 *  recorded as not having answered.
 */
export type Kind = "audio" | "answer";

export interface Pending {
  /** Primary key. Also the server's idempotency key. */
  responseId: string;
  attemptId: string;
  kind: Kind;
  /** Audio, or the JSON of a chosen or written answer. Blobs are
   *  structured-cloneable either way, so both survive a reload. */
  blob: Blob;
  /** For the "you recorded this at 14:32" line, and for ordering. */
  recordedAt: number;
  /** Why the recording stopped (user_ended | auto_advance | window_expired
   *  | cancelled | ""). Persisted with the blob so a reload-resumed upload
   *  still tells the truth about how the answer ended. */
  endedBy?: string;
  /** How many delivery runs have already been spent on it. */
  tries: number;
  /** The last thing that went wrong, for the screen and for support. */
  lastError: string;
}

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE, { keyPath: "responseId" });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function run<T>(mode: IDBTransactionMode,
                body: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  return open().then((db) => new Promise<T>((resolve, reject) => {
    const tx = db.transaction(STORE, mode);
    const request = body(tx.objectStore(STORE));
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
    tx.oncomplete = () => db.close();
  }));
}

/** Put a recording beyond the reach of a reload. Call before uploading. */
export async function remember(
  entry: Omit<Pending, "tries" | "lastError" | "kind">
         & Partial<Pick<Pending, "tries" | "lastError" | "kind">>,
): Promise<void> {
  await run("readwrite", (store) => store.put({
    tries: 0, lastError: "", kind: "audio", ...entry,
  } as Pending));
}

/** Forget it, because the server has it. Only ever called on an acknowledgement. */
export async function forget(responseId: string): Promise<void> {
  await run("readwrite", (store) => store.delete(responseId));
}

/** Record that a delivery run failed, keeping the audio. */
export async function noteFailure(responseId: string, error: string): Promise<void> {
  const existing = await run<Pending | undefined>(
    "readonly", (store) => store.get(responseId));
  if (!existing) return;
  await run("readwrite", (store) => store.put({
    ...existing, tries: existing.tries + 1, lastError: error,
  }));
}

/** Everything still owed, oldest first, for one attempt. */
export async function outstanding(attemptId: string): Promise<Pending[]> {
  const all = await run<Pending[]>("readonly", (store) => store.getAll());
  return all
    .filter((e) => e.attemptId === attemptId)
    .sort((a, b) => a.recordedAt - b.recordedAt);
}

/** Everything still owed, across every attempt. */
export async function outstandingAll(): Promise<Pending[]> {
  const all = await run<Pending[]>("readonly", (store) => store.getAll());
  return all.sort((a, b) => a.recordedAt - b.recordedAt);
}

export async function count(attemptId: string): Promise<number> {
  return (await outstanding(attemptId)).length;
}

/**
 *  Send everything owed for this attempt, oldest first.
 *
 *  `deliverOne` returns true when the server has it — which includes the 409
 *  that says it already did. Stops at the first entry it cannot deliver
 *  rather than working through the rest: if the connection is down, the
 *  second entry will fail the same way, and burning the retry budget on all
 *  of them turns one outage into a much longer stall.
 *
 *  Returns what is still owed afterwards, so a caller can block submission on
 *  a number rather than on a boolean it has to trust.
 */
export async function drain(
  attemptId: string,
  deliverOne: (entry: Pending) => Promise<{ ok: boolean; detail: string }>,
): Promise<{ delivered: number; remaining: number }> {
  let delivered = 0;
  for (const entry of await outstanding(attemptId)) {
    const result = await deliverOne(entry);
    if (result.ok) {
      await forget(entry.responseId);
      delivered += 1;
      continue;
    }
    await noteFailure(entry.responseId, result.detail);
    break;
  }
  return { delivered, remaining: await count(attemptId) };
}

/** Whether this browser can keep anything at all.
 *
 *  Private windows in some browsers expose `indexedDB` and then refuse to
 *  open it. A runner that assumed durability it does not have would be worse
 *  than one that knows it is not durable and says so.
 */
export function available(): boolean {
  try {
    return typeof indexedDB !== "undefined" && indexedDB !== null;
  } catch {
    return false;
  }
}

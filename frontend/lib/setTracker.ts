/**
 * Set tracker — prevents the same passage/prompt from appearing twice
 * in the same practice session for the same student.
 *
 * Uses localStorage keyed by skill + date. Resets daily so a new day
 * starts fresh.
 */

const TRACKER_KEY = "commiq.set_tracker";

interface TrackerData {
  /** ISO date string — resets when the date changes */
  date: string;
  /** Map of skill → Set of attempted IDs */
  attempted: Record<string, string[]>;
}

function getTracker(): TrackerData {
  if (typeof window === "undefined") return { date: todayStr(), attempted: {} };
  try {
    const raw = localStorage.getItem(TRACKER_KEY);
    if (!raw) return { date: todayStr(), attempted: {} };
    const data = JSON.parse(raw) as TrackerData;
    // Reset if date changed
    if (data.date !== todayStr()) {
      return { date: todayStr(), attempted: {} };
    }
    return data;
  } catch {
    return { date: todayStr(), attempted: {} };
  }
}

function saveTracker(data: TrackerData) {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(TRACKER_KEY, JSON.stringify(data));
  } catch {
    // localStorage full or unavailable — silently ignore
  }
}

function todayStr(): string {
  return new Date().toISOString().slice(0, 10);
}

/** Mark an ID as attempted for a given skill */
export function markAttempted(skill: string, id: string) {
  const tracker = getTracker();
  if (!tracker.attempted[skill]) tracker.attempted[skill] = [];
  if (!tracker.attempted[skill].includes(id)) {
    tracker.attempted[skill].push(id);
  }
  saveTracker(tracker);
}

/** Get IDs already attempted for a skill today */
export function getAttempted(skill: string): string[] {
  const tracker = getTracker();
  return tracker.attempted[skill] || [];
}

/** Filter out already-attempted IDs from a list */
export function filterUnattempted<T extends { id: string }>(skill: string, items: T[]): T[] {
  const attempted = new Set(getAttempted(skill));
  return items.filter((item) => !attempted.has(item.id));
}

/** Reset tracker for a skill (or all skills) */
export function resetTracker(skill?: string) {
  const tracker = getTracker();
  if (skill) {
    delete tracker.attempted[skill];
  } else {
    tracker.attempted = {};
  }
  saveTracker(tracker);
}

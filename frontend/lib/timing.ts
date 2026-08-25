/**
 *  The section clock. Advisory, and that is a decision rather than a
 *  shortcut.
 *
 *  Four clocks exist and they are not interchangeable:
 *
 *      prep            per item, before the tone            unchanged
 *      item response   per item, the recording window       unchanged
 *      section         this file                            advisory
 *      assessment      server-enforced, one hard stop       app/deadline.py
 *
 *  **Why this one never interrupts.** The item timer already bounds every
 *  recording. A section clock that could also stop one would be a second
 *  authority over the same audio, and the moment two things can end a
 *  recording is the moment answers start getting cut in half — somebody
 *  mid-sentence when a budget they were never shown ran out. So this counts,
 *  it warns, and it does nothing else. A candidate who is slow finishes the
 *  section late and keeps every word they said.
 *
 *  The budget is computed from the section's own items rather than stored, so
 *  it cannot disagree with the items sitting next to it on screen.
 */

/** Just enough of a runner item to cost it. */
export interface Timed {
  section_id: string;
  prep_seconds: number;
  response_seconds: number;
  prompt_plays_allowed: number;
  response_mode: string;
}

/** Seconds allowed for a played prompt. Mirrors the estimate the backend
 *  uses in `formats.PLAY_SECONDS`; approximate on both sides, and only ever
 *  used to draw a clock. */
export const PLAY_SECONDS = 8;

/** What an untimed item costs. A written or chosen answer has no window, and
 *  a section full of them is not instantaneous. */
export const UNTIMED_SECONDS = 30;

/** Between items: the next screen, the tone, settling. */
export const TRANSITION_SECONDS = 3;

export function itemSeconds(item: Timed): number {
  const answering = item.response_seconds || UNTIMED_SECONDS;
  return item.prep_seconds + answering + TRANSITION_SECONDS
    + (item.prompt_plays_allowed > 0 ? PLAY_SECONDS : 0);
}

/** The whole budget for the section this item belongs to. */
export function sectionBudget(items: Timed[], sectionId: string): number {
  return items
    .filter((i) => i.section_id === sectionId)
    .reduce((total, i) => total + itemSeconds(i), 0);
}

/** What is left of the section budget, given how long has been spent in it.
 *
 *  Floors at zero. A section that has overrun shows nothing left rather than
 *  a negative number — the overrun is not the candidate's problem to solve,
 *  and counting up past the end would read as a penalty.
 */
export function sectionRemaining(budgetSeconds: number,
                                 elapsedSeconds: number): number {
  return Math.max(0, Math.round(budgetSeconds - elapsedSeconds));
}

export type SectionMood = "fine" | "warn" | "over";

/** How to draw it. Warns at a quarter left, which is far enough out to be
 *  worth knowing and late enough not to nag for the whole section. */
export const WARN_FRACTION = 0.25;

export function sectionMood(remaining: number, budget: number): SectionMood {
  if (remaining <= 0) return "over";
  if (budget > 0 && remaining / budget <= WARN_FRACTION) return "warn";
  return "fine";
}

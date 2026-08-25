/**
 *  What the runner does after an item finishes.
 *
 *  Three inputs, one decision, and it is pulled out here because getting it
 *  wrong is invisible from inside the component: the sequence simply carries
 *  on, and the only symptom is a server refusing answers a candidate is still
 *  giving.
 */

export type Step = "next" | "submit";

export interface SequenceState {
  /** Zero-based position of the item that has just finished. */
  index: number;
  total: number;
  /** True once the whole-sitting clock has run out. */
  expired: boolean;
}

/**
 *  Where to go after an item.
 *
 *  **Expiry ends the sequence, not just the item.** The first version of this
 *  lived inline and only set the flag that cuts a countdown short — so the
 *  runner finished the current item early and then moved to the next one.
 *  Every answer after the bell was refused by the server, correctly, while
 *  the candidate kept working through questions that could no longer count.
 *  Nothing was mis-scored; they were simply left talking to a wall.
 *
 *  "Expiry submits the work that exists" has to mean the runner stops asking
 *  for more.
 */
/**
 *  Where a reload resumes.
 *
 *  The first item the server does not already hold an answer for. A runner
 *  that always began at item 1 made a candidate who refreshed redo every
 *  item -- each re-recording refused as a duplicate, the section budget
 *  burning all the while (hardware UAT, D7). Returns -1 when everything is
 *  answered, which means "submit", not "start again".
 */
export function firstOpenIndex(items: ReadonlyArray<{ answered: boolean }>): number {
  return items.findIndex((i) => !i.answered);
}

export function nextStep(state: SequenceState): Step {
  if (state.expired) return "submit";
  return state.index + 1 < state.total ? "next" : "submit";
}

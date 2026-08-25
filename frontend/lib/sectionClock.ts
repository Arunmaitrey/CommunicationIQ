/**
 *  Section-budget expiry, as a decision rather than an effect.
 *
 *  SVAR-style Sections A, C and D carry a budget. When it runs out the
 *  candidate must not be left sitting at "Play Audio" on a dead clock
 *  (hardware UAT, D3): an item still waiting at a gate is passed over, an
 *  item being recorded or answered is left to finish, and everything after
 *  it in the section is passed over by `advance`.
 */
export type GatePhase = "listen" | "armed" | "prep" | "ack";

const GATES: ReadonlySet<string> = new Set<GatePhase>(["listen", "armed", "prep", "ack"]);

export interface ExpiryDecision {
  /** The section's clock has reached zero (first time this is reported). */
  expired: boolean;
  /** The current item is waiting at a gate and must be released and passed over. */
  releaseGate: boolean;
}

export function sectionExpiry(args: {
  budgetSeconds: number; elapsedSeconds: number;
  alreadyExpired: boolean; phase: string;
}): ExpiryDecision {
  const { budgetSeconds, elapsedSeconds, alreadyExpired, phase } = args;
  if (budgetSeconds <= 0 || elapsedSeconds < budgetSeconds || alreadyExpired) {
    return { expired: false, releaseGate: false };
  }
  return { expired: true, releaseGate: GATES.has(phase) };
}

/** Seconds left on a wall-clock deadline, never negative, whole seconds up. */
export function remainingSeconds(endAtMs: number, nowMs: number): number {
  return Math.max(0, Math.ceil((endAtMs - nowMs) / 1000));
}

/** Position and total within a lettered group of runner items.
 *
 *  In a clip-gated section (Mettl Section D) each clip's own screen is a
 *  numbered item -- "Q.1 Listen to the given audio ... Type in 'Okay'" -- so
 *  four clips of three questions number 1..16, not 1..12. `firstOfPassage`
 *  holds the response ids that own their clip's playback. */
export function groupNumbering(
  groupItems: ReadonlyArray<{ response_id: string; ack_gate: string; passage_ref: string }>,
  responseId: string, firstOfPassage: ReadonlySet<string>,
): { no: number; total: number } {
  let no = 0, total = 0, mine = 0;
  for (const it of groupItems) {
    const clipScreen = it.ack_gate === "clip" && it.passage_ref !== "" && firstOfPassage.has(it.response_id);
    if (clipScreen) total += 1;
    total += 1;
    if (mine === 0) {
      if (clipScreen) no += 1;
      no += 1;
      if (it.response_id === responseId) mine = no;
    }
  }
  return { no: mine, total };
}

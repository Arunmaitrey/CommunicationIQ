/**
 *  How long an assessment takes, said truthfully.
 *
 *  `estimated_minutes` is the computed ceiling of every timed window; it is
 *  not a cap on the sitting. Three different clocks can exist and the line
 *  keeps them apart:
 *
 *  * a *section budget* (SVAR-style Section A 10 min, C 15 min, D 10 min),
 *    which the runner shows and stops progression on;
 *  * per-item recording windows on spoken tasks;
 *  * the server's *sitting safety stop* (estimate plus grace), which is a
 *    safeguard, not the assessment's own timing.
 *
 *  So: a range at a normal pace, which sections carry a budget (or, where
 *  none do, which sections are untimed), and the safety stop named as such.
 */
import type { ProfileSection } from "./api";

/** What an untimed section is *about*, for the sentence. */
const UNTIMED_LABEL: Record<string, string> = {
  sentence_completion: "grammar",
  voice_change: "grammar",
  listening_comprehension: "comprehension",
  reading_comprehension: "comprehension",
  response_selection: "multiple-choice",
  vocabulary_in_context: "vocabulary",
  dictation: "dictation",
  email_writing: "writing",
  passage_reconstruction: "writing",
};

function joinList(parts: string[]): string {
  return parts.length === 1 ? parts[0]
    : `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`;
}

export function untimedNote(sections: ProfileSection[]): string {
  const kinds: string[] = [];
  for (const s of sections) {
    if (s.response_seconds > 0) continue;
    const k = UNTIMED_LABEL[s.task_type] ?? "written";
    if (!kinds.includes(k)) kinds.push(k);
  }
  if (kinds.length === 0) return "";
  const noun = kinds.length === 1 ? "section is" : "sections are";
  const phrase = `${joinList(kinds)} ${noun} untimed`;
  return phrase.charAt(0).toUpperCase() + phrase.slice(1);
}

/** "Section A" from "Section A1 - Read & Say Aloud"; empty if unlettered. */
function letterOf(title: string): string {
  const m = /\b(?:section|part)\s*-?\s*([a-h])\d*\b/i.exec(title);
  return m ? m[1].toUpperCase() : "";
}

/** Which lettered sections carry a budget: "Sections A, C and D have section budgets; ..." */
export function budgetNote(sections: ProfileSection[]): string {
  const letters: string[] = [];
  for (const s of sections) {
    if (!(s.budget_seconds > 0)) continue;
    const l = letterOf(s.title) || s.title;
    if (!letters.includes(l)) letters.push(l);
  }
  if (letters.length === 0) return "";
  const head = letters.length === 1 ? `Section ${letters[0]} has a section budget`
    : `Sections ${joinList(letters)} have section budgets`;
  return `${head}; individual speaking/recording tasks also have their own windows`;
}

export function paceRange(typical: number, ceiling: number): string {
  const lo = typical > 0 && typical < ceiling ? typical : ceiling;
  return lo === ceiling ? `About ${ceiling} minutes` : `About ${lo}\u2013${ceiling} minutes`;
}

/** The full line for a card: pace · budgets (or untimed note) · safety stop. */
export function durationLine(p: {
  typical_minutes: number; estimated_minutes: number;
  sitting_limit_minutes: number; sections: ProfileSection[];
}): string {
  const parts = [`${paceRange(p.typical_minutes, p.estimated_minutes)} at a normal pace`];
  const budgets = budgetNote(p.sections);
  const untimed = untimedNote(p.sections);
  if (budgets) parts.push(budgets);
  else if (untimed) parts.push(untimed);
  if (p.sitting_limit_minutes > 0) parts.push(`Sitting safety stop after ${p.sitting_limit_minutes} minutes`);
  return parts.join(" \u00b7 ");
}

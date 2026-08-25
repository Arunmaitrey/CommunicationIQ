import { describe, expect, it } from "vitest";

import type { ProfileSection } from "./api";
import { budgetNote, durationLine, paceRange, untimedNote } from "./duration";

function sec(task_type: string, response_seconds: number, title = task_type,
             budget_seconds = 0): ProfileSection {
  return { id: title, position: 0, title, task_type, instructions: "",
           item_count: 1, prep_seconds: 0, response_seconds, prompt_plays_allowed: 0,
           allow_replay: false, weight: 1, selection: {}, budget_seconds } as unknown as ProfileSection;
}

const SVAR = [
  sec("read_aloud", 15, "Section A1 - Read & Say Aloud (Sentence)", 600),
  sec("repeat_sentence", 15, "Section A3 - Listen & Say Aloud", 600),
  sec("open_response", 60, "Section B - Speak on the Topic"),
  sec("sentence_completion", 0, "Section C1 - Verb Forms", 900),
  sec("voice_change", 0, "Section C5 - Change the Voice (Active/Passive)", 900),
  sec("listening_comprehension", 0, "Section D - Listen & Answer", 600),
];

describe("duration copy says what the implementation does", () => {
  it("SVAR-style: pace range, section budgets, and the safety stop named as such", () => {
    const line = durationLine({ typical_minutes: 51, estimated_minutes: 54,
                                sitting_limit_minutes: 81, sections: SVAR });
    expect(line).toBe("About 51\u201354 minutes at a normal pace \u00b7 "
      + "Sections A, C and D have section budgets; individual speaking/recording "
      + "tasks also have their own windows \u00b7 Sitting safety stop after 81 minutes");
    expect(line).not.toMatch(/up to/i);
    expect(line).not.toMatch(/untimed overall/i);
  });

  it("a format with no section budgets names its untimed sections instead", () => {
    const line = durationLine({ typical_minutes: 25, estimated_minutes: 28, sitting_limit_minutes: 42,
      sections: [sec("read_aloud", 15), sec("sentence_completion", 0), sec("listening_comprehension", 0)] });
    expect(line).toContain("Grammar and comprehension sections are untimed");
    expect(budgetNote(SVAR)).toMatch(/^Sections A, C and D have section budgets/);
    expect(untimedNote([sec("sentence_completion", 0)])).toBe("Grammar section is untimed");
  });

  it("collapses the range when typical is unknown or not smaller", () => {
    expect(paceRange(0, 8)).toBe("About 8 minutes");
    expect(paceRange(8, 8)).toBe("About 8 minutes");
    expect(paceRange(6, 8)).toBe("About 6\u20138 minutes");
  });
});

/**
 *  Every task type the server can serve must have a name a person recognises.
 *
 *  The runner's label map had six of sixteen. Each of these maps ends in
 *  `?? key`, so a missing entry is not a blank -- it renders the enum. A
 *  candidate partway through a hiring assessment was shown the words
 *  `reading_comprehension` where the section name belongs, on a screen they
 *  cannot go back from.
 *
 *  The list below is checked against the server's own by
 *  `backend/tests/test_task_labels.py`, which reads this file. Two lists that
 *  agree only because somebody remembered is what produced the bug.
 */
import { describe, expect, it } from "vitest";

import { TASK_LABEL, answerLine, taskLabel, whatToExpect } from "./tasks";

/** Mirrors `app.sections.SKILL_OF_TASK`. Kept in step by a backend test. */
export const SERVER_TASK_TYPES = [
  "conversation_question",
  "dictation",
  "email_writing",
  "listening_comprehension",
  "open_response",
  "passage_question",
  "passage_reconstruction",
  "read_aloud",
  "reading_comprehension",
  "repeat_sentence",
  "spoken_completion",
  "spoken_correction",
  "response_selection",
  "sentence_build",
  "sentence_completion",
  "voice_change",
  "short_answer",
  "story_retell",
  "vocabulary_in_context",
];

describe("task labels", () => {
  it("names every task type the server can put in a section", () => {
    const missing = SERVER_TASK_TYPES.filter((t) => !TASK_LABEL[t]);
    expect(missing).toEqual([]);
  });

  it("never renders a raw enum for a real task type", () => {
    for (const type of SERVER_TASK_TYPES) {
      expect(taskLabel(type)).not.toBe(type);
      expect(taskLabel(type)).not.toMatch(/_/);
    }
  });

  it("falls back to the key for something genuinely unknown", () => {
    // Not ideal, but better than blank -- and the test above is what stops a
    // real task type ever reaching this path.
    expect(taskLabel("something_new")).toBe("something_new");
  });
});

describe("what a candidate is told to expect", () => {
  it("does not mention speaking on an item answered by clicking", () => {
    // The bug: "You will have 0 seconds to read, then 0 seconds to speak" on
    // an untimed reading-comprehension item. Wrong twice over, and it reads
    // as a fault in the test rather than a sentence about the test.
    const said = whatToExpect("select", 0, 0, 0);
    expect(said).not.toMatch(/speak/i);
    expect(said).not.toMatch(/\b0 seconds/);
    expect(said).toMatch(/no timer/i);
  });

  it("does not mention speaking on an item answered by typing", () => {
    const said = whatToExpect("write", 0, 0, 0);
    expect(said).not.toMatch(/speak/i);
    expect(said).toMatch(/type/i);
  });

  it("never promises zero seconds of anything", () => {
    for (const mode of ["speak", "select", "write"]) {
      for (const plays of [0, 1]) {
        expect(whatToExpect(mode, 0, 0, plays)).not.toMatch(/\b0 seconds/);
      }
    }
  });

  it("still says the right thing for a spoken item", () => {
    expect(whatToExpect("speak", 5, 20, 0)).toBe(
      "You will have 5 seconds to read, then 20 seconds to speak.");
    expect(whatToExpect("speak", 0, 20, 0)).toBe(
      "You will have 20 seconds to speak.");
    expect(whatToExpect("speak", 0, 30, 1)).toMatch(/hear each item once/);
  });

  it("says the item is timed when it is", () => {
    expect(whatToExpect("select", 0, 45, 0)).toMatch(/45 seconds/);
    expect(whatToExpect("select", 0, 45, 0)).toMatch(/choose/);
  });
});


describe("answer-screen instruction is task-aware (shared P2 from the portfolio audit)", () => {
  it("never says 'say it back' where repetition is not the task", () => {
    const notRepeat = ["short_answer", "conversation_question", "spoken_completion",
                       "spoken_correction", "story_retell", "open_response",
                       "sentence_build", "passage_question"];
    for (const t of notRepeat) {
      expect(answerLine(t).toLowerCase()).not.toMatch(/say it back|repeat/);
    }
    expect(answerLine("repeat_sentence")).toBe("Repeat the sentence you heard.");
  });

  it("says the right action for every heard task", () => {
    expect(answerLine("short_answer")).toBe("Answer the question.");
    expect(answerLine("conversation_question")).toBe("Respond to what you heard.");
    expect(answerLine("spoken_completion")).toBe("Say the complete sentence with the missing word.");
    expect(answerLine("spoken_correction")).toBe("Say the corrected sentence.");
    expect(answerLine("story_retell")).toBe("Retell the story in your own words.");
    expect(answerLine("open_response")).toBe("Speak about the topic.");
    expect(answerLine("sentence_build")).toBe("Rearrange the words into a correct sentence and say it.");
    expect(answerLine("passage_question")).toBe("Answer the question about what you heard.");
  });
});

/**
 *  The section clock, at its boundaries.
 *
 *  The assertion that carries the weight is the one about what this clock
 *  *cannot* do: there is no function here that returns "stop the recording",
 *  because a second authority over one recording is how answers get cut in
 *  half. Everything else is arithmetic.
 */
import { describe, expect, it } from "vitest";

import {
  PLAY_SECONDS, TRANSITION_SECONDS, UNTIMED_SECONDS, WARN_FRACTION,
  itemSeconds, sectionBudget, sectionMood, sectionRemaining, type Timed,
} from "./timing";

function item(over: Partial<Timed> = {}): Timed {
  return {
    section_id: "s1", prep_seconds: 0, response_seconds: 20,
    prompt_plays_allowed: 0, response_mode: "speak", ...over,
  };
}

describe("costing an item", () => {
  it("counts the window, the prep and the gap after it", () => {
    expect(itemSeconds(item({ prep_seconds: 5, response_seconds: 20 })))
      .toBe(5 + 20 + TRANSITION_SECONDS);
  });

  it("counts a played prompt", () => {
    expect(itemSeconds(item({ prompt_plays_allowed: 1 })))
      .toBe(20 + TRANSITION_SECONDS + PLAY_SECONDS);
  });

  it("an untimed item is untimed, not instantaneous", () => {
    // A section of six reading questions has no response window and takes
    // several minutes. Costing it at zero would show a section budget of
    // three seconds and a clock that was over before it started.
    expect(itemSeconds(item({ response_seconds: 0 })))
      .toBe(UNTIMED_SECONDS + TRANSITION_SECONDS);
  });
});

describe("the section budget", () => {
  it("adds up only its own section's items", () => {
    const items = [
      item({ section_id: "a", response_seconds: 10 }),
      item({ section_id: "a", response_seconds: 10 }),
      item({ section_id: "b", response_seconds: 60 }),
    ];
    expect(sectionBudget(items, "a")).toBe(2 * (10 + TRANSITION_SECONDS));
    expect(sectionBudget(items, "b")).toBe(60 + TRANSITION_SECONDS);
  });

  it("a section id nobody has is zero, not a crash", () => {
    expect(sectionBudget([item()], "nope")).toBe(0);
  });
});

describe("what is left", () => {
  it("counts down", () => {
    expect(sectionRemaining(120, 0)).toBe(120);
    expect(sectionRemaining(120, 45)).toBe(75);
  });

  it("floors at zero rather than counting up past the end", () => {
    // An overrun is not the candidate's problem to solve, and a clock going
    // negative in front of somebody mid-answer reads as a penalty.
    expect(sectionRemaining(120, 121)).toBe(0);
    expect(sectionRemaining(120, 600)).toBe(0);
  });

  it("is exact at the boundary", () => {
    expect(sectionRemaining(120, 120)).toBe(0);
    expect(sectionRemaining(120, 119)).toBe(1);
  });
});

describe("how it is drawn", () => {
  it("is calm for most of the section", () => {
    expect(sectionMood(100, 120)).toBe("fine");
    expect(sectionMood(31, 120)).toBe("fine");
  });

  it("warns at the threshold exactly", () => {
    expect(sectionMood(120 * WARN_FRACTION, 120)).toBe("warn");
    expect(sectionMood(120 * WARN_FRACTION + 1, 120)).toBe("fine");
  });

  it("says over rather than warning forever", () => {
    expect(sectionMood(0, 120)).toBe("over");
  });

  it("a zero budget does not divide by zero", () => {
    expect(sectionMood(0, 0)).toBe("over");
    expect(sectionMood(10, 0)).toBe("fine");
  });
});

describe("what this clock deliberately cannot do", () => {
  it("exposes no way to end an item", async () => {
    // Stated as a test because it is a design decision that a future change
    // could quietly reverse. The item timer bounds every recording; if this
    // module ever grows a "should this item stop" function, two things can
    // end one recording and somebody gets cut off mid-sentence.
    const surface = Object.keys(await import("./timing"));
    for (const name of surface) {
      expect(name.toLowerCase()).not.toContain("stop");
      expect(name.toLowerCase()).not.toContain("advance");
      expect(name.toLowerCase()).not.toContain("interrupt");
    }
  });
});

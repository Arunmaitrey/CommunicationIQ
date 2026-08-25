/**
 *  Where the runner goes after an item.
 *
 *  Small enough to look not worth testing, which is exactly why it had a bug:
 *  the expiry branch did not exist, and the symptom was invisible from inside
 *  the component.
 */
import { describe, expect, it } from "vitest";

import { firstOpenIndex, nextStep } from "./sequence";

describe("after an item", () => {
  it("goes to the next one when there is one", () => {
    expect(nextStep({ index: 0, total: 5, expired: false })).toBe("next");
    expect(nextStep({ index: 3, total: 5, expired: false })).toBe("next");
  });

  it("submits after the last one", () => {
    expect(nextStep({ index: 4, total: 5, expired: false })).toBe("submit");
  });

  it("submits the moment the sitting expires, wherever we are", async () => {
    // The defect. Expiry used to cut the current item short and then carry
    // on, so every later answer was refused by the server while the candidate
    // kept working through questions that could no longer count.
    for (const index of [0, 1, 2, 3, 4]) {
      expect(nextStep({ index, total: 5, expired: true })).toBe("submit");
    }
  });

  it("a one-item assessment submits after its only item", () => {
    expect(nextStep({ index: 0, total: 1, expired: false })).toBe("submit");
  });

  it("expiry on the final item is still a submit, not a double submit", () => {
    expect(nextStep({ index: 4, total: 5, expired: true })).toBe("submit");
  });
});


describe("resume position (hardware UAT D7)", () => {
  it("starts at the first item the server does not hold", () => {
    expect(firstOpenIndex([{ answered: true }, { answered: true }, { answered: false }, { answered: false }])).toBe(2);
    expect(firstOpenIndex([{ answered: false }])).toBe(0);
  });
  it("reports -1 when everything is answered, which means submit", () => {
    expect(firstOpenIndex([{ answered: true }, { answered: true }])).toBe(-1);
    expect(firstOpenIndex([])).toBe(-1);
  });
});

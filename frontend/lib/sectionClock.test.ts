import { describe, expect, it } from "vitest";

import { groupNumbering, remainingSeconds, sectionExpiry } from "./sectionClock";

describe("section budget expiry (hardware UAT D3)", () => {
  it("passes over an item still waiting at Play Audio / Start Recording / thinking", () => {
    for (const phase of ["listen", "armed", "prep"]) {
      expect(sectionExpiry({ budgetSeconds: 600, elapsedSeconds: 600,
                             alreadyExpired: false, phase }))
        .toEqual({ expired: true, releaseGate: true });
    }
  });

  it("never touches an item being recorded or answered", () => {
    for (const phase of ["answer", "respond", "saving", "prompt"]) {
      expect(sectionExpiry({ budgetSeconds: 600, elapsedSeconds: 601,
                             alreadyExpired: false, phase }))
        .toEqual({ expired: true, releaseGate: false });
    }
  });

  it("does nothing before the budget, with no budget, or twice", () => {
    expect(sectionExpiry({ budgetSeconds: 600, elapsedSeconds: 599, alreadyExpired: false, phase: "listen" }).expired).toBe(false);
    expect(sectionExpiry({ budgetSeconds: 0, elapsedSeconds: 9999, alreadyExpired: false, phase: "listen" }).expired).toBe(false);
    expect(sectionExpiry({ budgetSeconds: 600, elapsedSeconds: 900, alreadyExpired: true, phase: "listen" }).expired).toBe(false);
  });
});

describe("wall-clock countdown (hardware UAT D4)", () => {
  it("is computed from the clock, so a throttled tab cannot stretch a window", () => {
    const endAt = 1_000_000;
    // Ten seconds of wall time passed while the tab slept: the display must
    // show the true remainder, not "one tick later".
    expect(remainingSeconds(endAt, endAt - 90_000)).toBe(90);
    expect(remainingSeconds(endAt, endAt - 80_000)).toBe(80);
    expect(remainingSeconds(endAt, endAt - 500)).toBe(1);
    expect(remainingSeconds(endAt, endAt)).toBe(0);
    expect(remainingSeconds(endAt, endAt + 5_000)).toBe(0);
  });
});


describe("group numbering counts clip screens in a clip-gated section (Mettl D)", () => {
  const items = [
    { response_id: "q1", ack_gate: "clip", passage_ref: "p1" },
    { response_id: "q2", ack_gate: "clip", passage_ref: "p1" },
    { response_id: "q3", ack_gate: "clip", passage_ref: "p1" },
    { response_id: "q4", ack_gate: "clip", passage_ref: "p2" },
    { response_id: "q5", ack_gate: "clip", passage_ref: "p2" },
    { response_id: "q6", ack_gate: "clip", passage_ref: "p2" },
  ];
  const first = new Set(["q1", "q4"]);
  it("numbers 1..8 for two clips of three questions", () => {
    expect(groupNumbering(items, "q1", first)).toEqual({ no: 2, total: 8 });
    expect(groupNumbering(items, "q3", first)).toEqual({ no: 4, total: 8 });
    expect(groupNumbering(items, "q4", first)).toEqual({ no: 6, total: 8 });
    expect(groupNumbering(items, "q6", first)).toEqual({ no: 8, total: 8 });
  });
  it("is plain 1..n without a clip gate (SVAR D stays 1..12)", () => {
    const plain = items.map((i) => ({ ...i, ack_gate: "section" }));
    expect(groupNumbering(plain, "q6", first)).toEqual({ no: 6, total: 6 });
  });
  it("the ack gate is released on section expiry", () => {
    expect(sectionExpiry({ budgetSeconds: 600, elapsedSeconds: 600, alreadyExpired: false, phase: "ack" }).releaseGate).toBe(true);
  });
});

describe("continuous numbering across sub-sections (Cognizant Section A)", () => {
  // The defect: 1/8 → 1/3 → 1/8 read as the assessment restarting. The
  // source numbers Section A continuously (Q1–Q23), so the first word-list
  // item must show as question 9 of 19, not 1 of 3.
  it("numbers a letter's sub-sections as one sequence", () => {
    const items = [
      ...Array.from({ length: 8 }, (_, n) => ({ response_id: `read-${n}`, ack_gate: "", passage_ref: "" })),
      ...Array.from({ length: 3 }, (_, n) => ({ response_id: `words-${n}`, ack_gate: "", passage_ref: "" })),
      ...Array.from({ length: 8 }, (_, n) => ({ response_id: `repeat-${n}`, ack_gate: "", passage_ref: "" })),
    ];
    expect(groupNumbering(items, "words-0", new Set())).toEqual({ no: 9, total: 19 });
    expect(groupNumbering(items, "repeat-0", new Set())).toEqual({ no: 12, total: 19 });
    expect(groupNumbering(items, "repeat-7", new Set())).toEqual({ no: 19, total: 19 });
  });
});

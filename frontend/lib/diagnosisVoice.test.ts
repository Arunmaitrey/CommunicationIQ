/**
 *  One diagnosis voice on every result view.
 *
 *  The student result, the trainer's student view and the employer's
 *  invitation result all render the same report components. None of them
 *  may draw the engine's weighted "biggest lever" or the gain-ranked
 *  recommendation table as an answer to "what should I work on first?" --
 *  those were the second and third voices the candidate UAT caught.
 */
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const VIEWS = [
  "app/(app)/results/[id]/page.tsx",
  "app/(app)/cohorts/[id]/students/[userId]/page.tsx",
  "app/(app)/tenant/invitations/[id]/result/page.tsx",
  "components/Report.tsx",
];

describe("no second chooser on any result view", () => {
  for (const view of VIEWS) {
    it(`${view} renders neither the lever nor the gain table`, () => {
      const src = readFileSync(view, "utf8");
      // Comments may explain the history; code may not read the fields.
      const code = src.replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, "");
      expect(code).not.toMatch(/\bbiggest_lever\b/);
      expect(code).not.toMatch(/\.recommendations\b/);
      expect(code).not.toMatch(/predicted_gain/);
      expect(code).not.toMatch(/biggest lever/i);
    });
  }

  it("the student result draws the diagnosis card and nothing derives one", () => {
    const src = readFileSync(VIEWS[0], "utf8");
    expect(src).toContain("WhatToWorkOnFirst");
    expect(src).toContain("data.primary_diagnosis");
    // No min-by-score over the dimensions map anywhere on the page.
    expect(src).not.toMatch(/Math\.min\([^)]*dimensions/);
    expect(src).not.toMatch(/sort\([^)]*score[^)]*\)/);
  });
});

// @vitest-environment jsdom
/**
 *  The report, rendered.
 *
 *  Written after a bug that no amount of backend testing could have caught,
 *  and that I found only by sitting an assessment by hand: an assessment can
 *  be entirely reading and writing, and that candidate was told their
 *  recordings were kept, that every figure came from their recording, and
 *  that what they typed was "heard". Three true sentences about somebody
 *  else's attempt.
 *
 *  The other half is the By skill panel, which had the opposite problem. The
 *  server has returned the four-skill rollup since M7; nothing declared it and
 *  nothing drew it, so it was computed on every attempt and shown to nobody.
 *  Correct code, invisible.
 *
 *  Both failure modes are only visible at the render. Hence this file.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { describe as describeError } from "./ListenBack";
import { Evidence, Highlights, Plan, Skills, Summary, answerLabel,
         itemsFootnote } from "./Report";
import type { SectionResult, SkillScore } from "@/lib/api";

afterEach(cleanup);

function section(over: Partial<SectionResult> = {}): SectionResult {
  return {
    section_id: "s1", position: 1, title: "Reading", task_type:
      "reading_comprehension", skill: "reading", score: 40,
    dimensions: {}, confidence: 0.5, weight: 1, items_total: 3,
    items_answered: 3, unscored_reason: "", ...over,
  };
}

function skill(over: Partial<SkillScore> = {}): SkillScore {
  return {
    skill: "reading", score: 40, section_count: 1, unscored_sections: [],
    note: "", ...over,
  };
}

describe("what a candidate's answers are called", () => {
  it("says heard for a recording and wrote for typing", () => {
    // The whole bug, in one line each way.
    expect(answerLabel(true)).toContain("heard");
    expect(answerLabel(false)).toContain("wrote");
    expect(answerLabel(false)).not.toContain("heard");
  });

  it("never invites a candidate to hear back something they typed", () => {
    const written = itemsFootnote(false);
    expect(written).not.toMatch(/hear|recording|listen/i);
    expect(written).toContain("what you gave");
  });

  it("still offers the listen-back where there is audio", () => {
    expect(itemsFootnote(true)).toMatch(/hear it back/);
  });
});

describe("the By skill panel", () => {
  it("shows each skill and the sections underneath it", () => {
    render(<Skills scaleMin={20} scaleMax={80}
                   skills={[skill(), skill({ skill: "writing", score: 20 })]}
                   sections={[section(),
                              section({ section_id: "s2", position: 2,
                                        title: "Sentence Completion",
                                        skill: "writing", score: 20 })]} />);

    expect(screen.getByText("reading")).toBeInTheDocument();
    expect(screen.getByText("writing")).toBeInTheDocument();
    expect(screen.getByText("Sentence Completion")).toBeInTheDocument();
  });

  it("annotates a weighted section and leaves a default one bare", () => {
    // The reason section weighting existed and did nothing for six phases was
    // that nobody could see what a section counted for. Showing "1 part" on
    // every row would be noise; showing nothing on a 3 would be the old bug
    // wearing a new coat.
    render(<Skills scaleMin={20} scaleMax={80}
                   skills={[skill({ section_count: 2 }),
                            skill({ skill: "writing", score: 20 })]}
                   sections={[section({ weight: 3 }),
                              section({ section_id: "s2", position: 2,
                                        title: "Sentence Completion",
                                        skill: "writing", score: 20 })]} />);

    expect(screen.getByText(/3 parts/)).toBeInTheDocument();
    expect(screen.queryByText(/1 part\b/)).not.toBeInTheDocument();
  });

  it("says plainly when a section does not count at all", () => {
    render(<Skills scaleMin={20} scaleMax={80}
                   skills={[skill(), skill({ skill: "writing", score: 20 })]}
                   sections={[section({ title: "Warm-up", weight: 0 }),
                              section({ section_id: "s2", position: 2,
                                        title: "Sentence Completion",
                                        skill: "writing", score: 20 })]} />);

    expect(screen.getByText(/does not count/)).toBeInTheDocument();
  });

  it("draws nothing when only one skill was measured", () => {
    // One skill is not a rollup. It is the overall score again under a
    // different heading, and a panel promising to separate skills that shows
    // exactly one is worse than no panel.
    const { container } = render(
      <Skills scaleMin={20} scaleMax={80} skills={[skill()]}
              sections={[section()]} />);

    expect(container).toBeEmptyDOMElement();
  });

  it("shows an unscored section rather than quietly dropping it", () => {
    render(<Skills scaleMin={20} scaleMax={80}
                   skills={[skill(), skill({ skill: "writing", score: 20 })]}
                   sections={[section({ score: null,
                                        unscored_reason: "No audio arrived." }),
                              section({ section_id: "s2", position: 2,
                                        title: "Sentence Completion",
                                        skill: "writing", score: 20 })]} />);

    expect(screen.getByText("No audio arrived.")).toBeInTheDocument();
  });

  it("carries the skill's own note about what is missing", () => {
    render(<Skills scaleMin={20} scaleMax={80}
                   skills={[skill({ note: "1 of 2 sections could not be scored." }),
                            skill({ skill: "writing", score: 20 })]}
                   sections={[section(),
                              section({ section_id: "s2", position: 2,
                                        title: "Sentence Completion",
                                        skill: "writing", score: 20 })]} />);

    expect(screen.getByText(/could not be scored/)).toBeInTheDocument();
  });
});

describe("what the listen-back panel is willing to say", () => {
  it("describes each kind of word-accuracy finding", () => {
    expect(describeError({ kind: "deletion", expected: "manager" }))
      .toBe('missed "manager"');
    expect(describeError({ kind: "insertion", heard: "um" })).toBe('added "um"');
    expect(describeError({ kind: "substitution", expected: "the", heard: "a" }))
      .toBe('"the" → "a"');
    expect(describeError({ kind: "word_order" })).toMatch(/order was not/);
  });

  it("says nothing rather than undefined when handed the wrong measurement", () => {
    // The bug. This panel was fed per-word clarity scores -- {word, score,
    // posterior} -- which carry no kind, no expected and no heard. Every one
    // of them fell through to the substitution template and rendered
    // `"undefined" → "undefined"`, twelve at a time, under a heading
    // promising a comparison against the sentence the candidate was given.
    const clarity = { word: "department", score: 20.0, posterior: 0.055 };

    expect(describeError(clarity as never)).toBe("");
  });

  it("says nothing for a half-formed finding either", () => {
    // Defensive rather than theoretical: the previous version would happily
    // print 'missed "undefined"' for a deletion with no expected word.
    expect(describeError({ kind: "deletion" })).toBe("");
    expect(describeError({ kind: "insertion" })).toBe("");
    expect(describeError({ kind: "substitution", expected: "the" })).toBe("");
    expect(describeError({})).toBe("");
  });
});

describe("what a candidate is offered on their own result", () => {
  it("has no student-only destination in the shared report blocks", () => {
    // The result page offered "Take another", linking to /simulate -- a
    // student page. A candidate cannot take another (an invitation is one
    // sitting, and the server refuses a second attempt), and clicking it
    // ejected them from their own report to a login screen they have no
    // account for.
    //
    // Asserted over the report components rather than the page, because
    // these are what an employer-facing view reuses and the same link must
    // not reappear through them.
    const source = [Summary, Highlights, Plan, Evidence, Skills]
      .map((c) => c.toString()).join("\n");

    for (const studentOnly of ["/simulate", "/practise", "/drills", "/home"]) {
      expect(source).not.toContain(studentOnly);
    }
  });
});

describe("one answer to what to work on first", () => {
  // The defect: the page computed "work on this first" three ways (engine
  // lever, weighted-gain plan, priorities) and showed all three. The plan
  // now renders the server's diagnosis order and nothing it derived itself.
  const priorities = [
    { dimension: "content", score: 20, responses: 5, practice: "speaking",
      practice_code: "practice_content", practice_profile_id: "p1",
      practice_name: "Content", practice_minutes: 5, verdict: "needs_most",
      evidence: "Measured at 20 of 80 across 5 answers — your lowest measured area.",
      advice: "Decide the two things you will say." },
    { dimension: "pronunciation", score: 24, responses: 15, practice: "speaking",
      practice_code: "practice_pronunciation", practice_profile_id: "p2",
      practice_name: "Pronunciation", practice_minutes: 5, verdict: "needs_work",
      evidence: "Measured at 24 of 80 across 15 answers — lower than your stronger areas.",
      advice: "Read a paragraph aloud." },
  ];
  const base = {
    priorities,
    // A gain-ranked table that disagrees with the diagnosis, exactly as the
    // live defect did. It must have no effect on what is drawn.
    recommendations: [
      { dimension: "pronunciation", current: 24, target: 80, predicted_gain: 11.2, advice: "x" },
      { dimension: "content", current: 20, target: 80, predicted_gain: 4.2, advice: "y" },
    ],
  } as unknown as Parameters<typeof Plan>[0]["result"];

  it("draws the diagnosis order, marking only the primary as first", () => {
    render(<Plan result={{ ...base, primary_diagnosis: {
      status: "identified", headline: "Content", reason: "", evidence: "",
      dimension: "content", label: "Content", score: 20, responses: 5,
      scale_max: 80, confidence: "solid", candidates: [], excluded: [],
      practice_code: "practice_content", practice_profile_id: "p1",
      practice_name: "Content", practice_minutes: 5, advice: "",
      source_attempt_id: "a", source_profile_id: "", source_profile_name: "",
    } } as typeof base} />);
    const items = screen.getAllByRole("listitem").map((li) => li.textContent ?? "");
    expect(items[0]).toContain("Content");
    expect(items[0]).toContain("first");
    expect(items[1]).toContain("Pronunciation");
    expect(items[1]).not.toContain("first");
    // The weighted gain never appears: it is not the diagnosis.
    expect(document.body.textContent).not.toContain("11.2");
    expect(document.body.textContent).not.toMatch(/overall/);
  });

  it("crowns nobody when the diagnosis found a tie", () => {
    render(<Plan result={{ ...base, primary_diagnosis: {
      status: "tied", headline: "Nothing clearly stands out yet",
      reason: "Content and Pronunciation were measured at about the same level.",
      evidence: "", dimension: "", label: "", score: null, responses: 0,
      scale_max: 80, confidence: "", excluded: [],
      candidates: [{ dimension: "content", label: "Content", score: 20, responses: 5 },
                   { dimension: "pronunciation", label: "Pronunciation", score: 24, responses: 15 }],
      practice_code: "", practice_profile_id: "", practice_name: "",
      practice_minutes: 0, advice: "", source_attempt_id: "a",
      source_profile_id: "", source_profile_name: "",
    }, priorities: priorities.map((p) => ({ ...p, verdict: "needs_work" })) } as typeof base} />);
    expect(screen.getByText(/Nothing clearly stands out yet/)).toBeTruthy();
    expect(screen.queryByText("first")).toBeNull();
    expect(screen.queryByText(/in order/)).toBeNull();
  });
});

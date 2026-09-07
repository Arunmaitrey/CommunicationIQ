import type { Role } from "@/lib/api";

export interface TourStep {
  /** CSS selector for the element this step highlights. Reuses selectors
   *  already present in the DOM (#app-rail, data-label on nav links) rather
   *  than adding new data-tour attributes everywhere. */
  selector: string;
  title: string;
  body: string;
  /** Route to navigate to before showing this step, if the user isn't
   *  already there. Only one step in the whole tour uses this. */
  route?: string;
  /** Preferred side for the tooltip relative to the highlighted element. */
  placement?: "right" | "bottom" | "left" | "top";
}

const HELP_STEP: TourStep = {
  selector: '[data-tour="help-button"]',
  title: "Come back anytime",
  body: "This icon reopens this tour, or the getting-started guide, whenever you need it.",
  placement: "left",
};

const RAIL_STEP: TourStep = {
  selector: "#app-rail",
  title: "Your menu",
  body: "Everything you can do lives here, grouped by what it's for.",
  placement: "right",
};

const STUDENT_STEPS: TourStep[] = [
  RAIL_STEP,
  {
    selector: '[data-tour="home-workflow"]',
    title: "What to do next",
    body: "This card always shows your next step and tracks your progress — check back here whenever you're not sure what's next.",
    route: "/home",
    placement: "top",
  },
  {
    selector: '[data-label="Take a test"]',
    title: "Take a test",
    body: "Timed, official attempts — scored properly, one at a time. Start with the short baseline test.",
    placement: "right",
  },
  {
    selector: '[data-label="Practise"]',
    title: "Practise",
    body: "Short, low-stakes sessions on your weakest skill. No pressure, no scoring against you.",
    placement: "right",
  },
  {
    selector: '[data-label="My progress"]',
    title: "My progress",
    body: "See how your scores are moving over time, and where the biggest gap still is.",
    placement: "right",
  },
  HELP_STEP,
];

const TRAINER_STEPS: TourStep[] = [
  RAIL_STEP,
  {
    selector: '[data-label="Overview"]',
    title: "Coaching overview",
    body: "Your cohorts, who's drifting, and who you've already picked up — at a glance.",
    placement: "right",
  },
  {
    selector: '[data-label="Cohorts"]',
    title: "Cohorts",
    body: "Every cohort assigned to you, with readiness bands for each student.",
    placement: "right",
  },
  {
    selector: '[data-label="Momentum"]',
    title: "Momentum",
    body: "Practice-consistency leaderboard — who's actually putting in reps.",
    placement: "right",
  },
  {
    selector: '[data-label="At-risk flags"]',
    title: "At-risk flags",
    body: "Students who need attention, surfaced automatically so nobody falls through.",
    placement: "right",
  },
  HELP_STEP,
];

const TENANT_ADMIN_STEPS: TourStep[] = [
  RAIL_STEP,
  {
    selector: '[data-label="People"]',
    title: "People",
    body: "Create accounts and assign roles for your institution.",
    placement: "right",
  },
  {
    selector: '[data-label="Import"]',
    title: "Import people",
    body: "Bulk-add students or staff from a spreadsheet instead of one at a time.",
    placement: "right",
  },
  {
    selector: '[data-label="Cohorts"]',
    title: "Cohorts",
    body: "Group students by branch, year, or section — and see readiness per cohort.",
    placement: "right",
  },
  {
    selector: '[data-label="Invitations"]',
    title: "Invitations",
    body: "One-time links for candidates who need a single assessment without a full account.",
    placement: "right",
  },
  HELP_STEP,
];

/** Per-role tour content. Returns an empty array for roles the tour doesn't
 *  cover yet (platform staff, candidates) — callers should treat that as
 *  "no tour available" rather than an error. */
export function tourStepsFor(role: Role | undefined): TourStep[] {
  switch (role) {
    case "student": return STUDENT_STEPS;
    case "trainer": return TRAINER_STEPS;
    case "tenant_admin": return TENANT_ADMIN_STEPS;
    default: return [];
  }
}

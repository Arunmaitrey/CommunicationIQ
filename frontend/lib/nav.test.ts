/**
 *  Where each role is allowed to go, and where an unrecognised one ends up.
 *
 *  Both of these were wrong at once, and for the same reason: `candidate` was
 *  added as a backend role in Phase 9 and never added to the `Role` union
 *  here. With no `candidate` member, no `switch` had to handle one and no
 *  `roles={[...]}` list looked incomplete, so the compiler never asked.
 *
 *  What that cost, found by sitting the invitation journey in a browser:
 *
 *  - The environment check, the runner and the report all guarded on
 *    `["student"]`. A candidate is not a student, so the three pages the
 *    invitation exists to deliver were the three they could not reach. They
 *    consented, an attempt was created on the server, and the browser took
 *    them somewhere else.
 *  - Somewhere else was `/platform`. `landingFor` ended `default: "/platform"`,
 *    so every role the frontend did not recognise was routed to the operator
 *    console -- fail-open, and it fired in practice.
 */
import { describe, expect, it } from "vitest";

import { SITTING_ROLES, landingFor, navFor } from "./nav";
import { PLATFORM_ROLES, ROLE_LABEL } from "./roles";
import type { Role } from "./api";

describe("where a role lands", () => {
  it("never sends an unrecognised role to the operator console", () => {
    // The property that matters, stated so it cannot regress: /platform is
    // reachable only by a role named explicitly as an operator.
    const unknown = "some_role_added_next_year" as Role;
    expect(landingFor(unknown)).not.toBe("/platform");
    expect(landingFor(undefined)).not.toBe("/platform");
  });

  it("sends a candidate somewhere harmless rather than to /platform", () => {
    expect(landingFor("candidate")).toBe("/login");
  });

  it("still sends each operator role to the console", () => {
    for (const role of PLATFORM_ROLES) {
      expect(landingFor(role)).toBe("/platform");
    }
  });

  it("sends the ordinary roles where they belong", () => {
    expect(landingFor("student")).toBe("/home");
    expect(landingFor("trainer")).toBe("/coaching");
    expect(landingFor("tenant_admin")).toBe("/tenant");
  });
});

describe("who may sit an assessment", () => {
  it("includes the invited candidate as well as the student", () => {
    // The check page, the runner and the report use this list. Guarding them
    // on students alone meant an invited candidate could consent and then not
    // sit the thing they had consented to.
    expect(SITTING_ROLES).toContain("student");
    expect(SITTING_ROLES).toContain("candidate");
  });

  it("does not quietly admit anybody else", () => {
    expect(SITTING_ROLES).toHaveLength(2);
    for (const role of PLATFORM_ROLES) {
      expect(SITTING_ROLES).not.toContain(role);
    }
    expect(SITTING_ROLES).not.toContain("trainer");
    expect(SITTING_ROLES).not.toContain("tenant_admin");
  });

  it("gives a candidate no navigation, because they have nowhere to browse", () => {
    // A candidate came for one assessment. An empty rail is correct here --
    // what would have been wrong is a rail with somebody else's links on it.
    expect(navFor("candidate")).toEqual([]);
  });
});

describe("the role list itself", () => {
  it("labels every role, so none can be added without being noticed", () => {
    // This is the guard that would have caught the whole thing: `ROLE_LABEL`
    // is a `Record<Role, string>`, so a new member of the union fails to
    // compile until somebody has looked at it.
    expect(ROLE_LABEL.candidate).toBe("Candidate");
    for (const label of Object.values(ROLE_LABEL)) {
      expect(label.trim()).not.toBe("");
    }
  });
});

describe("dead ends a candidate must never be sent to", () => {
  it("keeps every student-only destination out of the sitting roles' reach", () => {
    // A candidate has no account to log in with, so any navigation to a
    // student page ends at a login screen they cannot pass. This has now
    // happened three times: the route guards, "Take another" on the report,
    // and "Back to simulations" on a stopped attempt.
    const studentOnly = ["/simulate", "/practise", "/home",
                         "/my-progress", "/skills"];
    for (const path of studentOnly) {
      expect(landingFor("candidate")).not.toBe(path);
    }
  });

  it("gives a candidate a landing that is not a student surface", () => {
    const landing = landingFor("candidate");
    expect(["/login"]).toContain(landing);
  });
});

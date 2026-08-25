// @vitest-environment jsdom
/**
 *  `attemptApi.resume`, and why it does not go through the normal request
 *  helper.
 *
 *  The invite page asks "am I already somebody?" on every load, and the
 *  overwhelming majority of the time the answer is no -- a first-time
 *  candidate clicking the link in their email has no session at all.
 *
 *  Routed through `request`, that question is a 401, and `request` treats any
 *  401 as an expired session: it clears storage and sends the browser to
 *  /login. The first version of the resume fix did exactly that, and bounced
 *  every new candidate to a login screen they have no account for -- a worse
 *  bug than the stranded-on-refresh one it was written to fix, and it reached
 *  the browser because the journey was not re-run from a clean state.
 *
 *  So: no token means no request and a null answer, and any failure is also
 *  null. Nothing about asking may cost the visitor the page.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { attemptApi, setToken } from "./api";

const realFetch = globalThis.fetch;

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  globalThis.fetch = realFetch;
  localStorage.clear();
  vi.restoreAllMocks();
});

describe("asking where a candidate left off", () => {
  it("does not call the server at all without a session", async () => {
    const fetcher = vi.fn();
    globalThis.fetch = fetcher as never;

    expect(await attemptApi.resume()).toBeNull();
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("returns null on a 401 rather than ending the session", async () => {
    // The exact failure that bounced first-time candidates to /login: a
    // stale token in storage, a 401, and the global handler clearing
    // everything and navigating away from the invitation.
    setToken("stale-token");
    globalThis.fetch = vi.fn(async () =>
      new Response("null", { status: 401 })) as never;

    expect(await attemptApi.resume()).toBeNull();
    expect(localStorage.getItem("commiq.token")).toBe("stale-token");
  });

  it("returns null when the network is down, without throwing", async () => {
    setToken("a-token");
    globalThis.fetch = vi.fn(async () => { throw new TypeError("Failed to fetch"); }) as never;

    await expect(attemptApi.resume()).resolves.toBeNull();
  });

  it("returns the assessment when there is one", async () => {
    setToken("a-token");
    const payload = {
      profile_id: "p1", profile_name: "Support Associate",
      attempt_id: null, attempt_status: "", consent_given: false,
    };
    globalThis.fetch = vi.fn(async () =>
      new Response(JSON.stringify(payload), { status: 200 })) as never;

    expect(await attemptApi.resume()).toEqual(payload);
  });

  it("sends the session token when it has one", async () => {
    setToken("a-token");
    const fetcher = vi.fn(async () =>
      new Response(JSON.stringify({ profile_id: "" }), { status: 200 }));
    globalThis.fetch = fetcher as never;

    await attemptApi.resume();

    const [, init] = fetcher.mock.calls[0] as unknown as [string, RequestInit];
    expect((init.headers as Record<string, string>).Authorization)
      .toBe("Bearer a-token");
  });
});

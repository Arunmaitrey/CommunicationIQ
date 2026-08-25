"use client";
import { useCallback, useEffect, useRef, useState } from "react";

/** Notices when the candidate stops being at the screen.
 *
 *  Deliberately not a disqualifier. A real placement test would fail you for
 *  this; a practice tool that does the same teaches nothing and punishes the
 *  student whose hostel wifi dropped or whose mother walked in. What it does
 *  instead is pause, say what it saw, and ask whether now is still a good
 *  time — the interruption is recorded either way, so a trainer can see that
 *  an attempt was disturbed rather than wondering why the score dipped.
 *
 *  Three signals, because one is not enough on a phone:
 *
 *  * `visibilitychange` — the tab was backgrounded or the phone locked. The
 *    reliable one, and the only one mobile browsers fire consistently.
 *  * `blur` — focus went to another window on a desktop, where the tab can
 *    stay visible beside whatever took over.
 *  * `pagehide` — the browser is discarding the page. Last chance to record.
 *
 *  A grace period matters. Tapping a notification and coming straight back is
 *  not leaving, and interrupting a test for a half-second flicker would be
 *  worse than the thing it is guarding against.
 */

export type PresenceEvent = {
  /** What triggered it, for the record kept on the attempt. */
  kind: "hidden" | "blurred";
  at: number;
  /** How long they were gone, in milliseconds. Filled in on return. */
  awayMs?: number;
};

const GRACE_MS = 1_200;

export function usePresence(active: boolean) {
  const [away, setAway] = useState(false);
  const [events, setEvents] = useState<PresenceEvent[]>([]);
  const leftAt = useRef<number | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clear = () => {
    if (timer.current) {
      clearTimeout(timer.current);
      timer.current = null;
    }
  };

  const leave = useCallback((kind: PresenceEvent["kind"]) => {
    if (leftAt.current !== null) return;   // already counting
    clear();
    timer.current = setTimeout(() => {
      leftAt.current = Date.now();
      setEvents((prior) => [...prior, { kind, at: Date.now() }]);
      setAway(true);
    }, GRACE_MS);
  }, []);

  const returned = useCallback(() => {
    clear();
    if (leftAt.current === null) return;
    const awayMs = Date.now() - leftAt.current;
    leftAt.current = null;
    setEvents((prior) => {
      if (!prior.length) return prior;
      const last = prior[prior.length - 1];
      return [...prior.slice(0, -1), { ...last, awayMs }];
    });
  }, []);

  useEffect(() => {
    if (!active) return;

    const onVisibility = () =>
      (document.hidden ? leave("hidden") : returned());
    const onBlur = () => leave("blurred");
    const onFocus = () => returned();
    const onPageHide = () => leave("hidden");

    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("blur", onBlur);
    window.addEventListener("focus", onFocus);
    window.addEventListener("pagehide", onPageHide);
    return () => {
      clear();
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("blur", onBlur);
      window.removeEventListener("focus", onFocus);
      window.removeEventListener("pagehide", onPageHide);
    };
  }, [active, leave, returned]);

  /** Dismiss the prompt and carry on. The event stays in the record. */
  const resume = useCallback(() => setAway(false), []);

  return { away, events, resume };
}

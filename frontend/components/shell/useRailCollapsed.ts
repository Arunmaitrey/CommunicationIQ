"use client";
import { useCallback, useEffect, useState } from "react";
import { IDENTITY_EVENT } from "@/components/ThemeProvider";

/** Whether the navigation rail is collapsed, remembered per account.
 *
 *  Per account for the same reason the theme is: a placement lab is a room of
 *  shared machines, and a trainer who collapsed the rail must not hand a
 *  collapsed rail to the student who signs in next. Same storage convention,
 *  same identity event, so the two stay consistent.
 *
 *  Defaults to expanded. Somebody seeing the product for the first time should
 *  see what it can do, not a column of unlabelled icons.
 */
const KEY = "commiq.rail";

const keyFor = (email: string | null) =>
  email ? `${KEY}.${email.toLowerCase()}` : KEY;

function currentEmail(): string | null {
  try {
    const raw = localStorage.getItem("commiq.identity");
    return raw ? (JSON.parse(raw) as { email?: string }).email ?? null : null;
  } catch {
    return null;
  }
}

export function useRailCollapsed(): [boolean, () => void] {
  // Always starts expanded so the server and the first client render agree;
  // the stored preference is applied in an effect. Reading localStorage during
  // render would be a hydration mismatch.
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    const read = () => {
      try {
        setCollapsed(localStorage.getItem(keyFor(currentEmail())) === "1");
      } catch {
        setCollapsed(false);
      }
    };
    read();
    // "storage" covers other tabs; IDENTITY_EVENT covers a sign-in in this
    // one, which does not raise a storage event to itself.
    window.addEventListener("storage", read);
    window.addEventListener(IDENTITY_EVENT, read);
    return () => {
      window.removeEventListener("storage", read);
      window.removeEventListener(IDENTITY_EVENT, read);
    };
  }, []);

  const toggle = useCallback(() => {
    setCollapsed((was) => {
      const next = !was;
      try {
        localStorage.setItem(keyFor(currentEmail()), next ? "1" : "0");
      } catch {
        /* private browsing: the toggle still works, it just will not persist */
      }
      return next;
    });
  }, []);

  // Ctrl/Cmd + B, the shortcut every editor and most consoles already use.
  // Ignored while typing, or the first person to write "b" in a search box
  // loses their navigation.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() !== "b" || !(e.ctrlKey || e.metaKey)) return;
      const el = document.activeElement as HTMLElement | null;
      const tag = el?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT"
          || el?.isContentEditable) {
        return;
      }
      e.preventDefault();
      toggle();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggle]);

  return [collapsed, toggle];
}

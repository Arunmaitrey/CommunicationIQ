"use client";
import { createContext, useContext, useEffect, useState, ReactNode } from "react";

export type ThemeId =
  | "quadrant" | "quadrant-dark" | "minimal" | "midnight"
  | "enterprise" | "material" | "bento" | "gold" | "blue" | "royal-blue"
  | "glassmorphism" | "liquid-glass" | "ai-futurism" | "dark-console"
  | "luxury" | "cyberpunk" | "campus";

// Grouped by intent: Professional = safe in front of a placement officer ·
// Dark = what a student practising at 11pm in a hostel room will pick ·
// Expressive = personality. Campus leads as the product default.
export type ThemeGroup = "Professional" | "Dark" | "Expressive";

export const THEMES: { id: ThemeId; label: string; group: ThemeGroup }[] = [
  { id: "campus", label: "Campus", group: "Professional" },
  { id: "blue", label: "Ocean Blue", group: "Professional" },
  { id: "royal-blue", label: "Royal Blue", group: "Professional" },
  { id: "quadrant", label: "Quadrant Light", group: "Professional" },
  { id: "enterprise", label: "Enterprise SaaS", group: "Professional" },
  { id: "minimal", label: "Minimal", group: "Professional" },
  { id: "gold", label: "Gold", group: "Professional" },
  { id: "quadrant-dark", label: "Quadrant Dark", group: "Dark" },
  { id: "midnight", label: "Midnight Console", group: "Dark" },
  { id: "dark-console", label: "Dark Console", group: "Dark" },
  { id: "ai-futurism", label: "Futurism", group: "Dark" },
  { id: "luxury", label: "Luxury Enterprise", group: "Dark" },
  { id: "cyberpunk", label: "Cyberpunk", group: "Dark" },
  { id: "material", label: "Material 3", group: "Expressive" },
  { id: "bento", label: "Bento UI", group: "Expressive" },
  { id: "glassmorphism", label: "Glassmorphism", group: "Expressive" },
  { id: "liquid-glass", label: "Liquid Glass", group: "Expressive" },
];

export const THEME_GROUPS: ThemeGroup[] = ["Professional", "Dark", "Expressive"];

const DEFAULT: ThemeId = "campus";

/** Where one person's theme is kept.
 *
 *  Per account, not per browser. A placement lab is a room of shared machines:
 *  one student picking Cyberpunk must not hand it to the next person who signs
 *  in, and a trainer demoing to a principal must not inherit either.
 *
 *  Still per browser, and honestly so — the same student on the lab PC and on
 *  their phone starts at the default on each. Carrying it across devices means
 *  storing it on the account, which the API already supports
 *  (PUT /auth/preferences) and a later slice will wire up.
 */
const KEY = "commiq.theme";
/** Raised by RoleProvider when the signed-in account changes. */
export const IDENTITY_EVENT = "commiq:identity";
const keyFor = (email: string | null) => (email ? `${KEY}.${email.toLowerCase()}` : KEY);

/** Who is signed in, read from where RoleProvider keeps it. Read rather than
 *  imported to avoid a provider ordering dependency — the theme has to apply
 *  before anything else renders. */
function currentEmail(): string | null {
  try {
    const raw = localStorage.getItem("commiq.identity");
    return raw ? (JSON.parse(raw) as { email?: string }).email ?? null : null;
  } catch {
    return null;
  }
}

const Ctx = createContext<{ theme: ThemeId; setTheme: (t: ThemeId) => void }>({
  theme: DEFAULT,
  setTheme: () => {},
});

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemeId>(DEFAULT);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const read = () => {
      const saved = localStorage.getItem(keyFor(currentEmail())) as ThemeId | null;
      setThemeState(saved && THEMES.some((t) => t.id === saved) ? saved : DEFAULT);
    };
    read();
    // "storage" covers other tabs; IDENTITY_EVENT covers this one, because a
    // tab does not receive its own storage events.
    window.addEventListener("storage", read);
    window.addEventListener(IDENTITY_EVENT, read);
    return () => {
      window.removeEventListener("storage", read);
      window.removeEventListener(IDENTITY_EVENT, read);
    };
  }, []);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  const setTheme = (t: ThemeId) => {
    setThemeState(t);
    localStorage.setItem(keyFor(currentEmail()), t);
  };

  return <Ctx.Provider value={{ theme, setTheme }}>{children}</Ctx.Provider>;
}

export const useTheme = () => useContext(Ctx);

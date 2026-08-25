"use client";
import { useEffect, useRef, useState } from "react";
import { Check, Palette } from "lucide-react";
import { THEMES, THEME_GROUPS, useTheme, type ThemeId } from "@/components/ThemeProvider";

/** All sixteen themes, grouped by intent.
 *
 *  A swatch per theme rather than a text list: the choice is visual, and the
 *  three dots show the actual token values the theme will apply, read live
 *  from a hidden probe element rather than duplicated here — a second copy of
 *  the palette is a second thing to keep in sync.
 */
export function ThemePicker() {
  const { theme, setTheme } = useTheme();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  const current = THEMES.find((t) => t.id === theme);

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="btn btn-ghost btn-sm ds-focus"
        title={`Theme: ${current?.label ?? theme}`}
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <Palette size={14} />
        <span className="hidden sm:inline">{current?.label ?? "Theme"}</span>
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 mt-2 w-72 ds-card p-2 z-50 animate-fade-in max-h-[70vh] overflow-y-auto thin-scroll"
        >
          {THEME_GROUPS.map((group) => (
            <div key={group} className="mb-2 last:mb-0">
              <div className="px-2 py-1 text-[10px] font-bold uppercase tracking-wider text-muted">
                {group}
              </div>
              {THEMES.filter((t) => t.group === group).map((t) => (
                <button
                  key={t.id}
                  role="menuitemradio"
                  aria-checked={t.id === theme}
                  onClick={() => { setTheme(t.id as ThemeId); setOpen(false); }}
                  className="w-full flex items-center gap-2.5 px-2 py-1.5 rounded text-left text-xs hover:bg-surface2 ds-focus"
                >
                  <Swatch id={t.id} />
                  <span className="flex-1 font-medium">{t.label}</span>
                  {t.id === theme && <Check size={13} className="text-primary" />}
                </button>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/** Three dots rendered inside a `data-theme` scope, so each swatch shows that
 *  theme's real tokens without any of them being written twice. */
function Swatch({ id }: { id: string }) {
  return (
    <span data-theme={id} className="inline-flex gap-1 shrink-0 rounded p-1"
          style={{ background: "var(--bg)", border: "1px solid var(--border)" }}>
      <i className="block w-2.5 h-2.5 rounded-full" style={{ background: "var(--primary)" }} />
      <i className="block w-2.5 h-2.5 rounded-full" style={{ background: "var(--accent)" }} />
      <i className="block w-2.5 h-2.5 rounded-full" style={{ background: "var(--surface-2)" }} />
    </span>
  );
}

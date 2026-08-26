"use client";
import { useState } from "react";
import { Globe } from "lucide-react";
import type { Locale } from "@/lib/i18n";

const LANGUAGES: { code: Locale; label: string; native: string }[] = [
  { code: "en", label: "English", native: "English" },
  { code: "te", label: "Telugu", native: "తెలుగు" },
  { code: "hi", label: "Hindi", native: "हिन्दी" },
  { code: "ta", label: "Tamil", native: "தமிழ்" },
];

const STORAGE_KEY = "commiq-locale";

/** Get stored locale. */
export function getStoredLocale(): Locale {
  if (typeof window === "undefined") return "en";
  return (localStorage.getItem(STORAGE_KEY) as Locale) || "en";
}

/** Store locale. */
export function setStoredLocale(locale: Locale) {
  localStorage.setItem(STORAGE_KEY, locale);
}

/**
 * ACC-01: Language switcher.
 *
 * Allows students to switch feedback language between English, Telugu,
 * Hindi, and Tamil. Stored in localStorage and used by i18n.ts.
 */
export function LanguageSwitcher() {
  const [locale, setLocale] = useState<Locale>(getStoredLocale);

  function handleChange(code: Locale) {
    setLocale(code);
    setStoredLocale(code);
    // Force a re-render of i18n consumers
    window.dispatchEvent(new CustomEvent("locale-changed", { detail: code }));
  }

  return (
    <div className="flex items-center gap-2">
      <Globe size={14} className="text-muted" />
      <div className="flex gap-1">
        {LANGUAGES.map((lang) => (
          <button
            key={lang.code}
            onClick={() => handleChange(lang.code)}
            className={`px-2 py-0.5 text-[11px] rounded transition-colors ${
              locale === lang.code
                ? "bg-[var(--primary)] text-white font-semibold"
                : "text-muted hover:bg-[var(--border)]"
            }`}
            title={lang.label}
          >
            {lang.native}
          </button>
        ))}
      </div>
    </div>
  );
}

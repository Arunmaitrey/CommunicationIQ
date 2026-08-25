import type { Config } from "tailwindcss";

// Every colour maps to a CSS variable defined in app/globals.css (the single
// source of design truth). Themes swap the variables via data-theme on <html>,
// which is why a component written against these names works in all sixteen
// without knowing any of them exist.
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        surface: "var(--surface)",
        surface2: "var(--surface-2)",
        text: "var(--text)",
        muted: "var(--muted)",
        border: "var(--border)",
        primary: "var(--primary)",
        secondary: "var(--secondary)",
        accent: "var(--accent)",
        success: "var(--success)",
        warning: "var(--warning)",
        error: "var(--error)",
        // Readiness is a traffic light and stays one in every theme.
        ragGreen: "var(--rag-green)",
        ragAmber: "var(--rag-amber)",
        ragRed: "var(--rag-red)",
      },
      borderRadius: { ds: "var(--radius)" },
      boxShadow: { ds: "var(--shadow)" },
      fontFamily: { sans: "var(--font)" },
      transitionTimingFunction: { ds: "cubic-bezier(.4,0,.2,1)" },
    },
  },
  plugins: [],
};
export default config;

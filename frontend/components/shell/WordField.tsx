"use client";

/** Background texture made of words instead of circles.
 *
 *  Every other theme decorates with soft radial gradients. The Campus theme
 *  decorates with the vocabulary of the thing the product is about —
 *  placement, fluency, readiness — set very faint in the display and mono
 *  faces. Close up you can pick out a word; at working distance it reads as
 *  rhythm, which is the point. Anything more legible would compete with the
 *  interface sitting on top of it.
 *
 *  The layout is a fixed table rather than randomised. Random positions look
 *  different on every render and, worse, differ between the server pass and
 *  the client pass, which React reports as a hydration mismatch. Fixed
 *  coordinates also mean a designer can move one word without fighting a
 *  generator.
 *
 *  Percentages, not pixels, so the field spreads on a monitor and stays
 *  sparse on a phone rather than piling up in one corner. A few entries sit
 *  past 75% and are dropped on small screens — see `wide`.
 */

type Word = {
  text: string;
  /** left / top as a percentage of the viewport. */
  x: number;
  y: number;
  /** font-size in rem. */
  size: number;
  rotate?: number;
  /** Uppercase monospace, like the labels on the marketing site. */
  mono?: boolean;
  /** Uses the warm accent rather than the teal. */
  warm?: boolean;
  /** Only shown on wide viewports; keeps phones uncluttered. */
  wide?: boolean;
};

const WORDS: Word[] = [
  { text: "Placement", x: 4, y: 8, size: 5.5 },
  { text: "READINESS", x: 58, y: 4, size: 1.5, mono: true },
  { text: "Fluency", x: 66, y: 13, size: 4.2, warm: true },
  { text: "Interview", x: 10, y: 24, size: 3.4, rotate: -4 },
  { text: "COHORT", x: 42, y: 21, size: 1.25, mono: true, wide: true },
  { text: "Pronunciation", x: 52, y: 31, size: 3.8 },
  { text: "Diagnostic", x: 3, y: 41, size: 4.6, warm: true },
  { text: "BENCHMARK", x: 74, y: 44, size: 1.4, mono: true, wide: true },
  { text: "Confidence", x: 30, y: 52, size: 5 },
  { text: "Campus", x: 68, y: 58, size: 4.4, rotate: 3 },
  { text: "ARTICULATION", x: 6, y: 64, size: 1.3, mono: true },
  { text: "Employability", x: 38, y: 71, size: 3.6, warm: true },
  { text: "Assessment", x: 2, y: 80, size: 4.8, rotate: -2 },
  { text: "GRAMMAR", x: 62, y: 78, size: 1.45, mono: true },
  { text: "Communication", x: 24, y: 89, size: 4, wide: true },
  { text: "OUTCOMES", x: 76, y: 92, size: 1.35, mono: true, wide: true },
];

export function WordField() {
  return (
    <div className="word-field" aria-hidden="true">
      {WORDS.map((w) => (
        <span
          key={w.text}
          className={[
            w.mono ? "is-mono" : "",
            w.warm ? "is-warm" : "",
            w.wide ? "hidden xl:inline" : "",
          ].filter(Boolean).join(" ")}
          style={{
            left: `${w.x}%`,
            top: `${w.y}%`,
            fontSize: `${w.size}rem`,
            transform: w.rotate ? `rotate(${w.rotate}deg)` : undefined,
          }}
        >
          {w.text}
        </span>
      ))}
    </div>
  );
}

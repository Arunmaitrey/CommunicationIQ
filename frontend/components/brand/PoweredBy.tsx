"use client";

/** The Graymatter Technologies mark and attribution line.
 *
 *  The mark is drawn as inline SVG rather than linked from an external site.
 *  Two reasons, both practical: an <img> pointing at another origin is a
 *  runtime dependency that breaks the footer whenever that site is slow,
 *  moved or offline, and it leaks a request on every page view. Inline it
 *  costs nothing and renders identically at any size.
 *
 *  A graphite monogram on near-black — grey matter, literally.
 */
const GREY = "#9CA3AF";
const INK = "#050505";

export function GraymatterMark({ size = 16 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      role="img"
      aria-label="Graymatter Technologies"
      className="shrink-0 rounded-[3px]"
    >
      <rect width="32" height="32" fill={INK} />
      {/* An open G: a circle broken at the right, with the crossbar reaching
          into the gap. Reads at 14px, which is where it usually renders. */}
      <path
        d="M 23.5 10.5 A 9 9 0 1 0 25 16 L 17.5 16"
        fill="none"
        stroke={GREY}
        strokeWidth="2.6"
        strokeLinecap="round"
      />
    </svg>
  );
}

/** Attribution, sized to sit quietly at the bottom of a shell or a card. */
export function PoweredBy({ className = "" }: { className?: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 text-[10px] ${className}`}
    >
      <GraymatterMark size={14} />
      <span className="font-bold">Powered by Graymatter Technologies © 2026</span>
    </span>
  );
}

/** The same attribution, pinned to the corner of the viewport.
 *
 *  Rendered once per shell rather than per page, so it survives navigation
 *  without re-mounting and cannot end up on screen twice.
 */
export function PoweredByFloat() {
  return (
    <div className="powered-float">
      <PoweredBy />
    </div>
  );
}

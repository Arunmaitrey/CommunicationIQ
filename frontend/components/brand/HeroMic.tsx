"use client";

/** The login hero's centrepiece: a microphone under live sound waves.
 *
 *  The product is a speaking assessment, so the left panel now shows the
 *  thing it measures — a mic on its stand, with rings of sound pulsing out
 *  of it and a soft floor of reflected light. Built entirely from CSS 3D
 *  transforms and one inline SVG: no image, no model file, no external
 *  request, so it survives the strict CSP and renders identically offline.
 *
 *  Every colour is a theme token (--primary / --accent / --rail-*), so the
 *  same scene is teal on Campus, blue on Quadrant, gold on the Gold theme —
 *  it is tinted by whatever palette is live, never hard-coded. Motion stops
 *  under prefers-reduced-motion; the scene stays, it just holds still.
 */
export function HeroMic() {
  return (
    <div className="hero-mic" aria-hidden="true">
      {/* Sound rings, emitted from behind the capsule. */}
      <div className="hero-mic__waves">
        <span style={{ ["--i" as string]: 0 }} />
        <span style={{ ["--i" as string]: 1 }} />
        <span style={{ ["--i" as string]: 2 }} />
        <span style={{ ["--i" as string]: 3 }} />
      </div>

      {/* The instrument, tilted into perspective and gently floating. */}
      <div className="hero-mic__rig">
        <div className="hero-mic__glow" />
        <div className="hero-mic__body">
          <div className="hero-mic__grille">
            {/* Live level bars behind the grille — the mic "hearing". */}
            <div className="hero-mic__bars">
              <i style={{ ["--d" as string]: "0s" }} />
              <i style={{ ["--d" as string]: ".18s" }} />
              <i style={{ ["--d" as string]: ".36s" }} />
              <i style={{ ["--d" as string]: ".54s" }} />
              <i style={{ ["--d" as string]: ".72s" }} />
            </div>
          </div>
          <div className="hero-mic__ring" />
          <div className="hero-mic__ring hero-mic__ring--2" />
        </div>
        <div className="hero-mic__neck" />
        <div className="hero-mic__base" />
        <div className="hero-mic__shadow" />
      </div>

      {/* A few motes of light for depth. */}
      <div className="hero-mic__motes">
        <span style={{ ["--mx" as string]: "18%", ["--my" as string]: "30%", ["--md" as string]: "0s" }} />
        <span style={{ ["--mx" as string]: "78%", ["--my" as string]: "22%", ["--md" as string]: "1.1s" }} />
        <span style={{ ["--mx" as string]: "68%", ["--my" as string]: "70%", ["--md" as string]: "2.2s" }} />
        <span style={{ ["--mx" as string]: "28%", ["--my" as string]: "76%", ["--md" as string]: "1.6s" }} />
        <span style={{ ["--mx" as string]: "50%", ["--my" as string]: "14%", ["--md" as string]: ".6s" }} />
      </div>
    </div>
  );
}

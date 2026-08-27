"use client";

/** The AI narrator for listening practice.
 *
 *  While a passage plays, the student had a static ear icon to look at. This
 *  is a face instead: a headphoned AI presenter whose mouth moves as an
 *  equalizer while it speaks and rests to a flat line when it stops, ringed
 *  by sound waves that only pulse during playback. It gives the voice
 *  somewhere to come from and a clear "now / not now" signal.
 *
 *  Honest about what it is. The listening screen already says the passage is
 *  read by a synthetic voice; a synthetic face matched to it is the truthful
 *  picture, not a stock photo of a person who never spoke. Built from CSS and
 *  one inline SVG — no image, no external request, so it clears the CSP — and
 *  every colour is a theme token, so it is tinted by whichever palette is
 *  live. Motion stops under prefers-reduced-motion.
 *
 *  `speaking` drives the whole thing: true animates the mouth and rings,
 *  false settles it to a calm, breathing idle.
 */
export function AiNarrator({ speaking }: { speaking: boolean }) {
  return (
    <div className={`ai-narrator${speaking ? " is-speaking" : ""}`} aria-hidden="true">
      {/* Sound rings — visible only while speaking. */}
      <div className="ai-narrator__waves">
        <span style={{ ["--i" as string]: 0 }} />
        <span style={{ ["--i" as string]: 1 }} />
        <span style={{ ["--i" as string]: 2 }} />
      </div>

      <div className="ai-narrator__head">
        {/* Headphone band and ear cups — this is a listening context. */}
        <span className="ai-narrator__band" />
        <span className="ai-narrator__cup ai-narrator__cup--l" />
        <span className="ai-narrator__cup ai-narrator__cup--r" />

        {/* Face. */}
        <div className="ai-narrator__face">
          <span className="ai-narrator__eye ai-narrator__eye--l" />
          <span className="ai-narrator__eye ai-narrator__eye--r" />
          {/* Mouth: an equalizer that moves while speaking, flat at rest. */}
          <div className="ai-narrator__mouth">
            <i style={{ ["--d" as string]: "0s" }} />
            <i style={{ ["--d" as string]: ".15s" }} />
            <i style={{ ["--d" as string]: ".3s" }} />
            <i style={{ ["--d" as string]: ".45s" }} />
            <i style={{ ["--d" as string]: ".6s" }} />
          </div>
        </div>
      </div>

      {/* A small "AI" tag so nobody mistakes it for a recorded person. */}
      <span className="ai-narrator__tag">Synthetic voice</span>
    </div>
  );
}

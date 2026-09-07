"use client";
import { useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight, X } from "lucide-react";
import { useOnboarding } from "./OnboardingProvider";

const SPOTLIGHT_PAD = 8;
const TOOLTIP_GAP = 14;
const TOOLTIP_WIDTH = 320;

interface Rect { top: number; left: number; width: number; height: number }

/** A step's target counts as "on screen" only if it's actually laid out —
 *  the nav rail is `hidden md:flex`, so on a phone its children exist in the
 *  DOM but have a zero-size box. Treating that the same as "not found" lets
 *  the tour skip rail-based steps cleanly on small screens instead of
 *  spotlighting an invisible 0x0 box. */
function visibleRect(selector: string): Rect | null {
  const el = document.querySelector(selector);
  if (!el) return null;
  const r = el.getBoundingClientRect();
  if (r.width === 0 || r.height === 0) return null;
  return { top: r.top, left: r.left, width: r.width, height: r.height };
}

export function ProductTour() {
  const { tourActive, steps, stepIndex, nextStep, prevStep, skipTour } = useOnboarding();
  const router = useRouter();
  const pathname = usePathname();

  const [rect, setRect] = useState<Rect | null>(null);
  const [searching, setSearching] = useState(true);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const attemptsRef = useRef(0);

  const step = tourActive ? steps[stepIndex] : undefined;

  // Navigate to the step's page first, if it names one and we're elsewhere.
  useEffect(() => {
    if (!step?.route) return;
    if (pathname !== step.route) {
      router.push(step.route);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, pathname]);

  // Locate the target element, waiting briefly for late-mounting content
  // (e.g. the page we just navigated to, or data still loading) before
  // giving up and moving the tour on rather than showing a broken step.
  useEffect(() => {
    if (!step) return;
    setSearching(true);
    setRect(null);
    attemptsRef.current = 0;

    const tick = () => {
      const found = visibleRect(step.selector);
      if (found) {
        setRect(found);
        setSearching(false);
        if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
        return;
      }
      attemptsRef.current += 1;
      if (attemptsRef.current >= 10) {
        if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
        setSearching(false);
        nextStep(); // element genuinely unavailable here — skip cleanly
      }
    };

    tick();
    pollRef.current = setInterval(tick, 150);
    return () => {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, pathname]);

  // Track the target through resize/scroll — a collapsed rail or a window
  // resize mid-step shouldn't leave the spotlight pointing at empty space.
  useEffect(() => {
    if (!step || searching) return;
    const update = () => {
      const found = visibleRect(step.selector);
      if (found) setRect(found);
    };
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => {
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
    };
  }, [step, searching]);

  useEffect(() => {
    if (!tourActive) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") skipTour(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [tourActive, skipTour]);

  if (!tourActive || !step || !rect) return null;

  const spotlightStyle: React.CSSProperties = {
    top: rect.top - SPOTLIGHT_PAD,
    left: rect.left - SPOTLIGHT_PAD,
    width: rect.width + SPOTLIGHT_PAD * 2,
    height: rect.height + SPOTLIGHT_PAD * 2,
  };

  const tooltipStyle = placeTooltip(rect, step.placement ?? "bottom");
  const isLast = stepIndex === steps.length - 1;

  return (
    <div className="tour-overlay" role="dialog" aria-modal="true" aria-label={step.title}>
      <div className="tour-spotlight" style={spotlightStyle} />

      <div className="tour-tooltip" style={tooltipStyle}>
        <div className="flex items-start justify-between gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-wide" style={{ color: "var(--muted)" }}>
            Step {stepIndex + 1} of {steps.length}
          </span>
          <button
            type="button"
            onClick={skipTour}
            className="btn btn-icon btn-ghost -mt-1 -mr-1"
            aria-label="Skip tour"
            title="Skip tour"
          >
            <X size={14} />
          </button>
        </div>

        <h3 className="mt-1.5 text-[15px] font-bold" style={{ color: "var(--text)" }}>{step.title}</h3>
        <p className="mt-1.5 text-[13px] leading-relaxed" style={{ color: "var(--muted)" }}>{step.body}</p>

        <div className="mt-4 flex items-center justify-between gap-2">
          <button
            type="button"
            onClick={prevStep}
            disabled={stepIndex === 0}
            className="btn btn-ghost btn-sm"
          >
            <ArrowLeft size={13} />
            Back
          </button>
          <button type="button" onClick={nextStep} className="btn btn-primary btn-sm">
            {isLast ? "Finish" : "Next"}
            {!isLast && <ArrowRight size={13} />}
          </button>
        </div>
      </div>
    </div>
  );
}

function placeTooltip(target: Rect, placement: "right" | "bottom" | "left" | "top"): React.CSSProperties {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const margin = 12;

  let top = target.top;
  let left = target.left;

  if (placement === "right") {
    left = target.left + target.width + TOOLTIP_GAP;
    top = target.top;
  } else if (placement === "left") {
    left = target.left - TOOLTIP_WIDTH - TOOLTIP_GAP;
    top = target.top;
  } else if (placement === "top") {
    left = target.left;
    top = target.top - TOOLTIP_GAP - 160; // approximate card height before layout
  } else {
    left = target.left;
    top = target.top + target.height + TOOLTIP_GAP;
  }

  // Clamp so the tooltip never runs off-screen — the fallback that matters
  // most on a phone, where a right-side placement has nowhere to go.
  left = Math.max(margin, Math.min(left, vw - TOOLTIP_WIDTH - margin));
  top = Math.max(margin, Math.min(top, vh - margin - 40));

  return { top, left, maxWidth: Math.min(TOOLTIP_WIDTH, vw - margin * 2) };
}

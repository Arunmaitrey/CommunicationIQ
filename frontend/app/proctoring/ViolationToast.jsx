import React, { useEffect, useRef, useState, useCallback } from 'react';
import { AlertTriangle } from 'lucide-react';
import { VIOLATION_COPY, MAX_VIOLATIONS } from './constants';
import { isDocumentFullscreen } from './detectors/fullscreenExit';

/**
 * ViolationToast — proctoring violation popup.
 *
 * A single centered card for every violation, styled with the app's own
 * design tokens (--surface, --text, --muted, --brand-grad) so it looks like
 * part of the product rather than a bolted-on component: warning icon,
 * title, body copy, a "Violation X of N" counter, and one wide primary
 * button to acknowledge. The 4th (final) violation gets a red accent and a
 * short violation summary instead of an auto-dismiss timer.
 */
const ViolationToast = ({ violation, onDismiss, onReenterFullscreen }) => {
  const [visible, setVisible] = useState(false);
  const [exiting, setExiting] = useState(false);

  // The parent (ProctorCamera) re-renders very frequently — every
  // detection tick updates faceStatus — and passes onDismiss as an
  // inline arrow function each time, so its identity changes on nearly
  // every render. Keeping it in a ref (instead of the effect's
  // dependency array) means the show/hide effect below only re-runs when
  // `violation` itself actually changes, not on every unrelated parent
  // re-render. Without this, a parent re-render landing mid-dismiss would
  // re-fire the effect, reset visible/exiting back to their "showing"
  // values, and undo the fade-out already in progress — the toast would
  // flash back before finally disappearing.
  const onDismissRef = useRef(onDismiss);
  useEffect(() => {
    onDismissRef.current = onDismiss;
  }, [onDismiss]);

  useEffect(() => {
    if (violation) {
      setVisible(true);
      setExiting(false);

      if (!violation.isFinal) {
        const timer = setTimeout(() => {
          setExiting(true);
          setTimeout(() => {
            setVisible(false);
            onDismissRef.current?.();
          }, 250);
        }, 6000);
        return () => clearTimeout(timer);
      }
    }
  }, [violation]);

  // Whether the browser is actually out of fullscreen right now. This is
  // checked independent of which violation type fired — a TAB_SWITCH
  // violation can just as easily leave you outside fullscreen as a
  // FULLSCREEN_EXIT one does, and either way you need a way back in.
  const needsFullscreen = !isDocumentFullscreen();

  const handleDismiss = useCallback(() => {
    if (needsFullscreen && onReenterFullscreen) {
      onReenterFullscreen();
    }
    setExiting(true);
    setTimeout(() => {
      setVisible(false);
      onDismiss?.();
    }, 250);
  }, [needsFullscreen, onDismiss, onReenterFullscreen]);

  if (!violation || !visible) return null;

  const copy = VIOLATION_COPY[violation.type] || { title: 'Warning', body: 'A proctoring violation was detected.' };
  const isFinal = violation.isFinal;
  const totalSteps = MAX_VIOLATIONS + 1; // strikes before submit, plus the submitting one
  const accent = isFinal ? 'var(--rag-red)' : 'var(--rag-amber)';

  return (
    <div
      className="fixed inset-0 z-[200] flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.6)' }}
    >
      <div
        className="w-full max-w-sm rounded-2xl p-6 text-center transition-all duration-250"
        style={{
          background: 'var(--surface)',
          border: `1px solid var(--border)`,
          boxShadow: '0 20px 60px rgba(0,0,0,0.35)',
          opacity: exiting ? 0 : 1,
          transform: exiting ? 'scale(0.96)' : 'scale(1)',
        }}
      >
        <div
          className="w-14 h-14 rounded-full mx-auto mb-4 flex items-center justify-center"
          style={{ background: `color-mix(in srgb, ${accent} 15%, transparent)` }}
        >
          <AlertTriangle size={28} style={{ color: accent }} />
        </div>

        <h2 className="text-base font-bold" style={{ color: 'var(--text)' }}>
          {isFinal ? 'Exam Auto-Submitted' : copy.title}
        </h2>
        <p className="mt-2 text-[13px] leading-relaxed" style={{ color: 'var(--muted)' }}>
          {isFinal
            ? `You reached ${totalSteps} proctoring violations, so the exam was submitted automatically.`
            : copy.body}
        </p>

        {isFinal && (
          <div
            className="mt-4 rounded-xl p-3 text-left text-[12px] space-y-1.5"
            style={{ background: 'color-mix(in srgb, var(--rag-red) 8%, transparent)' }}
          >
            <div className="flex justify-between">
              <span style={{ color: 'var(--muted)' }}>Total violations</span>
              <span className="font-semibold" style={{ color: 'var(--rag-red)' }}>{violation.count}</span>
            </div>
            <div className="flex justify-between">
              <span style={{ color: 'var(--muted)' }}>Last violation</span>
              <span className="font-medium" style={{ color: 'var(--text)' }}>{copy.title}</span>
            </div>
          </div>
        )}

        <p className="mt-3 text-[11px] font-medium" style={{ color: 'var(--muted)' }}>
          {isFinal ? 'Contact an administrator if you believe this was a mistake.'
            : `Violation ${violation.count} of ${totalSteps}`}
        </p>

        {!isFinal && needsFullscreen ? (
          <div className="mt-4 flex flex-col gap-2">
            <button
              type="button"
              onClick={async () => {
                await onReenterFullscreen?.();
                handleDismiss();
              }}
              className="btn btn-primary w-full"
            >
              Re-enter Fullscreen
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={handleDismiss}
            className="btn btn-primary w-full mt-4"
          >
            OK
          </button>
        )}
      </div>
    </div>
  );
};

export default ViolationToast;

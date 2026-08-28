import React, { useEffect, useState, useCallback } from 'react';
import { VIOLATION_COPY, MAX_VIOLATIONS } from './constants';

/**
 * ViolationToast — non-intrusive violation popup.
 *
 * Shows a slide-in toast for warnings (1-3) and a full info card on the 4th violation.
 * Auto-dismisses after 5 seconds for non-final violations.
 */
const ViolationToast = ({ violation, onDismiss, onReenterFullscreen }) => {
  const [visible, setVisible] = useState(false);
  const [exiting, setExiting] = useState(false);

  useEffect(() => {
    if (violation) {
      setVisible(true);
      setExiting(false);

      if (!violation.isFinal) {
        const timer = setTimeout(() => {
          setExiting(true);
          setTimeout(() => {
            setVisible(false);
            onDismiss?.();
          }, 400);
        }, 5000);
        return () => clearTimeout(timer);
      }
    }
  }, [violation, onDismiss]);

  const handleDismiss = useCallback(() => {
    if (violation?.type === 'fullscreen_exit' && onReenterFullscreen) {
      onReenterFullscreen();
    }
    setExiting(true);
    setTimeout(() => {
      setVisible(false);
      onDismiss?.();
    }, 400);
  }, [violation, onDismiss, onReenterFullscreen]);

  if (!violation || !visible) return null;

  const copy = VIOLATION_COPY[violation.type] || { title: 'Warning', body: 'A proctoring violation was detected.' };
  const isFinal = violation.isFinal;
  const remaining = MAX_VIOLATIONS - violation.count;

  // 4th violation — full info card
  if (isFinal) {
    return (
      <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/60 p-4">
        <div
          className={`w-full max-w-lg rounded-2xl bg-white dark:bg-slate-900 border border-red-200 dark:border-red-800 shadow-2xl p-6 text-center transition-all duration-400 ${
            exiting ? 'opacity-0 scale-95' : 'opacity-100 scale-100'
          }`}
        >
          <div className="w-16 h-16 rounded-full bg-red-100 dark:bg-red-900/50 flex items-center justify-center mx-auto mb-4">
            <svg className="w-8 h-8 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4.5c-.77-.833-2.694-.833-3.464 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z" />
            </svg>
          </div>
          <h2 className="text-xl font-bold text-red-600 dark:text-red-400">Interview Submitted</h2>
          <p className="mt-3 text-sm text-slate-600 dark:text-slate-400">
            You have received {MAX_VIOLATIONS} proctoring violations. Your interview has been automatically submitted.
          </p>
          <div className="mt-4 rounded-xl bg-slate-50 dark:bg-slate-800 p-4 text-left">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-2">Violation Summary</h3>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-slate-600 dark:text-slate-400">Total Violations:</span>
                <span className="font-semibold text-red-600 dark:text-red-400">{violation.count}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-600 dark:text-slate-400">Final Violation:</span>
                <span className="font-medium text-slate-800 dark:text-slate-200">{copy.title}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-600 dark:text-slate-400">Status:</span>
                <span className="font-medium text-red-600 dark:text-red-400">Auto-submitted</span>
              </div>
            </div>
          </div>
          <p className="mt-4 text-xs text-slate-500 dark:text-slate-500">
            Contact an administrator if you believe this was a mistake.
          </p>
          <button
            type="button"
            onClick={handleDismiss}
            className="mt-4 px-5 py-2.5 text-sm font-semibold rounded-xl bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-300 dark:hover:bg-slate-600 transition-colors cursor-pointer"
          >
            Acknowledged
          </button>
        </div>
      </div>
    );
  }

  // Warnings 1-3 — slide-in toast
  return (
    <div className="fixed top-4 right-4 z-[150] pointer-events-auto">
      <div
        className={`w-80 rounded-xl border shadow-lg overflow-hidden transition-all duration-400 ${
          exiting
            ? 'opacity-0 translate-x-full'
            : 'opacity-100 translate-x-0'
        } ${
          violation.count >= 3
            ? 'bg-red-50 dark:bg-red-950/60 border-red-200 dark:border-red-800'
            : 'bg-amber-50 dark:bg-amber-950/60 border-amber-200 dark:border-amber-800'
        }`}
      >
        <div className="flex items-start gap-3 p-4">
          <div
            className={`w-10 h-10 rounded-full flex items-center justify-center shrink-0 ${
              violation.count >= 3
                ? 'bg-red-100 dark:bg-red-900/50'
                : 'bg-amber-100 dark:bg-amber-900/50'
            }`}
          >
            <svg
              className={`w-5 h-5 ${
                violation.count >= 3 ? 'text-red-500' : 'text-amber-500'
              }`}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4.5c-.77-.833-2.694-.833-3.464 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z" />
            </svg>
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between gap-2">
              <h3
                className={`text-sm font-semibold ${
                  violation.count >= 3
                    ? 'text-red-800 dark:text-red-300'
                    : 'text-amber-800 dark:text-amber-300'
                }`}
              >
                {copy.title}
              </h3>
              <button
                type="button"
                onClick={handleDismiss}
                className={`w-6 h-6 flex items-center justify-center rounded-full text-xs cursor-pointer ${
                  violation.count >= 3
                    ? 'bg-red-100 dark:bg-red-900/50 text-red-600 dark:text-red-400 hover:bg-red-200 dark:hover:bg-red-800'
                    : 'bg-amber-100 dark:bg-amber-900/50 text-amber-600 dark:text-amber-400 hover:bg-amber-200 dark:hover:bg-amber-800'
                }`}
                aria-label="Dismiss"
              >
                ✕
              </button>
            </div>
            <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">{copy.body}</p>
            <div className="mt-2 flex items-center gap-2">
              <div className="flex gap-1">
                {Array.from({ length: MAX_VIOLATIONS }).map((_, i) => (
                  <div
                    key={i}
                    className={`w-2 h-2 rounded-full ${
                      i < violation.count
                        ? 'bg-red-500'
                        : 'bg-slate-300 dark:bg-slate-600'
                    }`}
                  />
                ))}
              </div>
              <span className="text-[10px] text-slate-500 dark:text-slate-500">
                {remaining > 0
                  ? `${remaining} warning${remaining !== 1 ? 's' : ''} left`
                  : 'Final warning'}
              </span>
            </div>
          </div>
        </div>
        {violation.type === 'fullscreen_exit' && (
          <div className="px-4 pb-3">
            <button
              type="button"
              onClick={async () => {
                await onReenterFullscreen?.();
                handleDismiss();
              }}
              className="w-full px-3 py-1.5 text-xs font-semibold rounded-lg bg-amber-600 text-white hover:bg-amber-700 transition-colors cursor-pointer"
            >
              Re-enter Fullscreen
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default ViolationToast;

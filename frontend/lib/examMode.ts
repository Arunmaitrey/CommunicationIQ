/**
 * Global exam mode flag.
 *
 * When a practice or exam is active, the AppShell hides the nav rail so
 * only the ExamSidebar is visible — a single-sidebar layout that matches
 * the standard exam interface.
 */
"use client";

let _active = false;
const _listeners = new Set<() => void>();

export function isExamMode(): boolean {
  return _active;
}

export function setExamMode(active: boolean): void {
  if (_active === active) return;
  _active = active;
  _listeners.forEach(fn => fn());
}

/** Subscribe to exam-mode changes. Returns an unsubscribe function. */
export function onExamModeChange(fn: () => void): () => void {
  _listeners.add(fn);
  return () => { _listeners.delete(fn); };
}

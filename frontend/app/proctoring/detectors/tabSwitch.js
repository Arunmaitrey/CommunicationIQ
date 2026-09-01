import { VIOLATION_TYPES } from '../constants';

/**
 * Tab-switch / window-away detection using the Page Visibility API.
 *
 * Unlike the camera-based detectors, this is event-driven rather than
 * polled, and needs no sustained-duration "confirm window": setInterval/
 * setTimeout callbacks are throttled (often paused entirely) once a tab is
 * backgrounded, so waiting out a grace period while hidden isn't reliable.
 * Instead the violation is confirmed the instant the tab is backgrounded,
 * and the UI clears back to normal the moment the candidate returns.
 *
 * document.hidden/visibilitychange is used rather than window blur/focus:
 * blur also fires for in-page focus changes (browser permission prompts,
 * clicking into the video element, devtools, a second monitor) that are
 * not actually leaving the exam tab, and would produce false positives.
 * visibilitychange only fires for a genuine tab switch, minimize, or
 * switching to another application that covers the tab — which is what
 * "tab switching" should mean here.
 */
export function isTabHidden() {
  return typeof document !== 'undefined' && document.hidden === true;
}

/**
 * Subscribes to tab visibility changes. `onHidden` fires the moment the
 * exam tab is backgrounded; `onVisible` fires when the candidate returns.
 * Returns an unsubscribe function.
 */
export function subscribeTabSwitch(onHidden, onVisible) {
  const handleVisibilityChange = () => {
    if (document.hidden) {
      onHidden();
    } else {
      onVisible();
    }
  };

  document.addEventListener('visibilitychange', handleVisibilityChange);

  return () => {
    document.removeEventListener('visibilitychange', handleVisibilityChange);
  };
}

/**
 * @returns {string|null} VIOLATION_TYPES.TAB_SWITCH if the tab is
 *   currently hidden/backgrounded, else null.
 */
export function checkTabSwitch() {
  return isTabHidden() ? VIOLATION_TYPES.TAB_SWITCH : null;
}

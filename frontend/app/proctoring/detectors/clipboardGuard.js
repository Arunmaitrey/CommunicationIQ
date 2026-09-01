/**
 * Copy / cut / paste / right-click blocking for the exam surface.
 *
 * This is a *prevention* control, not a detector: unlike the other
 * modules in this folder it doesn't classify a VIOLATION_TYPES value,
 * it just stops the browser default action so candidates can't copy
 * question text out, paste answers in, or open a context menu to do
 * either. It's wired up the same way subscribeTabSwitch is — a single
 * subscribe function that attaches document-level listeners and
 * returns an unsubscribe callback for the calling useEffect's cleanup.
 *
 * Kept independent of the violation/confirmViolation pipeline on
 * purpose: blocking happens instantly on every attempt with no grace
 * window, and repeated attempts shouldn't by themselves count toward
 * MAX_VIOLATIONS the way a sustained camera/tab issue does. If you
 * want attempts to also count as violations, call onBlocked with a
 * VIOLATION_TYPES entry from the consuming component.
 */

const BLOCKED_EVENTS = ['copy', 'cut', 'paste', 'contextmenu'];

/**
 * Subscribes to clipboard and right-click events on the document and
 * prevents their default action for as long as the exam is active.
 *
 * @param {Object} [options]
 * @param {boolean} [options.blockSelection] - Also prevent text
 *   selection (selectstart), which stops copy via keyboard shortcuts
 *   from having anything selected to copy in the first place. Off by
 *   default since it also blocks selecting one's own typed answers in
 *   editable fields unless you exempt them (see isEditableTarget).
 * @param {(eventType: string) => void} [options.onBlocked] - Optional
 *   callback fired every time an attempt is blocked, e.g. to surface
 *   a toast ("Copy/paste is disabled during this exam") or to log it.
 * @returns {() => void} Unsubscribe function.
 */
export function subscribeClipboardGuard({
  blockSelection = false,
  onBlocked
} = {}) {
  if (typeof document === 'undefined') {
    return () => {};
  }

  const handleBlockedEvent = (event) => {
    event.preventDefault();
    event.stopPropagation();
    onBlocked?.(event.type);
  };

  BLOCKED_EVENTS.forEach((type) =>
    document.addEventListener(type, handleBlockedEvent, true)
  );

  let handleSelectStart;
  if (blockSelection) {
    handleSelectStart = (event) => {
      // Still allow selecting text the candidate typed themselves
      // (an <input>/<textarea>/contentEditable answer box) — only
      // block selecting exam/question content for copying.
      if (isEditableTarget(event.target)) return;
      event.preventDefault();
    };
    document.addEventListener('selectstart', handleSelectStart, true);
  }

  return () => {
    BLOCKED_EVENTS.forEach((type) =>
      document.removeEventListener(type, handleBlockedEvent, true)
    );
    if (handleSelectStart) {
      document.removeEventListener('selectstart', handleSelectStart, true);
    }
  };
}

function isEditableTarget(target) {
  if (!target) return false;
  const tag = target.tagName;
  return (
    tag === 'INPUT' ||
    tag === 'TEXTAREA' ||
    target.isContentEditable === true
  );
}

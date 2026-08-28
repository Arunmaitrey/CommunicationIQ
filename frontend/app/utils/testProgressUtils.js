/**
 * Test progress persistence utilities.
 *
 * Usage in any test page:
 *
 *   import { saveProgress, loadProgress, clearProgress, hasProgress } from '../utils/testProgressUtils';
 *
 *   const TEST_KEY = 'paragraph_compression';
 *
 *   // On each answer / state change:
 *   saveProgress(TEST_KEY, { currentQuestion, answers, timeRemaining });
 *
 *   // On mount — check for a draft:
 *   if (hasProgress(TEST_KEY)) {
 *     const draft = loadProgress(TEST_KEY);
 *     // restore state from draft
 *   }
 *
 *   // After successful submission:
 *   clearProgress(TEST_KEY);
 */

const STORAGE_PREFIX = 'test_progress_';
const EXPIRY_MS = 2 * 60 * 60 * 1000; // 2 hours — abandon stale drafts

/**
 * Persist current test progress.
 * @param {string} testType  - matches Score testType enum
 * @param {object} data      - arbitrary serialisable state
 */
export const saveProgress = (testType, data) => {
  try {
    const payload = {
      testType,
      savedAt: Date.now(),
      data
    };
    localStorage.setItem(`${STORAGE_PREFIX}${testType}`, JSON.stringify(payload));
  } catch (e) {
    // localStorage might be full or unavailable — fail silently
  }
};

/**
 * Load saved progress for a test type.
 * Returns null if not found or if the draft has expired.
 * @param {string} testType
 * @returns {{ testType, savedAt, data }|null}
 */
export const loadProgress = (testType) => {
  try {
    const raw = localStorage.getItem(`${STORAGE_PREFIX}${testType}`);
    if (!raw) return null;

    const payload = JSON.parse(raw);

    // Discard stale drafts
    if (Date.now() - payload.savedAt > EXPIRY_MS) {
      clearProgress(testType);
      return null;
    }

    return payload;
  } catch (e) {
    return null;
  }
};

/**
 * Check if unexpired progress exists for a test type.
 * @param {string} testType
 * @returns {boolean}
 */
export const hasProgress = (testType) => loadProgress(testType) !== null;

/**
 * Remove saved progress after a successful submission.
 * @param {string} testType
 */
export const clearProgress = (testType) => {
  try {
    localStorage.removeItem(`${STORAGE_PREFIX}${testType}`);
  } catch (e) {
    // ignore
  }
};

/**
 * Clear all in-progress test drafts (e.g. on logout).
 */
export const clearAllProgress = () => {
  try {
    Object.keys(localStorage)
      .filter(key => key.startsWith(STORAGE_PREFIX))
      .forEach(key => localStorage.removeItem(key));
  } catch (e) {
    // ignore
  }
};

/**
 * Returns the age of a saved draft in a human-readable format.
 * Useful for showing "Resume from 5 minutes ago" in the UI.
 * @param {string} testType
 * @returns {string|null}
 */
export const getProgressAge = (testType) => {
  const progress = loadProgress(testType);
  if (!progress) return null;

  const ageMs = Date.now() - progress.savedAt;
  const ageMin = Math.floor(ageMs / 60000);

  if (ageMin < 1) return 'just now';
  if (ageMin === 1) return '1 minute ago';
  if (ageMin < 60) return `${ageMin} minutes ago`;

  const ageHr = Math.floor(ageMin / 60);
  return `${ageHr} hour${ageHr > 1 ? 's' : ''} ago`;
};

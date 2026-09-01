import { VIOLATION_TYPES } from '../constants';

/**
 * Checks for more than one person present.
 *
 * Face-count alone only catches near-frontal faces — a second person
 * facing away or sideways (back of head visible) won't be counted by
 * MediaPipe's FaceDetector at all. Passing in personCount (a person
 * *body* count from a general object detector, e.g. MediaPipe
 * ObjectDetector's "person" class) closes that gap, since a body is
 * still recognized regardless of which way someone is facing.
 *
 * @param {Array} detections - detectorResult.detections (from FaceDetector)
 * @param {number} [personCount] - optional person-body count from a
 *   separate object detector. Omit/pass undefined if not available —
 *   the check still works on face count alone.
 * @returns {string|null} VIOLATION_TYPES.MULTIPLE_FACES if triggered, else null
 */
export function checkMultipleFaces(detections, personCount) {
  const faceCount = detections ? detections.length : 0;

  if (faceCount > 1) {
    return VIOLATION_TYPES.MULTIPLE_FACES;
  }

  if (typeof personCount === 'number' && personCount > 1) {
    return VIOLATION_TYPES.MULTIPLE_FACES;
  }

  return null;
}



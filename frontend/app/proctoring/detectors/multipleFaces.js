import { VIOLATION_TYPES } from '../constants';

/**
 * Checks for more than one person present.
 *
 * Two independent signals, deliberately weighted differently:
 *
 *   1. More than one *face* (MediaPipe FaceDetector). Strong evidence -- the
 *      detector only counts faces it can actually see, so this is believed.
 *
 *   2. More than one *body* (the "person" class of the general object
 *      detector). Weak evidence, and the reason QA saw "multi-face detected"
 *      flatly denied by the candidate: a poster, a reflection in a window, a
 *      mannequin or a chair reads as a person and fired the violation on its
 *      own. This path therefore requires that at least one face is also
 *      visible (with no face at all the situation is NO_FACE, not multi-face)
 *      and a separate, longer confidence window -- see the caller.
 *
 * Face-count alone only catches near-frontal faces: a second person facing
 * away or sideways won't be counted by FaceDetector at all, which is why the
 * body signal is used at all rather than dropped.
 *
 * @param {Array} detections - detectorResult.detections (from FaceDetector)
 * @param {number} [personCount] - person-body count from the object detector
 * @returns {{type: string, faceCount: number, personCount: number,
 *            basis: 'faces'|'bodies'}|null}
 *   The violation plus the evidence behind it (kept for the attempt's
 *   proctoring summary -- a count with no evidence is an assertion), or null.
 */
export function checkMultipleFaces(detections, personCount) {
  const faceCount = detections ? detections.length : 0;
  const bodies = typeof personCount === 'number' ? personCount : 0;

  if (faceCount > 1) {
    return {
      type: VIOLATION_TYPES.MULTIPLE_FACES,
      faceCount,
      personCount: bodies,
      basis: 'faces'
    };
  }

  // Body-only: needs a face on screen. Zero faces is NO_FACE and is handled
  // by its own check -- calling it multi-face told the candidate the wrong
  // thing and cost them a strike for a camera problem.
  if (bodies > 1 && faceCount >= 1) {
    return {
      type: VIOLATION_TYPES.MULTIPLE_FACES,
      faceCount,
      personCount: bodies,
      basis: 'bodies'
    };
  }

  return null;
}

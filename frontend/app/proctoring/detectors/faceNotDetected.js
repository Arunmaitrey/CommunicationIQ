import { VIOLATION_TYPES } from '../constants';

/**
 * Checks MediaPipe FaceDetector output for "no face present".
 * @param {Array} detections - detectorResult.detections
 * @returns {string|null} VIOLATION_TYPES.NO_FACE if triggered, else null
 */
export function checkFaceNotDetected(detections) {
  if (!detections || detections.length === 0) {
    return VIOLATION_TYPES.NO_FACE;
  }
  return null;
}

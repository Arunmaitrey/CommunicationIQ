import { VIOLATION_TYPES } from '../constants';

/**
 * Checks MediaPipe FaceDetector output for more than one face.
 * @param {Array} detections - detectorResult.detections
 * @returns {string|null} VIOLATION_TYPES.MULTIPLE_FACES if triggered, else null
 */
export function checkMultipleFaces(detections) {
  if (detections && detections.length > 1) {
    return VIOLATION_TYPES.MULTIPLE_FACES;
  }
  return null;
}

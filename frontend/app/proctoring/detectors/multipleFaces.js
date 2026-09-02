import { VIOLATION_TYPES } from '../constants';

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
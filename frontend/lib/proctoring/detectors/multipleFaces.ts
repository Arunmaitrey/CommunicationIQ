import { VIOLATION_TYPES, type ViolationType } from "../constants";

/** Checks for more than one face present. */
export function checkMultipleFaces(
  detections: unknown[] | null | undefined,
  personCount?: number,
): ViolationType | null {
  const faceCount = detections ? detections.length : 0;

  if (faceCount > 1) {
    return VIOLATION_TYPES.MULTIPLE_FACES;
  }

  if (typeof personCount === "number" && personCount > 1) {
    return VIOLATION_TYPES.MULTIPLE_FACES;
  }

  return null;
}

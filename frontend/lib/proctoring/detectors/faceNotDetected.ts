import { VIOLATION_TYPES, type ViolationType } from "../constants";

/** Checks MediaPipe FaceDetector output for "no face present". */
export function checkFaceNotDetected(detections: unknown[] | null | undefined): ViolationType | null {
  if (!detections || detections.length === 0) {
    return VIOLATION_TYPES.NO_FACE;
  }
  return null;
}

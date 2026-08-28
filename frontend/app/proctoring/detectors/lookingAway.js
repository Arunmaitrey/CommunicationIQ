import { VIOLATION_TYPES } from '../constants';

/*
  Key MediaPipe FaceLandmarker landmark indices used:
    1   = Nose tip
    10  = Forehead
    33  = Left eye
    152 = Chin
    263 = Right eye
*/

export function getHeadPose(landmarks) {
  if (!landmarks || landmarks.length < 264) {
    return null;
  }

  const nose = landmarks[1];
  const forehead = landmarks[10];
  const leftEye = landmarks[33];
  const rightEye = landmarks[263];
  const chin = landmarks[152];

  if (!nose || !forehead || !leftEye || !rightEye || !chin) {
    return null;
  }

  const eyeCenterX = (leftEye.x + rightEye.x) / 2;
  const eyeCenterY = (leftEye.y + rightEye.y) / 2;
  const eyeDistance = Math.abs(rightEye.x - leftEye.x);
  const faceHeight = Math.abs(chin.y - forehead.y);

  if (eyeDistance < 0.01 || faceHeight < 0.01) {
    return null;
  }

  const horizontalOffset = (nose.x - eyeCenterX) / eyeDistance;
  const verticalOffset = (nose.y - eyeCenterY) / faceHeight;

  return { horizontalOffset, verticalOffset };
}

// Enter/exit are different thresholds (hysteresis) so a single noisy frame
// right at the boundary doesn't flip state back and forth and keep
// resetting the 3-second confirmation window.
const ENTER_THRESHOLDS = { horizontal: 0.35, down: 0.35, up: -0.15 };
const EXIT_THRESHOLDS = { horizontal: 0.25, down: 0.25, up: -0.08 };

const SMOOTHING_ALPHA = 0.35; // 0-1, lower = smoother but slower to react

/**
 * Stateful tracker: smooths per-frame head-pose readings (EMA) and applies
 * hysteresis so momentary jitter doesn't repeatedly clear/restart the
 * caller's confirmation window. Create one instance per exam session and
 * call .check(faceLandmarks) every frame; call .reset() when the face is
 * lost or proctoring restarts.
 */
export function createLookingAwayTracker() {
  let smoothedH = 0;
  let smoothedV = 0;
  let initialized = false;
  let currentlyAway = false;

  return {
    reset() {
      initialized = false;
      currentlyAway = false;
      smoothedH = 0;
      smoothedV = 0;
    },

    check(faceLandmarks) {
      const pose = getHeadPose(faceLandmarks);

      // Pose unreadable this frame (e.g. transient landmark glitch) — hold
      // the previous state rather than flip-flopping.
      if (!pose) {
        return currentlyAway ? VIOLATION_TYPES.LOOKING_AWAY : null;
      }

      if (!initialized) {
        smoothedH = pose.horizontalOffset;
        smoothedV = pose.verticalOffset;
        initialized = true;
      } else {
        smoothedH += SMOOTHING_ALPHA * (pose.horizontalOffset - smoothedH);
        smoothedV += SMOOTHING_ALPHA * (pose.verticalOffset - smoothedV);
      }

      const crossedEnter =
        Math.abs(smoothedH) > ENTER_THRESHOLDS.horizontal ||
        smoothedV > ENTER_THRESHOLDS.down ||
        smoothedV < ENTER_THRESHOLDS.up;

      const withinExit =
        Math.abs(smoothedH) <= EXIT_THRESHOLDS.horizontal &&
        smoothedV <= EXIT_THRESHOLDS.down &&
        smoothedV >= EXIT_THRESHOLDS.up;

      if (!currentlyAway && crossedEnter) {
        currentlyAway = true;
      } else if (currentlyAway && withinExit) {
        currentlyAway = false;
      }

      return currentlyAway ? VIOLATION_TYPES.LOOKING_AWAY : null;
    }
  };
}

/**
 * One-off, non-smoothed check (e.g. for tests). Prefer
 * createLookingAwayTracker() for the live detection loop.
 */
export function checkLookingAway(faceLandmarks) {
  const headPose = getHeadPose(faceLandmarks);
  if (!headPose) return null;

  const away =
    Math.abs(headPose.horizontalOffset) > ENTER_THRESHOLDS.horizontal ||
    headPose.verticalOffset > ENTER_THRESHOLDS.down ||
    headPose.verticalOffset < ENTER_THRESHOLDS.up;

  return away ? VIOLATION_TYPES.LOOKING_AWAY : null;
}

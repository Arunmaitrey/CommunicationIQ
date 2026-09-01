import { VIOLATION_TYPES } from '../constants';

/*
  MediaPipe FaceLandmarker landmarks:
  1   nose tip
  10  forehead
  33, 133   left-eye horizontal bounds
  159, 145  left-eye vertical bounds
  263, 362  right-eye horizontal bounds
  386, 374  right-eye vertical bounds
  152 chin

  Iris landmarks are normally included when FaceLandmarker returns 478 points:
  468-472 left iris
  473-477 right iris
*/

const HEAD_ENTER = {
  horizontal: 0.35,
  down: 0.35,
  up: -0.15,
};

const HEAD_EXIT = {
  horizontal: 0.25,
  down: 0.25,
  up: -0.08,
};

const GAZE_ENTER = {
  horizontal: 0.18,
  vertical: 0.18,
};

const GAZE_EXIT = {
  horizontal: 0.12,
  vertical: 0.12,
};

const SMOOTHING_ALPHA = 0.35;

function averageLandmarks(landmarks, indices) {
  const points = indices.map((index) => landmarks[index]).filter(Boolean);

  if (points.length !== indices.length) {
    return null;
  }

  return {
    x: points.reduce((sum, point) => sum + point.x, 0) / points.length,
    y: points.reduce((sum, point) => sum + point.y, 0) / points.length,
  };
}

function getNormalizedEyePosition(iris, left, right, top, bottom) {
  const minX = Math.min(left.x, right.x);
  const maxX = Math.max(left.x, right.x);
  const minY = Math.min(top.y, bottom.y);
  const maxY = Math.max(top.y, bottom.y);

  const eyeWidth = maxX - minX;
  const eyeHeight = maxY - minY;

  if (eyeWidth < 0.005 || eyeHeight < 0.005) {
    return null;
  }

  return {
    // 0 means iris is near the eye centre.
    horizontal: ((iris.x - minX) / eyeWidth - 0.5) * 2,
    vertical: ((iris.y - minY) / eyeHeight - 0.5) * 2,
  };
}

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

  return {
    horizontalOffset: (nose.x - eyeCenterX) / eyeDistance,
    verticalOffset: (nose.y - eyeCenterY) / faceHeight,
  };
}

export function getEyeGaze(landmarks) {
  // Iris landmarks are unavailable in some FaceLandmarker configurations.
  if (!landmarks || landmarks.length < 478) {
    return null;
  }

  const leftIris = averageLandmarks(landmarks, [468, 469, 470, 471, 472]);
  const rightIris = averageLandmarks(landmarks, [473, 474, 475, 476, 477]);

  const leftEye = getNormalizedEyePosition(
    leftIris,
    landmarks[33],
    landmarks[133],
    landmarks[159],
    landmarks[145],
  );

  const rightEye = getNormalizedEyePosition(
    rightIris,
    landmarks[362],
    landmarks[263],
    landmarks[386],
    landmarks[374],
  );

  if (!leftEye || !rightEye) {
    return null;
  }

  return {
    horizontalOffset: (leftEye.horizontal + rightEye.horizontal) / 2,
    verticalOffset: (leftEye.vertical + rightEye.vertical) / 2,
  };
}

function getHeadDirection(horizontal, vertical) {
  if (horizontal > HEAD_ENTER.horizontal) return 'HEAD_RIGHT';
  if (horizontal < -HEAD_ENTER.horizontal) return 'HEAD_LEFT';
  if (vertical > HEAD_ENTER.down) return 'HEAD_DOWN';
  if (vertical < HEAD_ENTER.up) return 'HEAD_UP';

  return 'FORWARD';
}

function getGazeDirection(horizontal, vertical) {
  if (horizontal > GAZE_ENTER.horizontal) return 'EYES_RIGHT';
  if (horizontal < -GAZE_ENTER.horizontal) return 'EYES_LEFT';
  if (vertical > GAZE_ENTER.vertical) return 'EYES_DOWN';
  if (vertical < -GAZE_ENTER.vertical) return 'EYES_UP';

  return 'SCREEN';
}

/*
  If your camera preview is mirrored with CSS transform: scaleX(-1),
  the visual meaning of LEFT and RIGHT is reversed. Detection still works;
  only the displayed direction label needs swapping.
*/
function getAttentionDirection(headDirection, gazeDirection) {
  if (headDirection !== 'FORWARD') return headDirection;
  if (gazeDirection !== 'SCREEN') return gazeDirection;

  return 'SCREEN';
}

export function createLookingAwayTracker() {
  let initialized = false;
  let currentlyAway = false;

  let smoothedHeadH = 0;
  let smoothedHeadV = 0;
  let smoothedGazeH = 0;
  let smoothedGazeV = 0;

  function smooth(previous, current) {
    return previous + SMOOTHING_ALPHA * (current - previous);
  }

  return {
    reset() {
      initialized = false;
      currentlyAway = false;
      smoothedHeadH = 0;
      smoothedHeadV = 0;
      smoothedGazeH = 0;
      smoothedGazeV = 0;
    },

    checkDetailed(faceLandmarks) {
      const headPose = getHeadPose(faceLandmarks);
      const eyeGaze = getEyeGaze(faceLandmarks);

      // Do not mark a user as looking away based on a missing landmark frame.
      if (!headPose) {
        return {
          violation: currentlyAway ? VIOLATION_TYPES.LOOKING_AWAY : null,
          isAway: currentlyAway,
          direction: currentlyAway ? 'UNKNOWN' : 'SCREEN',
          headDirection: 'UNKNOWN',
          gazeDirection: 'UNKNOWN',
        };
      }

      if (!initialized) {
        smoothedHeadH = headPose.horizontalOffset;
        smoothedHeadV = headPose.verticalOffset;
        smoothedGazeH = eyeGaze?.horizontalOffset ?? 0;
        smoothedGazeV = eyeGaze?.verticalOffset ?? 0;
        initialized = true;
      } else {
        smoothedHeadH = smooth(smoothedHeadH, headPose.horizontalOffset);
        smoothedHeadV = smooth(smoothedHeadV, headPose.verticalOffset);

        if (eyeGaze) {
          smoothedGazeH = smooth(smoothedGazeH, eyeGaze.horizontalOffset);
          smoothedGazeV = smooth(smoothedGazeV, eyeGaze.verticalOffset);
        }
      }

      const headAwayEnter =
        Math.abs(smoothedHeadH) > HEAD_ENTER.horizontal ||
        smoothedHeadV > HEAD_ENTER.down ||
        smoothedHeadV < HEAD_ENTER.up;

      const headWithinExit =
        Math.abs(smoothedHeadH) <= HEAD_EXIT.horizontal &&
        smoothedHeadV <= HEAD_EXIT.down &&
        smoothedHeadV >= HEAD_EXIT.up;

      const gazeAwayEnter =
        eyeGaze &&
        (Math.abs(smoothedGazeH) > GAZE_ENTER.horizontal ||
          Math.abs(smoothedGazeV) > GAZE_ENTER.vertical);

      const gazeWithinExit =
        !eyeGaze ||
        (Math.abs(smoothedGazeH) <= GAZE_EXIT.horizontal &&
          Math.abs(smoothedGazeV) <= GAZE_EXIT.vertical);

      const crossedEnter = headAwayEnter || gazeAwayEnter;
      const withinExit = headWithinExit && gazeWithinExit;

      if (!currentlyAway && crossedEnter) {
        currentlyAway = true;
      } else if (currentlyAway && withinExit) {
        currentlyAway = false;
      }

      const headDirection = getHeadDirection(smoothedHeadH, smoothedHeadV);
      const gazeDirection = eyeGaze
        ? getGazeDirection(smoothedGazeH, smoothedGazeV)
        : 'UNAVAILABLE';

      return {
        violation: currentlyAway ? VIOLATION_TYPES.LOOKING_AWAY : null,
        isAway: currentlyAway,
        direction: getAttentionDirection(headDirection, gazeDirection),
        headDirection,
        gazeDirection,
        headPose: {
          horizontalOffset: smoothedHeadH,
          verticalOffset: smoothedHeadV,
        },
        eyeGaze: eyeGaze
          ? {
              horizontalOffset: smoothedGazeH,
              verticalOffset: smoothedGazeV,
            }
          : null,
      };
    },

    // Backwards-compatible: existing code can continue calling tracker.check().
    check(faceLandmarks) {
      return this.checkDetailed(faceLandmarks).violation;
    },
  };
}

export function checkLookingAway(faceLandmarks) {
  const headPose = getHeadPose(faceLandmarks);
  const eyeGaze = getEyeGaze(faceLandmarks);

  if (!headPose) {
    return null;
  }

  const headAway =
    Math.abs(headPose.horizontalOffset) > HEAD_ENTER.horizontal ||
    headPose.verticalOffset > HEAD_ENTER.down ||
    headPose.verticalOffset < HEAD_ENTER.up;

  const gazeAway =
    eyeGaze &&
    (Math.abs(eyeGaze.horizontalOffset) > GAZE_ENTER.horizontal ||
      Math.abs(eyeGaze.verticalOffset) > GAZE_ENTER.vertical);

  return headAway || gazeAway ? VIOLATION_TYPES.LOOKING_AWAY : null;
}
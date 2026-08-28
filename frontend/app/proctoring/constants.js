export const CONFIRM_DURATION_MS = 3000; // default / fallback
export const MAX_VIOLATIONS = 3;
export const DETECTION_INTERVAL_MS = 200;

export const VIOLATION_TYPES = {
  NO_FACE: 'no_face',
  MULTIPLE_FACES: 'multiple_faces',
  LOOKING_AWAY: 'looking_away',
  FULLSCREEN_EXIT: 'fullscreen_exit',
  TAB_SWITCH: 'tab_switch'
};

// Per-type sustained-duration before a violation is confirmed. Any type
// not listed here falls back to CONFIRM_DURATION_MS.
export const CONFIRM_DURATIONS_MS = {
  [VIOLATION_TYPES.NO_FACE]: 1500,
  [VIOLATION_TYPES.MULTIPLE_FACES]: 1000,
  [VIOLATION_TYPES.LOOKING_AWAY]: 1500,
  [VIOLATION_TYPES.FULLSCREEN_EXIT]: 2000,
  [VIOLATION_TYPES.TAB_SWITCH]: 0
};

export const getConfirmDuration = (type) =>
  CONFIRM_DURATIONS_MS[type] ?? CONFIRM_DURATION_MS;

export const VIOLATION_COPY = {
  [VIOLATION_TYPES.NO_FACE]: {
    title: 'Face Not Detected',
    body: 'We cannot detect your face. Please make sure your face is clearly visible in the camera.'
  },
  [VIOLATION_TYPES.MULTIPLE_FACES]: {
    title: 'Multiple Faces Detected',
    body: 'Only one person is allowed during the test. Please make sure no other person is visible in the camera.'
  },
  [VIOLATION_TYPES.LOOKING_AWAY]: {
    title: 'Please Look at the Screen',
    body: 'Your face appears to be turned away from the screen. Please look directly at the screen to continue.'
  },
  [VIOLATION_TYPES.FULLSCREEN_EXIT]: {
    title: 'Fullscreen Exited',
    body: 'You must stay in fullscreen mode during the exam. Re-enter fullscreen to continue.'
  },
  [VIOLATION_TYPES.TAB_SWITCH]: {
    title: 'Tab Switch Detected',
    body: 'Switching tabs or windows is not allowed during the interview. Please stay on this tab.'
  }
};
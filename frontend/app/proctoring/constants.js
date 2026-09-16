
export const CONFIRM_DURATION_MS = 1500; // default / fallback
// One strike policy for the whole app. This used to be 6 here while
// lib/proctoring used 3, so the same sitting could end after three warnings
// or after six depending on which surface was watching (QA: "no proper
// counts of proctoring"). Three, and the copy says three.
export const MAX_VIOLATIONS = 3;
export const DETECTION_INTERVAL_MS = 300;
export const PHONE_DETECTION_INTERVAL_MS = 800; // YOLOv8n (wasm) inference is heavier than face-mesh — poll slower. Raise this further (e.g. 1500-2000) on low-end devices if the UI feels sluggish.

export const VIOLATION_TYPES = {
  NO_FACE: 'no_face',
  MULTIPLE_FACES: 'multiple_faces',
  LOOKING_AWAY: 'looking_away',
  FULLSCREEN_EXIT: 'fullscreen_exit',
  MOBILE_PHONE: 'mobile_phone',
  TAB_SWITCH: 'tab_switch'
};

// Per-type sustained-duration before a violation is confirmed. Any type
// not listed here falls back to CONFIRM_DURATION_MS.
//
// TAB_SWITCH is 0 on purpose: it's confirmed the instant the tab is
// backgrounded, not after a grace window — see detectors/tabSwitch.js for
// why a duration-based confirm doesn't work reliably for a hidden tab.
export const CONFIRM_DURATIONS_MS = {
  [VIOLATION_TYPES.NO_FACE]: 2000,
  // Faces in view: believed quickly. A *body* count alone is a weaker
  // signal (see detectors/multipleFaces.js) and has to persist much longer
  // before it costs the candidate a strike.
  [VIOLATION_TYPES.MULTIPLE_FACES]: 1500,
  MULTIPLE_FACES_BODIES: 5000,
  [VIOLATION_TYPES.LOOKING_AWAY]: 2000,
  [VIOLATION_TYPES.FULLSCREEN_EXIT]: 3000,
  [VIOLATION_TYPES.MOBILE_PHONE]: 1500,
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
  [VIOLATION_TYPES.MOBILE_PHONE]: {
    title: 'Mobile Phone Detected',
    body: 'A mobile phone was detected in the camera view. Please remove it from view to continue.'
  },
  [VIOLATION_TYPES.TAB_SWITCH]: {
    title: 'Tab Switch Detected',
    body: 'You switched away from the exam tab or window. Please stay on this tab for the entire duration of the exam.'
  }
};

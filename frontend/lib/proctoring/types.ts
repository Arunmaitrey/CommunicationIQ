/**
 * Proctoring event types and interfaces.
 *
 * All detection happens client-side. Events are collected and sent to the
 * server only at submission time — nothing is streamed in real-time, which
 * keeps bandwidth low and avoids making students feel surveilled during
 * the test itself.
 */

export type ProctorFlag =
  | "tab_blur"
  | "tab_focus"
  | "multiple_faces"
  | "no_face"
  | "face_changed"
  | "gaze_away"
  | "screenshot_attempt"
  | "fullscreen_exit"
  | "clipboard_paste"
  | "devtools_open"
  | "right_click"
  | "copy_paste"
  | "phone_detected"
  | "camera_blocked";

export interface ProctorEvent {
  /** ISO timestamp when the event occurred */
  ts: string;
  /** What happened */
  flag: ProctorFlag;
  /** Optional detail string */
  detail?: string;
  /** Severity: low / medium / high */
  severity: "low" | "medium" | "high";
}

export interface ProctorState {
  /** Running event log */
  events: ProctorEvent[];
  /** Number of high-severity strikes (3 = auto-submit) */
  strikes: number;
  /** Camera stream active */
  cameraActive: boolean;
  /** Currently in fullscreen */
  isFullscreen: boolean;
  /** Currently focused on the tab */
  isFocused: boolean;
  /** Number of faces detected (0 = none, 1 = normal, 2+ = multiple people) */
  faceCount: number;
  /** Whether gaze is on-screen */
  gazeOnScreen: boolean;
}

export interface ProctorSummary {
  total_events: number;
  strikes: number;
  events: ProctorEvent[];
  /** Whether the student should be auto-submitted */
  should_auto_submit: boolean;
}

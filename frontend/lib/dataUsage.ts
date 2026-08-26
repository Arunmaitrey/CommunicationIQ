/**
 * ACC-04: Data-cost transparency.
 *
 * Show MB used per session so students on prepaid data plans know what
 * the platform costs them. Audio quality settings trade fidelity for
 * data on request.
 */

let totalBytesUploaded = 0;
let sessionStart = Date.now();

/** Track bytes uploaded (called from upload.ts after each successful POST). */
export function trackUpload(bytes: number) {
  totalBytesUploaded += bytes;
}

/** Get total MB uploaded this session. */
export function getUploadedMB(): number {
  return totalBytesUploaded / (1024 * 1024);
}

/** Get session duration in minutes. */
export function getSessionMinutes(): number {
  return (Date.now() - sessionStart) / 60000;
}

/** Get upload rate in KB/min. */
export function getUploadRate(): number {
  const minutes = getSessionMinutes();
  if (minutes < 0.1) return 0;
  return (totalBytesUploaded / 1024) / minutes;
}

/** Reset session tracking (e.g., on sign-out). */
export function resetSession() {
  totalBytesUploaded = 0;
  sessionStart = Date.now();
}

/** Format bytes for display. */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

/** Format MB for display. */
export function formatMB(mb: number): string {
  if (mb < 0.01) return "< 0.01 MB";
  return `${mb.toFixed(2)} MB`;
}

/** Estimate data usage for a typical session (in MB). */
export function estimateSessionUsage(itemsCount: number): number {
  // Each recording is ~30s of 16kHz mono WAV ≈ 960 KB ≈ ~1 MB
  // Plus overhead per upload ≈ 0.5 KB
  const avgRecordingMB = 0.96;
  const overheadMB = 0.001 * itemsCount;
  return itemsCount * avgRecordingMB + overheadMB;
}

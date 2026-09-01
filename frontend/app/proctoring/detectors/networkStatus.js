/**
 * Error classification for proctoring init/runtime failures.
 *
 * Everything that failed to start proctoring used to be shown to the
 * candidate as one generic "Proctoring Unavailable" message, which made a
 * dropped connection to the MediaPipe CDN (jsdelivr / storage.googleapis.com
 * — required to load the face/object-detection models) look identical to a
 * denied camera permission. These are very different problems for the
 * candidate to act on, so callers should classify the error and show the
 * right message (see ProctorCamera's blockProctoring()).
 */

export function isNetworkError(error) {
  if (typeof navigator !== 'undefined' && navigator.onLine === false) {
    return true;
  }

  const message = String(error?.message || error || '').toLowerCase();
  const name = String(error?.name || '').toLowerCase();

  return (
    message.includes('failed to fetch') ||
    message.includes('load failed') ||
    message.includes('network error') ||
    message.includes('networkerror') ||
    message.includes('err_internet_disconnected') ||
    message.includes('err_network') ||
    message.includes('err_connection') ||
    message.includes('err_name_not_resolved') ||
    message.includes('timeout') ||
    name.includes('networkerror') ||
    (name === 'typeerror' && message.includes('fetch'))
  );
}

export function isCameraPermissionError(error) {
  const name = String(error?.name || '');
  return (
    name === 'NotAllowedError' ||
    name === 'PermissionDeniedError' ||
    name === 'SecurityError'
  );
}

export function isCameraNotFoundError(error) {
  const name = String(error?.name || '');
  return (
    name === 'NotFoundError' ||
    name === 'DevicesNotFoundError' ||
    name === 'OverconstrainedError'
  );
}

/**
 * @returns {'network'|'camera_permission'|'camera_not_found'|'generic'}
 */
export function classifyProctoringError(error) {
  if (isCameraPermissionError(error)) return 'camera_permission';
  if (isCameraNotFoundError(error)) return 'camera_not_found';
  if (isNetworkError(error)) return 'network';
  return 'generic';
}

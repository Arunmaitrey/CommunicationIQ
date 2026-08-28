import { VIOLATION_TYPES } from '../constants';

export function isDocumentFullscreen() {
  return Boolean(
    document.fullscreenElement ||
    document.webkitFullscreenElement ||
    document.mozFullScreenElement ||
    document.msFullscreenElement
  );
}

export function requestFullscreen(element = document.documentElement) {
  const request =
    element.requestFullscreen ||
    element.webkitRequestFullscreen ||
    element.mozRequestFullScreen ||
    element.msRequestFullscreen;

  if (!request) return Promise.resolve();
  return request.call(element).catch(() => {});
}

export function exitFullscreen() {
  const exit =
    document.exitFullscreen ||
    document.webkitExitFullscreen ||
    document.mozCancelFullScreen ||
    document.msExitFullscreen;

  if (!exit || !isDocumentFullscreen()) return Promise.resolve();
  return exit.call(document).catch(() => {});
}

/**
 * @returns {string|null} VIOLATION_TYPES.FULLSCREEN_EXIT if not currently
 *   in fullscreen, else null.
 */
export function checkFullscreenExited() {
  return isDocumentFullscreen() ? null : VIOLATION_TYPES.FULLSCREEN_EXIT;
}

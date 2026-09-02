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

  if (!request) {
    return Promise.resolve();
  }

  try {
    const result = request.call(element);

    if (result && typeof result.catch === 'function') {
      return result.catch(() => {});
    }

    return Promise.resolve();
  } catch (error) {
    return Promise.resolve();
  }
}

export function exitFullscreen() {
  const exit =
    document.exitFullscreen ||
    document.webkitExitFullscreen ||
    document.mozCancelFullScreen ||
    document.msExitFullscreen;

  if (!exit || !isDocumentFullscreen()) {
    return Promise.resolve();
  }

  try {
    const result = exit.call(document);

    if (result && typeof result.catch === 'function') {
      return result.catch(() => {});
    }

    return Promise.resolve();
  } catch (error) {
    return Promise.resolve();
  }
}

/**
 * @returns {string|null} VIOLATION_TYPES.FULLSCREEN_EXIT if not currently
 * in fullscreen, else null.
 */
export function checkFullscreenExited() {
  return isDocumentFullscreen()
    ? null
    : VIOLATION_TYPES.FULLSCREEN_EXIT;
}

/**
 * Subscribes to fullscreen-change events across vendor prefixes.
 */
export function subscribeFullscreenChange(callback) {
  const events = [
    'fullscreenchange',
    'webkitfullscreenchange',
    'mozfullscreenchange',
    'MSFullscreenChange'
  ];

  events.forEach((evt) => {
    document.addEventListener(evt, callback);
  });

  return () => {
    events.forEach((evt) => {
      document.removeEventListener(evt, callback);
    });
  };
}
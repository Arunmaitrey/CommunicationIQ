// Fullscreen utility functions
export const enterFullscreen = () => {
  const element = document.documentElement;
  
  if (element.requestFullscreen) {
    return element.requestFullscreen();
  } else if (element.webkitRequestFullscreen) { /* Safari */
    return element.webkitRequestFullscreen();
  } else if (element.msRequestFullscreen) { /* IE11 */
    return element.msRequestFullscreen();
  } else {
    console.warn('Fullscreen API is not supported');
    return Promise.reject(new Error('Fullscreen API is not supported'));
  }
};

export const exitFullscreen = () => {
  if (document.exitFullscreen) {
    return document.exitFullscreen();
  } else if (document.webkitExitFullscreen) { /* Safari */
    return document.webkitExitFullscreen();
  } else if (document.msExitFullscreen) { /* IE11 */
    return document.msExitFullscreen();
  } else {
    console.warn('Fullscreen exit API is not supported');
    return Promise.reject(new Error('Fullscreen exit API is not supported'));
  }
};

export const isFullscreen = () => {
  return !!(
    document.fullscreenElement ||
    document.webkitFullscreenElement ||
    document.msFullscreenElement
  );
};

export const toggleFullscreen = () => {
  if (isFullscreen()) {
    return exitFullscreen();
  } else {
    return enterFullscreen();
  }
};

export const addFullscreenChangeHandler = (handler) => {
  document.addEventListener('fullscreenchange', handler);
  document.addEventListener('webkitfullscreenchange', handler);
  document.addEventListener('msfullscreenchange', handler);
  
  // Return cleanup function
  return () => {
    document.removeEventListener('fullscreenchange', handler);
    document.removeEventListener('webkitfullscreenchange', handler);
    document.removeEventListener('msfullscreenchange', handler);
  };
};

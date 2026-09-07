import { VIOLATION_TYPES, type ViolationType } from "../constants";

type PrefixedDocument = Document & {
  webkitFullscreenElement?: Element | null;
  mozFullScreenElement?: Element | null;
  msFullscreenElement?: Element | null;
  webkitExitFullscreen?: () => void | Promise<void>;
  mozCancelFullScreen?: () => void | Promise<void>;
  msExitFullscreen?: () => void | Promise<void>;
};

type PrefixedElement = HTMLElement & {
  webkitRequestFullscreen?: () => void | Promise<void>;
  mozRequestFullScreen?: () => void | Promise<void>;
  msRequestFullscreen?: () => void | Promise<void>;
};

export function isDocumentFullscreen(): boolean {
  const doc = document as PrefixedDocument;
  return Boolean(
    document.fullscreenElement ||
    doc.webkitFullscreenElement ||
    doc.mozFullScreenElement ||
    doc.msFullscreenElement,
  );
}

export function requestFullscreen(element: HTMLElement = document.documentElement): Promise<void> {
  const el = element as PrefixedElement;
  const request = el.requestFullscreen || el.webkitRequestFullscreen
    || el.mozRequestFullScreen || el.msRequestFullscreen;

  if (!request) {
    return Promise.resolve();
  }

  try {
    const result = request.call(el);
    if (result && typeof (result as Promise<void>).catch === "function") {
      return (result as Promise<void>).catch(() => {});
    }
    return Promise.resolve();
  } catch {
    return Promise.resolve();
  }
}

export function exitFullscreen(): Promise<void> {
  const doc = document as PrefixedDocument;
  const exit = document.exitFullscreen || doc.webkitExitFullscreen
    || doc.mozCancelFullScreen || doc.msExitFullscreen;

  if (!exit || !isDocumentFullscreen()) {
    return Promise.resolve();
  }

  try {
    const result = exit.call(document);
    if (result && typeof (result as Promise<void>).catch === "function") {
      return (result as Promise<void>).catch(() => {});
    }
    return Promise.resolve();
  } catch {
    return Promise.resolve();
  }
}

export function checkFullscreenExited(): ViolationType | null {
  return isDocumentFullscreen() ? null : VIOLATION_TYPES.FULLSCREEN_EXIT;
}

/** Subscribes to fullscreen-change events across vendor prefixes. */
export function subscribeFullscreenChange(callback: () => void): () => void {
  const events = [
    "fullscreenchange",
    "webkitfullscreenchange",
    "mozfullscreenchange",
    "MSFullscreenChange",
  ];

  events.forEach((evt) => document.addEventListener(evt, callback));

  return () => {
    events.forEach((evt) => document.removeEventListener(evt, callback));
  };
}

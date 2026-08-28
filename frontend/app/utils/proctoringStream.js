let cachedStream = null;
let pendingPromise = null;

export async function getProctoringStream() {
  if (cachedStream) return cachedStream;
  if (pendingPromise) return pendingPromise;

  pendingPromise = navigator.mediaDevices
    .getUserMedia({
      audio: false,
      video: {
        width: { ideal: 1280 },
        height: { ideal: 720 },
      },
    })
    .then((stream) => {
      cachedStream = stream;
      return stream;
    })
    .finally(() => {
      pendingPromise = null;
    });

  return pendingPromise;
}

export function stopProctoringStream() {
  if (cachedStream) {
    cachedStream.getTracks().forEach((t) => t.stop());
  }
  cachedStream = null;
  pendingPromise = null;
}

let cachedStream: MediaStream | null = null;
let pendingPromise: Promise<MediaStream> | null = null;

export async function getProctoringStream(): Promise<MediaStream> {
  if (cachedStream) return cachedStream;
  if (pendingPromise) return pendingPromise;

  pendingPromise = navigator.mediaDevices
    .getUserMedia({
      audio: false,
      video: { width: { ideal: 1280 }, height: { ideal: 720 } },
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

export function stopProctoringStream(): void {
  if (cachedStream) {
    cachedStream.getTracks().forEach((t) => t.stop());
  }
  cachedStream = null;
  pendingPromise = null;
}

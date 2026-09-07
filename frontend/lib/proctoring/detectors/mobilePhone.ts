import { VIOLATION_TYPES, type ViolationType } from "../constants";

/*
  YOLOv8n (COCO classes) runs in-browser via onnxruntime-web, loaded as a
  plain <script> tag from a CDN (like this project already does with
  MediaPipe's model files) instead of an npm import — this avoids the
  bundler trying to transform onnxruntime-web's internal files.

  The CDN script also auto-fetches its own matching .wasm file from the
  same CDN folder — no local wasm assets needed.

  Model file (served from Next.js's public/ dir): frontend/public/models/yolov8n.onnx
*/

const ORT_SCRIPT_URL = "https://cdn.jsdelivr.net/npm/onnxruntime-web@1.20.1/dist/ort.min.js";

const MODEL_URL = "/models/yolov8n.onnx";
const INPUT_SIZE = 640;

// Lower phone threshold helps detect small, cropped, or partly occluded
// phones. Lower values increase sensitivity but can also create false
// positives.
const PHONE_SCORE_THRESHOLD = 0.10;
const PERSON_SCORE_THRESHOLD = 0.3;
const IOU_THRESHOLD = 0.45;

const PERSON_CLASS_ID = 0;
const CELL_PHONE_CLASS_ID = 67;

interface OrtTensor {
  data: Float32Array | Int32Array | number[];
  dims: number[];
}

interface OrtInferenceSession {
  inputNames: string[];
  outputNames: string[];
  run: (feeds: Record<string, OrtTensor>) => Promise<Record<string, OrtTensor>>;
  release?: () => void;
}

interface OrtGlobal {
  env: { wasm: { numThreads: number } };
  InferenceSession: {
    create: (url: string, options: { executionProviders: string[]; graphOptimizationLevel: string }) => Promise<OrtInferenceSession>;
  };
  Tensor: new (type: string, data: Float32Array, dims: number[]) => OrtTensor;
}

declare global {
  interface Window {
    ort?: OrtGlobal;
  }
}

export interface Detection {
  classId: number;
  score: number;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

let ortLoadPromise: Promise<OrtGlobal> | null = null;
let sessionPromise: Promise<OrtInferenceSession> | null = null;
let scratchCanvas: HTMLCanvasElement | null = null;

/** Injects the onnxruntime-web <script> tag once and resolves with window.ort. */
function loadOrtGlobal(): Promise<OrtGlobal> {
  if (window.ort) {
    return Promise.resolve(window.ort);
  }

  if (!ortLoadPromise) {
    ortLoadPromise = new Promise<OrtGlobal>((resolve, reject) => {
      const script = document.createElement("script");
      script.src = ORT_SCRIPT_URL;
      script.async = true;
      script.onload = () => resolve(window.ort as OrtGlobal);
      script.onerror = () => reject(new Error("Failed to load onnxruntime-web from CDN"));
      document.head.appendChild(script);
    }).catch((error) => {
      ortLoadPromise = null; // allow retry
      throw error;
    });
  }

  return ortLoadPromise;
}

export function loadPhoneDetector(): Promise<OrtInferenceSession> {
  if (!sessionPromise) {
    sessionPromise = loadOrtGlobal()
      .then((ort) => {
        ort.env.wasm.numThreads = 1; // simplest, most compatible config
        return ort.InferenceSession.create(MODEL_URL, {
          executionProviders: ["wasm"],
          graphOptimizationLevel: "all",
        });
      })
      .catch((error) => {
        sessionPromise = null; // allow retry on next call
        throw error;
      });
  }
  return sessionPromise;
}

export function releasePhoneDetector(session: OrtInferenceSession | null | undefined): void {
  try {
    session?.release?.();
  } catch (error) {
    console.warn("YOLO session cleanup error:", error);
  }

  sessionPromise = null;
}

function letterboxFrame(video: HTMLVideoElement): ImageData {
  if (!scratchCanvas) {
    scratchCanvas = document.createElement("canvas");
    scratchCanvas.width = INPUT_SIZE;
    scratchCanvas.height = INPUT_SIZE;
  }

  const ctx = scratchCanvas.getContext("2d")!;
  const vw = video.videoWidth;
  const vh = video.videoHeight;
  const scale = Math.min(INPUT_SIZE / vw, INPUT_SIZE / vh);
  const nw = Math.round(vw * scale);
  const nh = Math.round(vh * scale);
  const dx = Math.floor((INPUT_SIZE - nw) / 2);
  const dy = Math.floor((INPUT_SIZE - nh) / 2);

  ctx.fillStyle = "#727272";
  ctx.fillRect(0, 0, INPUT_SIZE, INPUT_SIZE);
  ctx.drawImage(video, 0, 0, vw, vh, dx, dy, nw, nh);

  return ctx.getImageData(0, 0, INPUT_SIZE, INPUT_SIZE);
}

function toInputTensor(imageData: ImageData): OrtTensor {
  const { data } = imageData;
  const area = INPUT_SIZE * INPUT_SIZE;
  const chw = new Float32Array(3 * area);

  for (let i = 0; i < area; i++) {
    chw[i] = data[i * 4] / 255;
    chw[area + i] = data[i * 4 + 1] / 255;
    chw[2 * area + i] = data[i * 4 + 2] / 255;
  }

  return new window.ort!.Tensor("float32", chw, [1, 3, INPUT_SIZE, INPUT_SIZE]);
}

function boxIou(a: Detection, b: Detection): number {
  const x1 = Math.max(a.x1, b.x1);
  const y1 = Math.max(a.y1, b.y1);
  const x2 = Math.min(a.x2, b.x2);
  const y2 = Math.min(a.y2, b.y2);

  const intersection = Math.max(0, x2 - x1) * Math.max(0, y2 - y1);
  const areaA = Math.max(0, a.x2 - a.x1) * Math.max(0, a.y2 - a.y1);
  const areaB = Math.max(0, b.x2 - b.x1) * Math.max(0, b.y2 - b.y1);
  const union = areaA + areaB - intersection;

  return union > 0 ? intersection / union : 0;
}

function nonMaxSuppression(boxes: Detection[]): Detection[] {
  boxes.sort((a, b) => b.score - a.score);

  const kept: Detection[] = [];

  for (const box of boxes) {
    const overlaps = kept.some(
      (keptBox) => keptBox.classId === box.classId && boxIou(keptBox, box) >= IOU_THRESHOLD,
    );

    if (!overlaps) {
      kept.push(box);
    }
  }

  return kept;
}

function parseDetections(output: OrtTensor): Detection[] {
  const data = output.data;
  const [, numAttrs, numAnchors] = output.dims;

  if (numAttrs < 84) {
    console.error("Unexpected YOLO output shape:", output.dims);
    return [];
  }

  const boxes: Detection[] = [];

  for (let i = 0; i < numAnchors; i++) {
    const personScore = data[(4 + PERSON_CLASS_ID) * numAnchors + i];
    const phoneScore = data[(4 + CELL_PHONE_CLASS_ID) * numAnchors + i];

    let classId: number | null = null;
    let score = 0;

    if (phoneScore >= PHONE_SCORE_THRESHOLD) {
      classId = CELL_PHONE_CLASS_ID;
      score = phoneScore;
    } else if (personScore >= PERSON_SCORE_THRESHOLD) {
      classId = PERSON_CLASS_ID;
      score = personScore;
    } else {
      continue;
    }

    const cx = data[i];
    const cy = data[numAnchors + i];
    const width = data[2 * numAnchors + i];
    const height = data[3 * numAnchors + i];

    boxes.push({
      classId,
      score,
      x1: Math.max(0, cx - width / 2),
      y1: Math.max(0, cy - height / 2),
      x2: Math.min(INPUT_SIZE, cx + width / 2),
      y2: Math.min(INPUT_SIZE, cy + height / 2),
    });
  }

  return nonMaxSuppression(boxes);
}

export async function runObjectDetection(
  session: OrtInferenceSession | null | undefined,
  video: HTMLVideoElement | null | undefined,
): Promise<Detection[] | null> {
  if (!session || !video || video.readyState < 2 || video.videoWidth === 0) {
    return null;
  }

  try {
    const imageData = letterboxFrame(video);
    const tensor = toInputTensor(imageData);
    const feeds = { [session.inputNames[0]]: tensor };
    const results = await session.run(feeds);
    const output = results[session.outputNames[0]];

    return parseDetections(output);
  } catch (error) {
    console.error("YOLO inference error:", error);
    return null;
  }
}

export function checkMobilePhone(detections: Detection[] | null | undefined): ViolationType | null {
  const hasPhone = (detections || []).some((d) => d.classId === CELL_PHONE_CLASS_ID);
  return hasPhone ? VIOLATION_TYPES.MOBILE_PHONE : null;
}

export function countPersons(detections: Detection[] | null | undefined): number {
  return (detections || []).filter((d) => d.classId === PERSON_CLASS_ID).length;
}

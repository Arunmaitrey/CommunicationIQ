import { VIOLATION_TYPES } from '../constants';

const ORT_SCRIPT_URL =
  'https://cdn.jsdelivr.net/npm/onnxruntime-web@1.20.1/dist/ort.min.js';

const MODEL_URL = '/models/yolov8n.onnx';
const INPUT_SIZE = 640;

const PHONE_SCORE_THRESHOLD = 0.10;
const PERSON_SCORE_THRESHOLD = 0.3;
const IOU_THRESHOLD = 0.45;

const PERSON_CLASS_ID = 0;
const CELL_PHONE_CLASS_ID = 67;

let ortLoadPromise = null;
let sessionPromise = null;
let scratchCanvas = null;

function loadOrtGlobal() {
  if (window.ort) {
    return Promise.resolve(window.ort);
  }

  if (!ortLoadPromise) {
    ortLoadPromise = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = ORT_SCRIPT_URL;
      script.async = true;
      script.onload = () => resolve(window.ort);
      script.onerror = () =>
        reject(new Error('Failed to load onnxruntime-web from CDN'));
      document.head.appendChild(script);
    }).catch((error) => {
      ortLoadPromise = null;
      throw error;
    });
  }

  return ortLoadPromise;
}

export function loadPhoneDetector() {
  if (!sessionPromise) {
    sessionPromise = loadOrtGlobal()
      .then((ort) => {
        ort.env.wasm.numThreads = 1;
        return ort.InferenceSession.create(MODEL_URL, {
          executionProviders: ['wasm'],
          graphOptimizationLevel: 'all',
        });
      })
      .catch((error) => {
        sessionPromise = null;
        throw error;
      });
  }
  return sessionPromise;
}

export function releasePhoneDetector(session) {
  try {
    session?.release?.();
  } catch (error) {
    console.warn('YOLO session cleanup error:', error);
  }

  sessionPromise = null;
}

function letterboxFrame(video) {
  if (!scratchCanvas) {
    scratchCanvas = document.createElement('canvas');
    scratchCanvas.width = INPUT_SIZE;
    scratchCanvas.height = INPUT_SIZE;
  }

  const ctx = scratchCanvas.getContext('2d');
  const vw = video.videoWidth;
  const vh = video.videoHeight;
  const scale = Math.min(INPUT_SIZE / vw, INPUT_SIZE / vh);
  const nw = Math.round(vw * scale);
  const nh = Math.round(vh * scale);
  const dx = Math.floor((INPUT_SIZE - nw) / 2);
  const dy = Math.floor((INPUT_SIZE - nh) / 2);

  ctx.fillStyle = '#727272';
  ctx.fillRect(0, 0, INPUT_SIZE, INPUT_SIZE);
  ctx.drawImage(video, 0, 0, vw, vh, dx, dy, nw, nh);

  return ctx.getImageData(0, 0, INPUT_SIZE, INPUT_SIZE);
}

function toInputTensor(imageData) {
  const { data } = imageData;
  const area = INPUT_SIZE * INPUT_SIZE;
  const chw = new Float32Array(3 * area);

  for (let i = 0; i < area; i++) {
    chw[i] = data[i * 4] / 255;
    chw[area + i] = data[i * 4 + 1] / 255;
    chw[2 * area + i] = data[i * 4 + 2] / 255;
  }

  return new window.ort.Tensor('float32', chw, [1, 3, INPUT_SIZE, INPUT_SIZE]);
}

function boxIou(a, b) {
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

function nonMaxSuppression(boxes) {
  boxes.sort((a, b) => b.score - a.score);

  const kept = [];

  for (const box of boxes) {
    const overlaps = kept.some(
      (keptBox) =>
        keptBox.classId === box.classId &&
        boxIou(keptBox, box) >= IOU_THRESHOLD,
    );

    if (!overlaps) {
      kept.push(box);
    }
  }

  return kept;
}

function parseDetections(output) {
  const data = output.data;
  const [, numAttrs, numAnchors] = output.dims;

  if (numAttrs < 84) {
    console.error('Unexpected YOLO output shape:', output.dims);
    return [];
  }

  const boxes = [];

  for (let i = 0; i < numAnchors; i++) {
    const personScore = data[(4 + PERSON_CLASS_ID) * numAnchors + i];
    const phoneScore = data[(4 + CELL_PHONE_CLASS_ID) * numAnchors + i];

    let classId = null;
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

export async function runObjectDetection(session, video) {
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
    console.error('YOLO inference error:', error);
    return null;
  }
}

export function checkMobilePhone(detections) {
  const hasPhone = (detections || []).some(
    (d) => d.classId === CELL_PHONE_CLASS_ID,
  );

  return hasPhone ? VIOLATION_TYPES.MOBILE_PHONE : null;
}

export function countPersons(detections) {
  return (detections || []).filter(
    (d) => d.classId === PERSON_CLASS_ID,
  ).length;
}
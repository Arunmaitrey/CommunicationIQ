import React, { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import {
  FaceDetector,
  FaceLandmarker,
  FilesetResolver
} from '@mediapipe/tasks-vision';

import {
  getProctoringStream,
  stopProctoringStream
} from '../utils/proctoringStream';

import {
  getConfirmDuration,
  MAX_VIOLATIONS,
  DETECTION_INTERVAL_MS,
  VIOLATION_COPY,
  VIOLATION_TYPES
} from './constants';
import { readPersistedState, writePersistedState, clearPersistedState } from './storage';
import { checkFaceNotDetected } from './detectors/faceNotDetected';
import { checkMultipleFaces } from './detectors/multipleFaces';
import { checkLookingAway, createLookingAwayTracker } from './detectors/lookingAway';
import {
  isDocumentFullscreen,
  requestFullscreen,
  exitFullscreen,
  checkFullscreenExited
} from './detectors/fullscreenExit';
import ViolationToast from './ViolationToast';

/**
 * ProctorCamera — AI interview proctoring component.
 *
 * Props:
 * - sessionId: string|number — the interview session id
 * - enabled: boolean — whether proctoring should be active
 * - onViolation: ({ type, count, timestamp }) => void — called on each confirmed violation
 * - onAutoEnd: ({ reason, violationType, count, timestamp }) => void — called when max violations reached
 * - examCompleted: boolean — set true when interview finishes normally
 */
const ProctorCamera = ({
  sessionId,
  enabled = true,
  onViolation,
  onAutoEnd,
  examCompleted = false,
  inline = false
}) => {
  const faceDetectorRef = useRef(null);
  const faceLandmarkerRef = useRef(null);
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const animationFrameRef = useRef(null);
  const lastDetectionTimeRef = useRef(0);

  const activeViolationRef = useRef(null);
  const lookingAwayTrackerRef = useRef(null);
  if (!lookingAwayTrackerRef.current) {
    lookingAwayTrackerRef.current = createLookingAwayTracker();
  }

  const persistedOnMount = readPersistedState(sessionId);

  const [faceStatus, setFaceStatus] = useState('Initializing...');
  const [currentToast, setCurrentToast] = useState(null);
  const [proctoringBlocked, setProctoringBlocked] = useState(false);
  const [isLocked, setIsLocked] = useState(() => persistedOnMount?.locked ?? false);
  const [violationCount, setViolationCount] = useState(
    () => persistedOnMount?.violationCount ?? 0
  );
  const [fullscreenReady, setFullscreenReady] = useState(() => isDocumentFullscreen());

  const fullscreenTimerRef = useRef(null);
  const violationCountRef = useRef(persistedOnMount?.violationCount ?? 0);
  const faceEvalRef = useRef({ face_detected: false, away_events: 0, multi_face_events: 0, violation_count: 0 });
  const tabViolationCountRef = useRef(0);

  const shouldProctor = enabled && !!sessionId;

  // ==================================================
  // TEARDOWN
  // ==================================================
  const teardown = useCallback(() => {
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }

    lookingAwayTrackerRef.current?.reset();

    if (fullscreenTimerRef.current) {
      clearTimeout(fullscreenTimerRef.current);
      fullscreenTimerRef.current = null;
    }

    if (videoRef.current) {
      videoRef.current.pause();
      videoRef.current.srcObject = null;
    }

    stopProctoringStream();
    streamRef.current = null;

    if (faceDetectorRef.current) {
      try { faceDetectorRef.current.close(); } catch { /* ignore */ }
      faceDetectorRef.current = null;
    }

    if (faceLandmarkerRef.current) {
      try { faceLandmarkerRef.current.close(); } catch { /* ignore */ }
      faceLandmarkerRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (isLocked || examCompleted) {
      teardown();
      setFaceStatus(isLocked ? 'Camera stopped (exam locked)' : 'Camera stopped');
    }
  }, [isLocked, examCompleted, teardown]);

  const sendFaceEvaluation = useCallback(async () => {
    if (!sessionId || typeof window === 'undefined') return
    const payload = {
      face_detected: faceEvalRef.current.face_detected,
      away_events: faceEvalRef.current.away_events,
      multi_face_events: faceEvalRef.current.multi_face_events,
      violation_count: faceEvalRef.current.violation_count,
    }
    try {
      await fetch(`/api/interview/${sessionId}/face-evaluation`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
    } catch { /* best-effort */ }
  }, [sessionId]);

  useEffect(() => {
    if (examCompleted && sessionId) {
      sendFaceEvaluation()
    }
  }, [examCompleted, sessionId, sendFaceEvaluation])

  useEffect(() => {
    return () => {
      if (sessionId && !examCompleted) {
        sendFaceEvaluation()
      }
    }
  }, [sessionId, examCompleted, sendFaceEvaluation])

  // ==================================================
  // 1. INITIALIZE MEDIAPIPE
  // ==================================================
  useEffect(() => {
    if (!shouldProctor || isLocked || examCompleted || !fullscreenReady) return;

    let cancelled = false;

    const init = async () => {
      try {
        setFaceStatus('Loading proctoring...');

        const vision = await FilesetResolver.forVisionTasks(
          'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@1.0.1/wasm'
        );
        if (cancelled) return;

        const detector = await FaceDetector.createFromOptions(vision, {
          baseOptions: {
            modelAssetPath:
              'https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite',
            delegate: 'CPU'
          },
          runningMode: 'VIDEO',
          minDetectionConfidence: 0.5,
          minSuppressionThreshold: 0.3
        });
        if (cancelled) { detector.close(); return; }
        faceDetectorRef.current = detector;

        const landmarker = await FaceLandmarker.createFromOptions(vision, {
          baseOptions: {
            modelAssetPath:
              'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task',
            delegate: 'CPU'
          },
          runningMode: 'VIDEO',
          numFaces: 1,
          minFaceDetectionConfidence: 0.5,
          minFacePresenceConfidence: 0.5,
          minTrackingConfidence: 0.5,
          outputFaceBlendshapes: false,
          outputFacialTransformationMatrixes: false
        });
        if (cancelled) { detector.close(); landmarker.close(); return; }
        faceLandmarkerRef.current = landmarker;

        setFaceStatus('Face detector ready');
      } catch (err) {
        console.error('MediaPipe init failed:', err);
        setFaceStatus('Proctoring init failed');
        setProctoringBlocked(true);
      }
    };

    init();
    return () => { cancelled = true; };
  }, [shouldProctor, isLocked, examCompleted, fullscreenReady]);

  // ==================================================
  // 2. CAMERA
  // ==================================================
  useEffect(() => {
    if (!shouldProctor || isLocked || examCompleted || !fullscreenReady) return;

    let cancelled = false;

    const start = async () => {
      try {
        setFaceStatus('Starting camera...');
        const stream = await getProctoringStream();
        if (cancelled) return;
        streamRef.current = stream;

        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play().catch(() => {});
        }
        setFaceStatus('Waiting for face...');
      } catch {
        setFaceStatus('Camera unavailable');
        setProctoringBlocked(true);
      }
    };

    start();
    return () => { cancelled = true; };
  }, [shouldProctor, isLocked, examCompleted, fullscreenReady]);

  // ==================================================
  // 3. VIOLATION CONFIRMATION
  // ==================================================
  const confirmViolation = useCallback((type) => {
    const timestamp = Date.now();
    const nextCount = violationCountRef.current + 1;
    violationCountRef.current = nextCount;
    const isFinal = nextCount > MAX_VIOLATIONS;

    setViolationCount(nextCount);

    faceEvalRef.current.violation_count = nextCount
    if (type === VIOLATION_TYPES.LOOKING_AWAY) {
      faceEvalRef.current.away_events = (faceEvalRef.current.away_events || 0) + 1
    }
    if (type === VIOLATION_TYPES.MULTIPLE_FACES) {
      faceEvalRef.current.multi_face_events = (faceEvalRef.current.multi_face_events || 0) + 1
    }

    writePersistedState(sessionId, {
      locked: isFinal,
      violationCount: nextCount,
      lastViolationType: type,
      lastViolationAt: timestamp
    });

    onViolation?.({ type, count: nextCount, timestamp });

    setCurrentToast({ type, count: nextCount, isFinal, timestamp });

    if (isFinal) {
      setIsLocked(true);
      onAutoEnd?.({
        reason: 'proctoring_violation_limit_reached',
        violationType: type,
        count: nextCount,
        timestamp
      });
    }
  }, [sessionId, onViolation, onAutoEnd]);

  const trackViolation = useCallback((type, now) => {
    const active = activeViolationRef.current;

    if (!active || active.type !== type) {
      activeViolationRef.current = { type, since: now, confirmed: false };
      setFaceStatus(`Checking (${VIOLATION_COPY[type]?.title || type})...`);
      return;
    }

    if (active.confirmed) return;

    if (now - active.since >= getConfirmDuration(type)) {
      activeViolationRef.current = { ...active, confirmed: true };
      confirmViolation(type);
    } else {
      setFaceStatus(`Checking (${VIOLATION_COPY[type]?.title || type})...`);
    }
  }, [confirmViolation]);

  const clearActiveViolation = () => {
    activeViolationRef.current = null;
  };

  // ==================================================
  // 4. CONTINUOUS PROCTORING LOOP
  // ==================================================
  useEffect(() => {
    if (!shouldProctor || isLocked || examCompleted || proctoringBlocked) return;

    let cancelled = false;

    const detect = () => {
      if (cancelled) return;

      const video = videoRef.current;
      const detector = faceDetectorRef.current;
      const landmarker = faceLandmarkerRef.current;

      if (!video || !detector || !landmarker || video.readyState < 2 || video.videoWidth === 0) {
        animationFrameRef.current = requestAnimationFrame(detect);
        return;
      }

      const now = performance.now();

      if (now - lastDetectionTimeRef.current >= DETECTION_INTERVAL_MS) {
        lastDetectionTimeRef.current = now;

        try {
          const detectorResult = detector.detectForVideo(video, now);
          const detections = detectorResult?.detections || [];

          const noFace = checkFaceNotDetected(detections);
          const multiFace = checkMultipleFaces(detections);

          if (noFace) {
            trackViolation(noFace, now);
          } else if (multiFace) {
            faceEvalRef.current.face_detected = true
            trackViolation(multiFace, now);
          } else {
            faceEvalRef.current.face_detected = true
            const landmarkResult = landmarker.detectForVideo(video, now);
            const faceLandmarks = landmarkResult?.faceLandmarks?.[0];

            if (!faceLandmarks) {
              clearActiveViolation();
              lookingAwayTrackerRef.current.reset();
              setFaceStatus('Face detected');
            } else {
              const lookingAway = lookingAwayTrackerRef.current.check(faceLandmarks);
              if (lookingAway) {
                trackViolation(lookingAway, now);
              } else {
                clearActiveViolation();
                setFaceStatus('Face detected');
              }
            }
          }
        } catch { /* detection error — ignore single frame */ }
      }

      animationFrameRef.current = requestAnimationFrame(detect);
    };

    animationFrameRef.current = requestAnimationFrame(detect);

    return () => {
      cancelled = true;
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
        animationFrameRef.current = null;
      }
    };
  }, [shouldProctor, isLocked, examCompleted, proctoringBlocked, trackViolation]);

  // ==================================================
  // 4b. FULLSCREEN EXIT DETECTION
  // ==================================================
  useEffect(() => {
    if (!shouldProctor || isLocked || examCompleted || proctoringBlocked || !fullscreenReady) return;

    const handleFullscreenChange = () => {
      const violation = checkFullscreenExited();
      if (violation) {
        if (!fullscreenTimerRef.current) {
          setFaceStatus(`Checking (${VIOLATION_COPY[violation]?.title})...`);
          fullscreenTimerRef.current = setTimeout(() => {
            fullscreenTimerRef.current = null;
            confirmViolation(violation);
          }, getConfirmDuration(violation));
        }
      } else if (fullscreenTimerRef.current) {
        clearTimeout(fullscreenTimerRef.current);
        fullscreenTimerRef.current = null;
        setFaceStatus('Face detected');
      }
    };

    const events = ['fullscreenchange', 'webkitfullscreenchange', 'mozfullscreenchange'];
    events.forEach((evt) => document.addEventListener(evt, handleFullscreenChange));

    return () => {
      events.forEach((evt) => document.removeEventListener(evt, handleFullscreenChange));
      if (fullscreenTimerRef.current) {
        clearTimeout(fullscreenTimerRef.current);
        fullscreenTimerRef.current = null;
      }
    };
  }, [shouldProctor, isLocked, examCompleted, proctoringBlocked, fullscreenReady, confirmViolation]);

  // ==================================================
  // 4c. TAB SWITCHING DETECTION
  // ==================================================
  useEffect(() => {
    if (!shouldProctor || isLocked || examCompleted || proctoringBlocked) return;

    const handleVisibilityChange = () => {
      if (document.hidden) {
        confirmViolation(VIOLATION_TYPES.TAB_SWITCH);
        setTimeout(() => {
          window.focus();
        }, 100);
      }
    };

    const handleBlur = () => {
      confirmViolation(VIOLATION_TYPES.TAB_SWITCH);
      setTimeout(() => {
        window.focus();
      }, 100);
    };

    const handleKeyDown = (e) => {
      if (
        (e.ctrlKey && e.key === 'Tab') ||
        (e.ctrlKey && e.key === 'w') ||
        (e.altKey && e.key === 'Tab') ||
        e.key === 'F11' ||
        (e.metaKey && e.key === 'Tab')
      ) {
        e.preventDefault();
        confirmViolation(VIOLATION_TYPES.TAB_SWITCH);
        return false;
      }
    };

    const handleContextMenu = (e) => {
      e.preventDefault();
      return false;
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('blur', handleBlur);
    document.addEventListener('keydown', handleKeyDown);
    document.addEventListener('contextmenu', handleContextMenu);

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('blur', handleBlur);
      document.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('contextmenu', handleContextMenu);
    };
  }, [shouldProctor, isLocked, examCompleted, proctoringBlocked, confirmViolation]);

  // Unmount cleanup
  useEffect(() => {
    return () => { teardown(); };
  }, [teardown]);

  // ==================================================
  // 5. UI
  // ==================================================

  if (!shouldProctor) return null;
  if (examCompleted) return null;

  if (!fullscreenReady && !isLocked) {
    return (
      <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60">
        <div className="w-[90%] max-w-md rounded-2xl bg-white dark:bg-slate-900 border border-gray-200 dark:border-slate-700 p-6 shadow-2xl text-center">
          <div className="w-16 h-16 rounded-full bg-teal-100 dark:bg-teal-900/50 flex items-center justify-center mx-auto mb-4">
            <svg className="w-8 h-8 text-teal-600 dark:text-teal-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
            </svg>
          </div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Fullscreen Required</h2>
          <p className="mt-3 text-sm text-gray-600 dark:text-slate-400">
            This interview must be taken in fullscreen mode with proctoring active.
            Click below to enter fullscreen and start.
          </p>
          <button
            type="button"
            onClick={async () => {
              await requestFullscreen();
              setFullscreenReady(isDocumentFullscreen());
            }}
            className="mt-4 px-5 py-2.5 text-sm font-semibold rounded-xl bg-teal-600 text-white hover:bg-teal-700 transition-colors cursor-pointer"
          >
            Enter Fullscreen & Start
          </button>
        </div>
      </div>
    );
  }

  if (proctoringBlocked) {
    return (
      <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60">
        <div className="w-[90%] max-w-md rounded-2xl bg-white dark:bg-slate-900 border border-gray-200 dark:border-slate-700 p-6 shadow-2xl text-center">
          <div className="w-16 h-16 rounded-full bg-red-100 dark:bg-red-900/50 flex items-center justify-center mx-auto mb-4">
            <svg className="w-8 h-8 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
            </svg>
          </div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Proctoring Unavailable</h2>
          <p className="mt-3 text-sm text-gray-600 dark:text-slate-400">
            Camera access or proctoring system failed. This interview cannot continue
            without proctoring. Please allow camera access and reload.
          </p>
        </div>
      </div>
    );
  }

  if (isLocked) {
    return (
      <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70">
        <div className="w-[90%] max-w-md rounded-2xl bg-white dark:bg-slate-900 border border-gray-200 dark:border-slate-700 p-6 shadow-2xl text-center">
          <div className="w-16 h-16 rounded-full bg-red-100 dark:bg-red-900/50 flex items-center justify-center mx-auto mb-4">
            <svg className="w-8 h-8 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4.5c-.77-.833-2.694-.833-3.464 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z" />
            </svg>
          </div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Interview Locked</h2>
          <p className="mt-3 text-sm text-gray-600 dark:text-slate-400">
            Your interview was automatically submitted after repeated proctoring violations.
            Contact an administrator if you believe this was a mistake.
          </p>
        </div>
      </div>
    );
  }

  return (
    <>
      {!inline && (
        <div className="fixed bottom-4 right-4 z-50">
          <div className="bg-white dark:bg-slate-900 border border-gray-200 dark:border-slate-700 rounded-xl shadow-lg overflow-hidden">
            <video
              ref={videoRef}
              autoPlay
              muted
              playsInline
              className="w-40 h-28 object-cover bg-black rounded-t-xl"
            />
            <div className="px-2 py-1.5 text-[10px] text-gray-500 dark:text-slate-400 flex justify-between gap-2 bg-white dark:bg-slate-900">
              <span className="truncate">{faceStatus}</span>
              <span className="shrink-0 font-mono">{violationCount}/{MAX_VIOLATIONS}</span>
            </div>
          </div>
        </div>
      )}

      {inline && (
        <div className="rounded-2xl border border-slate-700 bg-slate-900 overflow-hidden">
          <div className="relative aspect-video bg-black">
            <video
              ref={videoRef}
              autoPlay
              muted
              playsInline
              className="w-full h-full object-cover"
            />
            {!isDocumentFullscreen() && (
              <div className="absolute inset-0 flex items-center justify-center bg-black/60">
                <button
                  type="button"
                  onClick={async () => {
                    await requestFullscreen();
                    setFullscreenReady(isDocumentFullscreen());
                  }}
                  className="px-5 py-2.5 text-sm font-semibold rounded-xl bg-teal-600 text-white hover:bg-teal-700 transition-colors cursor-pointer"
                >
                  Enter Fullscreen
                </button>
              </div>
            )}
          </div>
          <div className="px-3 py-2 text-xs text-slate-400 flex justify-between gap-2 bg-slate-900">
            <span className="truncate">{faceStatus}</span>
            <span className="shrink-0 font-mono">{violationCount}/{MAX_VIOLATIONS}</span>
          </div>
        </div>
      )}

      {/* Violation Toast */}
      <ViolationToast
        violation={currentToast}
        onDismiss={() => setCurrentToast(null)}
        onReenterFullscreen={async () => {
          await requestFullscreen();
          setFullscreenReady(isDocumentFullscreen());
        }}
      />
    </>
  );
};

export default ProctorCamera;

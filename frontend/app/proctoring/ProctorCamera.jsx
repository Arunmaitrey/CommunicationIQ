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
  exitFullscreen
} from './detectors/fullscreenExit';
import {
  loadPhoneDetector,
  releasePhoneDetector,
  runObjectDetection,
  checkMobilePhone,
  countPersons
} from './detectors/mobilePhone';
import ViolationToast from './ViolationToast';
import { API_BASE, getToken } from '@/lib/api';

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

  const phoneSessionRef = useRef(null);
  const phoneCheckInFlightRef = useRef(false);
  const activePhoneViolationRef = useRef(null);

  // Person-body count from the same YOLO pass used for phone detection.
  // Fed into checkMultipleFaces() as a fallback for a second person whose
  // face isn't frontal (turned away / side-on), which MediaPipe's
  // face-only detector can't see on its own. Defaults to 1 until the
  // first object-detection pass completes.
  const personCountRef = useRef(1);

  const pendingAutoEndRef = useRef(null);

  const persistedOnMount = readPersistedState(sessionId);

  const [faceStatus, setFaceStatus] = useState('Initializing...');
  const [currentToast, setCurrentToast] = useState(null);
  const [proctoringBlocked, setProctoringBlocked] = useState(false);
  const [isLocked, setIsLocked] = useState(() => persistedOnMount?.locked ?? false);
  const [violationCount, setViolationCount] = useState(
    () => persistedOnMount?.violationCount ?? 0
  );
  const [fullscreenReady, setFullscreenReady] = useState(() => isDocumentFullscreen());
  // Tracks whether onAutoEnd already fired for the final violation this
  // render cycle, so the fallback lock screen (with its own "Continue to
  // Results" button) doesn't render a second time while the parent is
  // still navigating away — see the isLocked render block below.
  const [autoEndFired, setAutoEndFired] = useState(false);

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
      videoRef.current.onloadedmetadata = null;
      videoRef.current.pause();
      videoRef.current.srcObject = null;
    }

    streamRef.current?.getTracks().forEach((track) => {
      try { track.stop(); } catch { /* ignore */ }
    });

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

    if (phoneSessionRef.current) {
      releasePhoneDetector(phoneSessionRef.current);
      phoneSessionRef.current = null;
    }
    phoneCheckInFlightRef.current = false;
    activePhoneViolationRef.current = null;
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
      const token = getToken();
      await fetch(`${API_BASE}/student/attempts/${sessionId}/proctor-events`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
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

        const phoneSession = await loadPhoneDetector();
        if (cancelled) {
          detector.close();
          landmarker.close();
          releasePhoneDetector(phoneSession);
          return;
        }
        phoneSessionRef.current = phoneSession;

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

        const videoTracks = stream.getVideoTracks();
        if (!videoTracks.length || videoTracks[0].readyState !== 'live') {
          console.error('[ProctorCamera] stream has no live video track', videoTracks);
          setFaceStatus('Camera unavailable');
          setProctoringBlocked(true);
          return;
        }

        streamRef.current = stream;

        const video = videoRef.current;
        if (video) {
          video.srcObject = stream;

          const tryPlay = () => {
            video.play().catch((err) => {
              console.error('[ProctorCamera] video.play() failed:', err);
            });
          };

          video.onloadedmetadata = tryPlay;
          tryPlay();
        }
        setFaceStatus('Waiting for face...');
      } catch (err) {
        console.error('[ProctorCamera] camera start failed:', err);
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
      // Release the camera hardware immediately rather than waiting for
      // the isLocked-driven effect — on a backgrounded tab (exactly the
      // case when the user has switched to another app), React can delay
      // that effect, leaving the camera indicator on longer than it
      // should be. teardown() is idempotent (safe to call again from the
      // effect right after).
      teardown();
      setIsLocked(true);
      pendingAutoEndRef.current = {
        reason: 'proctoring_violation_limit_reached',
        violationType: type,
        count: nextCount,
        timestamp
      };
    }
  }, [sessionId, onViolation, onAutoEnd, teardown]);

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

  const trackPhoneViolation = useCallback((now) => {
    const type = VIOLATION_TYPES.MOBILE_PHONE;
    const active = activePhoneViolationRef.current;

    if (!active) {
      activePhoneViolationRef.current = { since: now, confirmed: false };
      setFaceStatus(`Checking (${VIOLATION_COPY[type]?.title || 'Phone detected'})...`);
      return;
    }

    if (active.confirmed) return;

    if (now - active.since >= getConfirmDuration(type)) {
      activePhoneViolationRef.current = { ...active, confirmed: true };
      confirmViolation(type);
    } else {
      setFaceStatus(`Checking (${VIOLATION_COPY[type]?.title || 'Phone detected'})...`);
    }
  }, [confirmViolation]);

  const clearPhoneViolation = () => {
    activePhoneViolationRef.current = null;
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

        // Phone + person-body detection: async YOLO inference, run
        // independently of the synchronous face checks below. Guarded so
        // a slow inference call can't stack up multiple overlapping runs.
        // The same detection pass feeds both checkMobilePhone() and the
        // personCountRef used by checkMultipleFaces() below.
        if (phoneSessionRef.current && !phoneCheckInFlightRef.current) {
          phoneCheckInFlightRef.current = true;
          runObjectDetection(phoneSessionRef.current, video)
            .then((objDetections) => {
              const phoneViolation = checkMobilePhone(objDetections);
              if (phoneViolation) {
                trackPhoneViolation(performance.now());
              } else {
                clearPhoneViolation();
              }

              personCountRef.current = countPersons(objDetections) || 1;
            })
            .catch((err) => {
              console.error('[ProctorCamera] phone detection error:', err);
            })
            .finally(() => {
              phoneCheckInFlightRef.current = false;
            });
        }

        try {
          const detectorResult = detector.detectForVideo(video, now);
          const detections = detectorResult?.detections || [];

          const noFace = checkFaceNotDetected(detections);
          const multiFace = checkMultipleFaces(detections, personCountRef.current);

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
  }, [shouldProctor, isLocked, examCompleted, proctoringBlocked, trackViolation, trackPhoneViolation]);

  // ==================================================
  // 4b. FULLSCREEN EXIT DETECTION
  // ==================================================
  useEffect(() => {
    if (!shouldProctor || isLocked || examCompleted || proctoringBlocked || !fullscreenReady) return;

    const handleFullscreenChange = () => {
      const stillFullscreen = isDocumentFullscreen();

      if (!stillFullscreen) {
        if (!fullscreenTimerRef.current) {
          setFaceStatus(`Checking (${VIOLATION_COPY[VIOLATION_TYPES.FULLSCREEN_EXIT]?.title || 'Fullscreen exited'})...`);
          fullscreenTimerRef.current = setTimeout(() => {
            fullscreenTimerRef.current = null;
            confirmViolation(VIOLATION_TYPES.FULLSCREEN_EXIT);
          }, getConfirmDuration(VIOLATION_TYPES.FULLSCREEN_EXIT));
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

  useEffect(() => {
    return () => { teardown(); };
  }, [teardown]);

  useEffect(() => {
    const handlePageHide = () => teardown();
    window.addEventListener('pagehide', handlePageHide);
    window.addEventListener('beforeunload', handlePageHide);
    return () => {
      window.removeEventListener('pagehide', handlePageHide);
      window.removeEventListener('beforeunload', handlePageHide);
    };
  }, [teardown]);

  const statusTone = useCallback(() => {
    if (faceStatus === 'Face detected') return 'ok';
    if (faceStatus.startsWith('Checking') || faceStatus === 'Waiting for face...') return 'warn';
    if (faceStatus === 'Camera unavailable' || faceStatus.startsWith('Camera stopped') || faceStatus === 'Proctoring init failed') return 'error';
    return 'neutral';
  }, [faceStatus]);
  const tone = statusTone();
  const toneDot = { ok: 'bg-emerald-500', warn: 'bg-amber-500 animate-pulse', error: 'bg-red-500', neutral: 'bg-slate-400' }[tone];
  const toneText = { ok: 'text-emerald-700 dark:text-emerald-400', warn: 'text-amber-700 dark:text-amber-400', error: 'text-red-700 dark:text-red-400', neutral: 'text-slate-500 dark:text-slate-400' }[tone];

  // ==================================================
  // 5. UI
  // ==================================================

  if (!shouldProctor) return null;
  if (examCompleted) return null;

  if (!fullscreenReady && !isLocked) {
    return (
      <div
        className="fixed inset-0 z-[100] flex items-center justify-center p-4"
        style={{ background: 'rgba(0,0,0,0.6)' }}
      >
        <div
          className="w-full max-w-sm rounded-2xl p-6 text-center"
          style={{
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            boxShadow: '0 20px 60px rgba(0,0,0,0.35)',
          }}
        >
          <div
            className="w-14 h-14 rounded-full mx-auto mb-4 flex items-center justify-center"
            style={{ background: 'color-mix(in srgb, var(--brand) 15%, transparent)' }}
          >
            <svg className="w-7 h-7" style={{ color: 'var(--brand)' }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
            </svg>
          </div>

          <h2 className="text-base font-bold" style={{ color: 'var(--text)' }}>
            Fullscreen Required
          </h2>
          <p className="mt-2 text-[13px] leading-relaxed" style={{ color: 'var(--muted)' }}>
            This interview must be taken in fullscreen mode with proctoring active.
            Click below to enter fullscreen and start.
          </p>

          <button
            type="button"
            onClick={async () => {
              await requestFullscreen();
              setFullscreenReady(isDocumentFullscreen());
            }}
            className="btn btn-primary w-full mt-4"
          >
            Enter Fullscreen & Start
          </button>
        </div>
      </div>
    );
  }

  if (proctoringBlocked) {
    return (
      <div
        className="fixed inset-0 z-[100] flex items-center justify-center p-4"
        style={{ background: 'rgba(0,0,0,0.6)' }}
      >
        <div
          className="w-full max-w-sm rounded-2xl p-6 text-center"
          style={{
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            boxShadow: '0 20px 60px rgba(0,0,0,0.35)',
          }}
        >
          <div
            className="w-14 h-14 rounded-full mx-auto mb-4 flex items-center justify-center"
            style={{ background: 'color-mix(in srgb, var(--rag-red) 15%, transparent)' }}
          >
            <svg className="w-7 h-7" style={{ color: 'var(--rag-red)' }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
            </svg>
          </div>

          <h2 className="text-base font-bold" style={{ color: 'var(--text)' }}>
            Proctoring Unavailable
          </h2>
          <p className="mt-2 text-[13px] leading-relaxed" style={{ color: 'var(--muted)' }}>
            Camera access or the proctoring system failed. This interview cannot
            continue without proctoring. Please allow camera access and reload.
          </p>
        </div>
      </div>
    );
  }

  if (isLocked) {
    if (currentToast?.isFinal) {
      return (
        <ViolationToast
          violation={currentToast}
          onDismiss={() => {
            setCurrentToast(null);
            const payload = pendingAutoEndRef.current;
            if (payload) {
              pendingAutoEndRef.current = null;
              setAutoEndFired(true);
              onAutoEnd?.(payload);
            }
          }}
          onReenterFullscreen={async () => {
            await requestFullscreen();
            setFullscreenReady(isDocumentFullscreen());
          }}
        />
      );
    }

    // onAutoEnd already fired from the dismiss above — keep the same
    // backdrop up instead of going blank, so there's no flash of the
    // underlying page while waiting for the parent to navigate away.
    if (autoEndFired) {
      return (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center p-4"
          style={{ background: 'rgba(0,0,0,0.6)' }}
        />
      );
    }

    return (
      <div
        className="fixed inset-0 z-[100] flex items-center justify-center p-4"
        style={{ background: 'rgba(0,0,0,0.6)' }}
      >
        <div
          className="w-full max-w-sm rounded-2xl p-6 text-center"
          style={{
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            boxShadow: '0 20px 60px rgba(0,0,0,0.35)',
          }}
        >
          <div
            className="w-14 h-14 rounded-full mx-auto mb-4 flex items-center justify-center"
            style={{ background: 'color-mix(in srgb, var(--rag-red) 15%, transparent)' }}
          >
            <svg className="w-7 h-7" style={{ color: 'var(--rag-red)' }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4.5c-.77-.833-2.694-.833-3.464 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z" />
            </svg>
          </div>

          <h2 className="text-base font-bold" style={{ color: 'var(--text)' }}>
            Interview Locked
          </h2>
          <p className="mt-2 text-[13px] leading-relaxed" style={{ color: 'var(--muted)' }}>
            Your interview was automatically submitted after repeated proctoring
            violations. Contact an administrator if you believe this was a mistake.
          </p>

          <button
            type="button"
            onClick={() => {
              const payload = pendingAutoEndRef.current || {
                reason: 'proctoring_violation_limit_reached',
                violationType: persistedOnMount?.lastViolationType ?? null,
                count: violationCountRef.current,
                timestamp: persistedOnMount?.lastViolationAt ?? Date.now()
              };
              pendingAutoEndRef.current = null;
              onAutoEnd?.(payload);
            }}
            className="btn btn-primary w-full mt-4"
          >
            Continue to Results
          </button>
        </div>
      </div>
    );
  }

  return (
    <>
      {!inline && (
        <div className="fixed bottom-4 right-4 z-50">
          <div className="bg-white dark:bg-slate-900 border-2 border-gray-200 dark:border-slate-700 rounded-xl shadow-xl overflow-hidden">
            <video
              ref={videoRef}
              autoPlay
              muted
              playsInline
              className="w-40 h-28 object-cover bg-black rounded-t-xl"
            />
            <div className="px-2.5 py-2 text-[11px] flex items-center justify-between gap-2 bg-white dark:bg-slate-900">
              <span className={`flex items-center gap-1.5 font-semibold truncate ${toneText}`}>
                <span className={`w-2 h-2 rounded-full shrink-0 ${toneDot}`} />
                {faceStatus}
              </span>
              <span className={`shrink-0 font-mono font-bold ${violationCount > 0 ? 'text-red-600' : 'text-slate-400'}`}>
                {violationCount}/{MAX_VIOLATIONS + 1}
              </span>
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
          <div className="px-3 py-2 text-xs flex items-center justify-between gap-2 bg-slate-900">
            <span className={`flex items-center gap-1.5 font-semibold truncate ${
              tone === 'ok' ? 'text-emerald-400' : tone === 'warn' ? 'text-amber-400' : tone === 'error' ? 'text-red-400' : 'text-slate-400'
            }`}>
              <span className={`w-2 h-2 rounded-full shrink-0 ${toneDot}`} />
              {faceStatus}
            </span>
            <span className={`shrink-0 font-mono font-bold ${violationCount > 0 ? 'text-red-400' : 'text-slate-500'}`}>
              {violationCount}/{MAX_VIOLATIONS + 1}
            </span>
          </div>
        </div>
      )}

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

"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import type { ProctorEvent, ProctorFlag, ProctorState, ProctorSummary } from "./types";

const STRIKE_THRESHOLD = 3;

function ts(): string {
  return new Date().toISOString();
}

function event(
  flag: ProctorFlag,
  severity: "low" | "medium" | "high",
  detail?: string,
): ProctorEvent {
  return { ts: ts(), flag, severity, detail };
}

/**
 * Core proctoring hook. Call once per exam/practice session.
 *
 * Returns the live state, a `summary()` function to collect the final
 * report at submission time, and `requestCamera()` to start the stream.
 */
export function useProctoring() {
  const [state, setState] = useState<ProctorState>({
    events: [],
    strikes: 0,
    cameraActive: false,
    isFullscreen: false,
    isFocused: true,
    faceCount: 1,
    gazeOnScreen: true,
  });

  const eventsRef = useRef<ProctorEvent[]>([]);
  const strikesRef = useRef(0);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const faceIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const prevFaceDataRef = useRef<ImageData | null>(null);

  const addEvent = useCallback(
    (flag: ProctorFlag, severity: "low" | "medium" | "high", detail?: string) => {
      const ev = event(flag, severity, detail);
      eventsRef.current.push(ev);
      if (severity === "high") {
        strikesRef.current += 1;
      }
      setState((prev) => ({
        ...prev,
        events: [...eventsRef.current],
        strikes: strikesRef.current,
      }));
    },
    [],
  );

  // ── Tab / Window Focus Detection ────────────────────────────────────────
  useEffect(() => {
    const onBlur = () => {
      setState((p) => ({ ...p, isFocused: false }));
      addEvent("tab_blur", "high", "Student switched tab or window");
    };
    const onFocus = () => {
      setState((p) => ({ ...p, isFocused: true }));
      addEvent("tab_focus", "low", "Student returned to exam");
    };

    document.addEventListener("visibilitychange", () => {
      if (document.hidden) onBlur();
      else onFocus();
    });
    window.addEventListener("blur", onBlur);
    window.addEventListener("focus", onFocus);

    return () => {
      document.removeEventListener("visibilitychange", onBlur);
      window.removeEventListener("blur", onBlur);
      window.removeEventListener("focus", onFocus);
    };
  }, [addEvent]);

  // ── Fullscreen Detection ────────────────────────────────────────────────
  useEffect(() => {
    const onFSChange = () => {
      const isFS = !!document.fullscreenElement;
      setState((p) => ({ ...p, isFullscreen: isFS }));
      if (!isFS) {
        addEvent("fullscreen_exit", "medium", "Student exited fullscreen");
      }
    };
    document.addEventListener("fullscreenchange", onFSChange);
    return () => document.removeEventListener("fullscreenchange", onFSChange);
  }, [addEvent]);

  // ── Keyboard Shortcuts (screenshot, copy, paste, devtools) ──────────────
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // PrintScreen / Cmd+Shift+3,4 / Alt+PrintScreen
      if (e.key === "PrintScreen" || (e.metaKey && e.shiftKey && (e.key === "3" || e.key === "4" || e.key === "5"))) {
        addEvent("screenshot_attempt", "high", `Key: ${e.key}`);
      }
      // Ctrl+U (view source), F12, Ctrl+Shift+I/J/C
      if (e.key === "F12") {
        addEvent("devtools_open", "high", "F12 pressed");
      }
      if (e.ctrlKey && e.shiftKey && (e.key === "I" || e.key === "J" || e.key === "C")) {
        addEvent("devtools_open", "medium", `Ctrl+Shift+${e.key}`);
      }
    };

    const onContext = (e: MouseEvent) => {
      e.preventDefault();
      addEvent("right_click", "medium", "Right-click disabled during exam");
    };

    const onPaste = () => {
      addEvent("clipboard_paste", "medium", "Paste detected");
    };

    document.addEventListener("keydown", onKey);
    document.addEventListener("contextmenu", onContext);
    document.addEventListener("paste", onPaste);

    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("contextmenu", onContext);
      document.removeEventListener("paste", onPaste);
    };
  }, [addEvent]);

  // ── Camera & Face Detection ─────────────────────────────────────────────
  const requestCamera = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 320, height: 240, facingMode: "user" },
        audio: false,
      });
      streamRef.current = stream;
      setState((p) => ({ ...p, cameraActive: true }));

      // Create hidden video + canvas for face detection
      const video = document.createElement("video");
      video.srcObject = stream;
      video.autoplay = true;
      video.muted = true;
      video.playsInline = true;
      video.style.display = "none";
      document.body.appendChild(video);
      videoRef.current = video;

      const canvas = document.createElement("canvas");
      canvas.width = 320;
      canvas.height = 240;
      canvasRef.current = canvas;

      // Start face detection loop
      faceIntervalRef.current = setInterval(() => detectFace(), 2000);
    } catch (err: any) {
      addEvent("camera_blocked", "high", err.message || "Camera access denied");
    }
  }, [addEvent]);

  const stopCamera = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.remove();
      videoRef.current = null;
    }
    if (faceIntervalRef.current) {
      clearInterval(faceIntervalRef.current);
      faceIntervalRef.current = null;
    }
    setState((p) => ({ ...p, cameraActive: false }));
  }, []);

  // ── Simple Face Detection via Canvas ────────────────────────────────────
  // Uses skin-color detection as a lightweight proxy for face presence.
  const detectFace = useCallback(() => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    ctx.drawImage(video, 0, 0, 320, 240);
    const imageData = ctx.getImageData(0, 0, 320, 240);
    const data = imageData.data;

    // Count skin-colored pixels (simple HSV-based)
    let skinPixels = 0;
    const totalPixels = 320 * 240;
    for (let i = 0; i < data.length; i += 16) {
      const r = data[i];
      const g = data[i + 1];
      const b = data[i + 2];
      // Skin color heuristic in RGB space
      if (r > 95 && g > 40 && b > 20 &&
          r > g && r > b &&
          (r - g) > 15 &&
          Math.abs(r - g) > 15) {
        skinPixels++;
      }
    }

    const skinRatio = skinPixels / (totalPixels / 16);
    const hasFace = skinRatio > 0.05; // At least 5% skin-colored pixels

    // Motion detection (compare with previous frame)
    let motion = 0;
    if (prevFaceDataRef.current) {
      const prev = prevFaceDataRef.current.data;
      for (let i = 0; i < data.length; i += 64) {
        if (Math.abs(data[i] - prev[i]) > 30) motion++;
      }
    }
    prevFaceDataRef.current = imageData;

    setState((p) => {
      const newFaceCount = hasFace ? 1 : 0;
      if (!hasFace && p.faceCount > 0) {
        addEvent("no_face", "high", "No face detected in camera");
      } else if (hasFace && p.faceCount === 0) {
        addEvent("face_changed", "low", "Face reappeared");
      }
      return { ...p, faceCount: newFaceCount };
    });
  }, [addEvent]);

  // ── Gaze Detection (simplified — uses screen position) ──────────────────
  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      // If mouse is near edges, student might be looking at second monitor
      const w = window.innerWidth;
      const h = window.innerHeight;
      const onScreen =
        e.clientX > 50 && e.clientX < w - 50 &&
        e.clientY > 50 && e.clientY < h - 50;

      if (!onScreen && state.gazeOnScreen) {
        setState((p) => ({ ...p, gazeOnScreen: false }));
        addEvent("gaze_away", "low", "Cursor near screen edge — possible second monitor");
      } else if (onScreen && !state.gazeOnScreen) {
        setState((p) => ({ ...p, gazeOnScreen: true }));
      }
    };

    document.addEventListener("mousemove", onMouseMove);
    return () => document.removeEventListener("mousemove", onMouseMove);
  }, [addEvent, state.gazeOnScreen]);

  // ── Summary for submission ──────────────────────────────────────────────
  const summary = useCallback((): ProctorSummary => {
    return {
      total_events: eventsRef.current.length,
      strikes: strikesRef.current,
      events: eventsRef.current,
      should_auto_submit: strikesRef.current >= STRIKE_THRESHOLD,
    };
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopCamera();
    };
  }, [stopCamera]);

  return {
    state,
    requestCamera,
    stopCamera,
    summary,
    videoRef,
  };
}

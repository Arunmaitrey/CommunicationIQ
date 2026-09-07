"use client";
import { useEffect, useState } from "react";
import { Maximize2, AlertTriangle, Shield, Camera, Mic } from "lucide-react";

/**
 * Wraps practice/exam content. If the student exits fullscreen during the session,
 * shows a blocking overlay prompting them to re-enter fullscreen to continue.
 */
export function FullscreenGuard({ children }: { children: React.ReactNode }) {
  const [isFullscreen, setIsFullscreen] = useState(true);

  useEffect(() => {
    const onChange = () => {
      setIsFullscreen(!!document.fullscreenElement);
    };
    document.addEventListener("fullscreenchange", onChange);
    setIsFullscreen(!!document.fullscreenElement);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  const enterFullscreen = () => {
    document.documentElement.requestFullscreen().catch(() => {});
  };

  return (
    <>
      {children}

      {/* Fullscreen exit overlay — blocks interaction until re-entered */}
      {!isFullscreen && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center"
          style={{ background: "rgba(0,0,0,0.9)" }}
        >
          <div className="max-w-md w-full mx-4 space-y-5 p-8 rounded-2xl"
               style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
            {/* Warning icon */}
            <div className="text-center">
              <div className="w-16 h-16 rounded-full mx-auto flex items-center justify-center mb-4"
                   style={{ background: "color-mix(in srgb, var(--rag-amber) 15%, transparent)" }}>
                <AlertTriangle size={32} style={{ color: "var(--rag-amber)" }} />
              </div>
              <h2 className="text-lg font-bold mb-2">Exam Paused — Fullscreen Required</h2>
              <p className="text-sm text-muted leading-relaxed">
                You exited fullscreen during the exam. This is required for exam integrity.
                Please re-enter fullscreen to continue.
              </p>
            </div>

            {/* Status indicators */}
            <div className="flex items-center justify-center gap-4 text-xs text-muted">
              <span className="flex items-center gap-1.5">
                <Camera size={12} /> Camera active
              </span>
              <span className="flex items-center gap-1.5">
                <Mic size={12} /> Mic active
              </span>
              <span className="flex items-center gap-1.5">
                <Shield size={12} /> Proctoring on
              </span>
            </div>

            {/* Re-enter button */}
            <button
              onClick={enterFullscreen}
              className="btn btn-primary w-full ds-focus flex items-center justify-center gap-2 py-3"
            >
              <Maximize2 size={18} />
              Re-enter Fullscreen
            </button>

            <p className="text-[10px] text-muted text-center">
              Your exam progress is saved. Nothing is lost.
            </p>
          </div>
        </div>
      )}
    </>
  );
}

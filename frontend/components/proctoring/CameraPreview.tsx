"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { Camera, CameraOff, Eye, AlertTriangle, GripVertical } from "lucide-react";

/**
 * Draggable camera preview shown during exams.
 * Displays the student's own face feed so they can verify the camera works.
 * Can be dragged anywhere on the screen.
 */
export function CameraPreview({
  videoRef,
  faceCount,
  strikes,
  isFocused,
}: {
  videoRef: React.RefObject<HTMLVideoElement | null>;
  faceCount: number;
  strikes: number;
  isFocused: boolean;
}) {
  const localVideoRef = useRef<HTMLVideoElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [collapsed, setCollapsed] = useState(false);
  const [hasStream, setHasStream] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pos, setPos] = useState({ x: 12, y: 12 });
  const dragging = useRef(false);
  const dragOffset = useRef({ x: 0, y: 0 });

  useEffect(() => {
    let attempts = 0;
    const check = () => {
      if (videoRef.current?.srcObject) {
        setHasStream(true);
      } else if (attempts < 10) {
        attempts++;
        setTimeout(check, 500);
      } else {
        setError("Camera not available");
      }
    };
    check();
  }, [videoRef]);

  // Copy stream to visible video after hasStream becomes true and <video> mounts
  useEffect(() => {
    if (hasStream && localVideoRef.current && videoRef.current?.srcObject) {
      localVideoRef.current.srcObject = videoRef.current.srcObject;
    }
  }, [hasStream, videoRef]);

  const onPointerDown = useCallback((e: React.PointerEvent) => {
    dragging.current = true;
    const rect = containerRef.current?.getBoundingClientRect();
    if (rect) {
      dragOffset.current = { x: e.clientX - rect.left, y: e.clientY - rect.top };
    }
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  }, []);

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    if (!dragging.current) return;
    setPos({
      x: Math.max(0, Math.min(window.innerWidth - 170, e.clientX - dragOffset.current.x)),
      y: Math.max(0, Math.min(window.innerHeight - 160, e.clientY - dragOffset.current.y)),
    });
  }, []);

  const onPointerUp = useCallback(() => {
    dragging.current = false;
  }, []);

  return (
    <div
      ref={containerRef}
      className="fixed z-[60] rounded-lg overflow-hidden shadow-lg touch-none select-none"
      style={{
        top: pos.y,
        left: pos.x,
        width: collapsed ? 48 : 160,
        background: "var(--surface)",
        border: "1px solid var(--border)",
        transition: dragging.current ? "none" : "width 0.2s ease",
      }}
    >
      {/* Draggable header */}
      <div
        className="flex items-center justify-between px-2 py-1 cursor-grab active:cursor-grabbing"
        style={{ background: "color-mix(in srgb, var(--primary) 10%, transparent)" }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
      >
        <div className="flex items-center gap-1">
          <GripVertical size={10} className="text-muted" />
          <Camera size={10} style={{ color: "var(--primary)" }} />
          {!collapsed && (
            <span className="text-[9px] font-semibold uppercase" style={{ color: "var(--primary)" }}>
              Proctoring
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          {strikes > 0 && (
            <span
              className="text-[9px] font-bold px-1.5 py-0.5 rounded-full"
              style={{
                background: strikes >= 3 ? "var(--rag-red)" : "var(--rag-amber)",
                color: "var(--on-primary)",
              }}
            >
              {strikes}/3
            </span>
          )}
          <button
            onClick={(e) => { e.stopPropagation(); setCollapsed(!collapsed); }}
            className="text-[9px] text-muted hover:text-text"
          >
            {collapsed ? "▶" : "◀"}
          </button>
        </div>
      </div>

      {!collapsed && (
        <div className="relative">
          {hasStream ? (
            <video
              ref={localVideoRef}
              autoPlay
              muted
              playsInline
              className="w-full"
              style={{ height: 100, objectFit: "cover", transform: "scaleX(-1)", background: "var(--surface-2)" }}
            />
          ) : (
            <div className="w-full flex items-center justify-center"
                 style={{ height: 100, background: "var(--surface-2)" }}>
              <div className="text-center">
                <Camera size={16} className="mx-auto mb-1 text-muted" />
                <span className="text-[8px] text-muted">
                  {error || "Starting camera…"}
                </span>
              </div>
            </div>
          )}
          <div className="absolute bottom-1 left-1 right-1 flex items-center gap-1">
            <span
              className="text-[8px] px-1 py-0.5 rounded font-semibold flex items-center gap-0.5"
              style={{ background: faceCount > 0 ? "var(--rag-green)" : "var(--rag-red)", color: "var(--on-primary)" }}
            >
              {faceCount > 0 ? <Eye size={8} /> : <CameraOff size={8} />}
              {faceCount > 0 ? "Face OK" : "No face"}
            </span>
            {!isFocused && (
              <span className="text-[8px] px-1 py-0.5 rounded font-semibold"
                style={{ background: "var(--rag-red)", color: "var(--on-primary)" }}>
                Tab left
              </span>
            )}
          </div>
        </div>
      )}

      {collapsed && (
        <div className="flex items-center justify-center py-1" style={{ height: 48 }}>
          {faceCount > 0 ? (
            <Eye size={14} style={{ color: "var(--rag-green)" }} />
          ) : (
            <AlertTriangle size={14} style={{ color: "var(--rag-red)" }} />
          )}
        </div>
      )}
    </div>
  );
}

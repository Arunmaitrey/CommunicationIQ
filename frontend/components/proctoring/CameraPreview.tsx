"use client";
import { useEffect, useRef, useState } from "react";
import { Camera, CameraOff, Eye, AlertTriangle } from "lucide-react";

/**
 * Small camera preview shown in the top-right corner during exams.
 * Displays the student's own face feed so they can verify the camera works.
 * Also shows the face detection status and strike count.
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
  const [collapsed, setCollapsed] = useState(false);
  const [hasStream, setHasStream] = useState(false);

  // Poll for stream availability (the hook creates it async)
  useEffect(() => {
    const check = () => {
      if (videoRef.current?.srcObject) {
        setHasStream(true);
        // Mirror to our local display video
        if (localVideoRef.current) {
          localVideoRef.current.srcObject = videoRef.current.srcObject;
        }
      } else {
        setTimeout(check, 500);
      }
    };
    check();
  }, [videoRef]);

  if (!hasStream) return null;

  return (
    <div
      className="fixed z-50 rounded-lg overflow-hidden shadow-lg"
      style={{
        top: 12,
        right: 12,
        width: collapsed ? 48 : 160,
        background: "var(--surface)",
        border: "1px solid var(--border)",
        transition: "width 0.2s ease",
      }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-2 py-1 cursor-pointer"
        style={{ background: "color-mix(in srgb, var(--primary) 10%, transparent)" }}
        onClick={() => setCollapsed(!collapsed)}
      >
        <div className="flex items-center gap-1">
          <Camera size={10} style={{ color: "var(--primary)" }} />
          {!collapsed && (
            <span className="text-[9px] font-semibold uppercase" style={{ color: "var(--primary)" }}>
              Proctoring
            </span>
          )}
        </div>
        {strikes > 0 && (
          <span
            className="text-[9px] font-bold px-1.5 py-0.5 rounded-full"
            style={{
              background: strikes >= 3 ? "var(--rag-red)" : "var(--rag-amber)",
              color: "white",
            }}
          >
            {strikes}/3
          </span>
        )}
      </div>

      {/* Video feed */}
      {!collapsed && (
        <div className="relative">
          <video
            ref={localVideoRef}
            autoPlay
            muted
            playsInline
            className="w-full"
            style={{
              height: 100,
              objectFit: "cover",
              transform: "scaleX(-1)",
              background: "#000",
            }}
          />

          {/* Status indicators overlay */}
          <div className="absolute bottom-1 left-1 right-1 flex items-center gap-1">
            {/* Face status */}
            <span
              className="text-[8px] px-1 py-0.5 rounded font-semibold flex items-center gap-0.5"
              style={{
                background: faceCount > 0 ? "var(--rag-green)" : "var(--rag-red)",
                color: "white",
              }}
            >
              {faceCount > 0 ? <Eye size={8} /> : <CameraOff size={8} />}
              {faceCount > 0 ? "Face OK" : "No face"}
            </span>

            {/* Focus status */}
            {!isFocused && (
              <span
                className="text-[8px] px-1 py-0.5 rounded font-semibold"
                style={{ background: "var(--rag-red)", color: "white" }}
              >
                Tab left
              </span>
            )}
          </div>
        </div>
      )}

      {/* Collapsed mini indicator */}
      {collapsed && (
        <div
          className="flex items-center justify-center py-1"
          style={{ height: 48 }}
        >
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

"use client";
import { AlertTriangle, Eye, Monitor, X } from "lucide-react";

/**
 * Warning popup shown when proctoring detects suspicious activity.
 * Shows a message and the remaining strikes before auto-submit.
 */
export function ProctorWarning({
  strikes,
  maxStrikes,
  message,
  onDismiss,
  isFocused,
}: {
  strikes: number;
  maxStrikes: number;
  message: string;
  onDismiss: () => void;
  isFocused: boolean;
}) {
  if (isFocused && strikes === 0) return null;

  const remaining = maxStrikes - strikes;
  const severity = remaining <= 1 ? "high" : remaining <= 2 ? "medium" : "low";

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center"
      style={{ background: "rgba(0,0,0,0.6)" }}
    >
      <div
        className="rounded-xl p-6 max-w-sm w-full mx-4 text-center"
        style={{
          background: "var(--surface)",
          border: `2px solid ${severity === "high" ? "var(--rag-red)" : severity === "medium" ? "var(--rag-amber)" : "var(--primary)"}`,
          boxShadow: "0 20px 60px rgba(0,0,0,0.3)",
        }}
      >
        {/* Icon */}
        <div
          className="w-14 h-14 rounded-full mx-auto mb-4 flex items-center justify-center"
          style={{
            background: severity === "high"
              ? "color-mix(in srgb, var(--rag-red) 15%, transparent)"
              : "color-mix(in srgb, var(--rag-amber) 15%, transparent)",
          }}
        >
          <AlertTriangle
            size={28}
            style={{ color: severity === "high" ? "var(--rag-red)" : "var(--rag-amber)" }}
          />
        </div>

        {/* Title */}
        <h3 className="text-base font-bold mb-2" style={{ color: "var(--text)" }}>
          {!isFocused ? "Do not leave the exam" : "Proctoring Warning"}
        </h3>

        {/* Message */}
        <p className="text-[13px] mb-4" style={{ color: "var(--muted)" }}>
          {!isFocused
            ? "You have switched away from the exam. Please return immediately. Switching tabs is not allowed during the exam."
            : message
          }
        </p>

        {/* Strike counter */}
        <div className="flex items-center justify-center gap-2 mb-4">
          {Array.from({ length: maxStrikes }).map((_, i) => (
            <div
              key={i}
              className="w-3 h-3 rounded-full"
              style={{
                background: i < strikes
                  ? "var(--rag-red)"
                  : "color-mix(in srgb, var(--border) 50%, transparent)",
              }}
            />
          ))}
        </div>

        <p className="text-[11px] font-semibold mb-4" style={{ color: "var(--rag-red)" }}>
          {remaining > 0
            ? `${remaining} warning${remaining !== 1 ? "s" : ""} remaining. The exam will auto-submit after ${maxStrikes} violations.`
            : "Auto-submitting now..."
          }
        </p>

        {/* Action buttons */}
        <div className="flex gap-2 justify-center">
          {!isFocused ? (
            <button
              onClick={onDismiss}
              className="px-4 py-2 rounded-lg text-[12px] font-semibold"
              style={{
                background: "var(--primary)",
                color: "white",
              }}
            >
              Return to Exam
            </button>
          ) : (
            <button
              onClick={onDismiss}
              className="px-4 py-2 rounded-lg text-[12px] font-semibold flex items-center gap-1.5"
              style={{
                background: "var(--primary)",
                color: "white",
              }}
            >
              <X size={12} /> Dismiss
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

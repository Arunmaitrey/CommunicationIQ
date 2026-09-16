"use client";
import { useState } from "react";
import { Loader2, Star } from "lucide-react";
import { useToast } from "@/components/Toast";
import { API_BASE, getToken } from "@/lib/api";

/**
 * Review & Rating card shown after each practice session.
 * Submits rating to the backend and shows the question review.
 */
export function ReviewCard({
  attemptId,
  label,
  onNext,
  onBack,
  nextLabel = "Next set →",
  backLabel = "Back to practice",
  children,
}: {
  attemptId?: string;
  label: string;
  onNext: () => void;
  onBack: () => void;
  nextLabel?: string;
  backLabel?: string;
  children?: React.ReactNode;
}) {
  const { toast } = useToast();
  const [rating, setRating] = useState(0);
  const [hoveredStar, setHoveredStar] = useState(0);
  const [difficulty, setDifficulty] = useState<"easy" | "just_right" | "hard" | "">("");
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  async function submitRating(star: number) {
    setRating(star);
    if (!attemptId) return;
    setSubmitting(true);
    try {
      const res = await fetch(`${API_BASE}/student/attempts/${attemptId}/review`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${getToken() || ""}`,
        },
        body: JSON.stringify({ rating: star, difficulty: difficulty || "just_right" }),
      });
      if (res.ok) {
        setSubmitted(true);
        toast("success", "Thanks for your feedback!");
      }
    } catch {
      // silent — rating is non-critical
    } finally {
      setSubmitting(false);
    }
  }

  const DIFFICULTY_OPTIONS = [
    { value: "easy" as const, label: "Easy", color: "var(--rag-green)" },
    { value: "just_right" as const, label: "Just Right", color: "var(--primary)" },
    { value: "hard" as const, label: "Hard", color: "var(--rag-red)" },
  ];

  return (
    <div className="ds-card p-5 mb-4">
      <div className="flex items-center justify-between mb-3">
        <div className="text-sm font-bold">
          {submitted ? "Thank you for your feedback!" : `Rate this ${label}`}
        </div>
        {!submitted && (
          <div className="flex gap-1 items-center">
            {submitting && <Loader2 size={14} className="animate-spin text-muted" />}
            {[1, 2, 3, 4, 5].map((star) => (
              <button
                key={star}
                onClick={() => submitRating(star)}
                onMouseEnter={() => setHoveredStar(star)}
                onMouseLeave={() => setHoveredStar(0)}
                disabled={submitting}
                className="text-lg transition-transform hover:scale-110 disabled:opacity-50"
                style={{
                  color: star <= (hoveredStar || rating) ? "var(--rag-amber)" : "var(--muted)",
                }}
              >
                <Star size={18} fill={star <= (hoveredStar || rating) ? "var(--rag-amber)" : "none"} />
              </button>
            ))}
          </div>
        )}
        {submitted && (
          <div className="flex gap-0.5">
            {[1, 2, 3, 4, 5].map((star) => (
              <Star key={star} size={16} fill={star <= rating ? "var(--rag-amber)" : "none"}
                style={{ color: star <= rating ? "var(--rag-amber)" : "var(--muted)" }} />
            ))}
          </div>
        )}
      </div>
      <div className="text-xs text-muted leading-relaxed mb-3">
        How was this {label}? Your rating helps improve question quality.
      </div>
      {/* Difficulty selector */}
      {!submitted && (
        <div className="flex items-center gap-2 mb-3">
          <span className="text-[10px] font-semibold text-muted uppercase tracking-wider">Difficulty:</span>
          <div className="flex gap-1.5">
            {DIFFICULTY_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                onClick={() => setDifficulty(opt.value)}
                className="text-[10px] font-semibold px-2.5 py-1 rounded-full transition-colors"
                style={{
                  background: difficulty === opt.value
                    ? `color-mix(in srgb, ${opt.color} 20%, transparent)`
                    : "var(--surface-2)",
                  color: difficulty === opt.value ? opt.color : "var(--muted)",
                  border: difficulty === opt.value ? `1.5px solid ${opt.color}` : "1.5px solid var(--border)",
                }}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      )}
      {children && <div className="mb-3">{children}</div>}
      <div className="flex items-center gap-3">
        <button onClick={onNext}
          className="btn btn-primary btn-sm ds-focus flex-1">
          {nextLabel}
        </button>
        <button onClick={onBack}
          className="btn btn-ghost btn-sm ds-focus">
          {backLabel}
        </button>
      </div>
    </div>
  );
}

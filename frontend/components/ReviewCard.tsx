"use client";
import { useState } from "react";
import { Star } from "lucide-react";
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
  const [submitted, setSubmitted] = useState(false);

  async function submitRating(star: number) {
    setRating(star);
    if (!attemptId) return;
    try {
      const res = await fetch(`${API_BASE}/student/attempts/${attemptId}/review`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${getToken() || ""}`,
        },
        body: JSON.stringify({ rating: star, difficulty: "just_right" }),
      });
      if (res.ok) {
        setSubmitted(true);
        toast("success", "Thanks for your feedback!");
      }
    } catch {
      // silent — rating is non-critical
    }
  }

  return (
    <div className="ds-card p-5 mb-4">
      <div className="flex items-center justify-between mb-3">
        <div className="text-sm font-bold">
          {submitted ? "Thank you for your feedback!" : `Rate this ${label}`}
        </div>
        {!submitted && (
          <div className="flex gap-1">
            {[1, 2, 3, 4, 5].map((star) => (
              <button
                key={star}
                onClick={() => submitRating(star)}
                onMouseEnter={() => setHoveredStar(star)}
                onMouseLeave={() => setHoveredStar(0)}
                className="text-lg transition-transform hover:scale-110"
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

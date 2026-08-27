"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Clock, MessageSquare, Star, ThumbsDown, ThumbsUp, Minus } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { PageHeader, Section, Skeleton, Badge } from "@/components/ui";
import { SITTING_ROLES } from "@/lib/nav";

interface Review {
  attempt_id: string;
  rating: number;
  comment: string;
  difficulty: string;
  submitted_at: string;
}

const DIFF_ICONS: Record<string, typeof Star> = {
  easy: ThumbsUp,
  just_right: Minus,
  hard: ThumbsDown,
};

const DIFF_LABELS: Record<string, string> = {
  easy: "Easy",
  just_right: "Just Right",
  hard: "Hard",
};

export default function WritingReviewsPage() {
  return (
    <RequireAuth roles={SITTING_ROLES}>
      <WritingReviews />
    </RequireAuth>
  );
}

function WritingReviews() {
  const [reviews, setReviews] = useState<Review[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const found: Review[] = [];
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key?.startsWith("commiq.reviews.")) {
        try {
          const raw = localStorage.getItem(key);
          if (raw) found.push(JSON.parse(raw));
        } catch { /* skip corrupt */ }
      }
    }
    found.sort((a, b) => new Date(b.submitted_at).getTime() - new Date(a.submitted_at).getTime());
    setReviews(found);
    setLoading(false);
  }, []);

  if (loading) return <Skeleton rows={4} />;

  return (
    <>
      <PageHeader
        title="Writing Reviews"
        sub="Your feedback on past writing exams"
      />

      {reviews.length === 0 ? (
        <Section>
          <div className="text-center py-12 text-muted">
            <Star size={32} className="mx-auto mb-3 opacity-30" />
            <div className="text-sm font-medium mb-1">No reviews yet</div>
            <div className="text-xs">Complete a writing exam and leave a review to see it here.</div>
            <Link href="/tests" className="btn btn-primary btn-sm mt-4">
              Take a test
            </Link>
          </div>
        </Section>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {reviews.map((review) => {
            const DiffIcon = DIFF_ICONS[review.difficulty] || Minus;
            return (
              <div
                key={review.attempt_id}
                className="ds-card p-4 flex flex-col gap-3 hover:shadow-md transition-shadow"
                style={{ borderColor: review.rating >= 4 ? "var(--rag-green)" : review.rating <= 2 ? "var(--rag-red)" : undefined }}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1">
                    {[1, 2, 3, 4, 5].map((s) => (
                      <Star
                        key={s}
                        size={14}
                        className={s <= review.rating ? "fill-amber-400 text-amber-400" : "text-muted/30"}
                      />
                    ))}
                  </div>
                  <Badge>
                    {DIFF_LABELS[review.difficulty] || review.difficulty}
                  </Badge>
                </div>

                {review.comment && (
                  <div className="flex items-start gap-2 text-xs text-muted">
                    <MessageSquare size={12} className="shrink-0 mt-0.5" />
                    <span className="line-clamp-3">{review.comment}</span>
                  </div>
                )}

                <div className="flex items-center gap-1.5 text-[10px] text-muted mt-auto pt-2 border-t border-border">
                  <Clock size={10} />
                  <span>{new Date(review.submitted_at).toLocaleDateString()}</span>
                  <span className="ml-auto font-mono text-[9px] opacity-50">
                    {review.attempt_id.slice(0, 8)}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </>
  );
}

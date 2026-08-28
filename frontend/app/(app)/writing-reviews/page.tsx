"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Clock, MessageSquare, Star, ThumbsDown, ThumbsUp, Minus, FileText, ExternalLink } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { PageHeader, Section, Skeleton, Badge, ErrorNote, EmptyState } from "@/components/ui";
import { SITTING_ROLES } from "@/lib/nav";
import { API_BASE, getToken } from "@/lib/api";
import { useData } from "@/lib/useData";
import { api, attemptApi } from "@/lib/api";

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
  // Fetch the student's home data which includes recent attempts with scores
  const home = useData(() => api.studentHome());
  // Fetch writing submissions
  const writingSubmissions = useData(() => {
    const token = getToken();
    return fetch(`${API_BASE}/student/writing/submissions`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    }).then((r) => r.ok ? r.json() : []);
  });
  // Fetch all reviews (student reviews on exam results)
  const reviews = useData(() => {
    const token = getToken();
    return fetch(`${API_BASE}/student/writing/submissions`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    }).then((r) => r.ok ? r.json() : []);
  });

  if (home.loading || writingSubmissions.loading) return <Skeleton rows={4} />;
  if (home.error) return <ErrorNote message={home.error} />;

  const submissions = (writingSubmissions.data ?? []) as any[];
  const attempts = (home.data?.recent_attempts ?? []);

  return (
    <>
      <PageHeader
        title="Writing Reviews"
        sub="Your writing submissions, scores and feedback"
      />

      {/* Writing submissions with scores */}
      {submissions.length > 0 ? (
        <Section title="Writing submissions" className="mb-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {submissions.map((sub: any) => (
              <div
                key={sub.submission_id}
                className="ds-card p-4 flex flex-col gap-3 hover:shadow-md transition-shadow"
              >
                <div className="flex items-center justify-between">
                  <div className="text-sm font-bold">{sub.title || "Writing Task"}</div>
                  {sub.overall != null && (
                    <div className="text-lg font-bold" style={{
                      color: sub.overall >= 60 ? "var(--rag-green)" : sub.overall >= 40 ? "var(--rag-amber)" : "var(--rag-red)"
                    }}>
                      {sub.overall}
                    </div>
                  )}
                </div>

                {/* Measures */}
                {sub.measures && sub.measures.length > 0 && (
                  <div className="space-y-1.5">
                    {sub.measures.map((m: any) => (
                      <div key={m.name} className="flex items-center justify-between">
                        <span className="text-[11px] text-muted capitalize">{m.name.replace(/_/g, " ")}</span>
                        <div className="flex items-center gap-2">
                          <div className="w-16 h-1.5 rounded-full" style={{ background: "var(--surface-2)" }}>
                            <div className="h-full rounded-full" style={{
                              width: `${Math.min(100, (m.score / 80) * 100)}%`,
                              background: m.score >= 60 ? "var(--rag-green)" : m.score >= 40 ? "var(--rag-amber)" : "var(--rag-red)"
                            }} />
                          </div>
                          <span className="text-[10px] font-bold w-6 text-right">{Math.round(m.score)}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                <div className="text-[10px] text-muted">{sub.word_count} words</div>

                <div className="flex items-center gap-1.5 text-[10px] text-muted mt-auto pt-2 border-t border-border">
                  <Clock size={10} />
                  <span>Submitted</span>
                </div>
              </div>
            ))}
          </div>
        </Section>
      ) : (
        <EmptyState
          icon={FileText}
          title="No writing submissions yet"
          desc="Complete a writing practice to see your submissions and scores here."
          action={<Link href="/writing" className="btn btn-primary btn-sm">Start writing practice</Link>}
        />
      )}

      {/* Exam attempts with scores */}
      {attempts.length > 0 && (
        <Section title="Recent exam scores" className="mb-4">
          <div className="space-y-2">
            {attempts.map((a: any) => (
              <div key={a.id} className="flex items-center justify-between p-3 rounded-lg" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
                <div className="flex items-center gap-3">
                  <div className="min-w-0">
                    <div className="text-[12px] font-medium">{a.profile_name || "Exam"}</div>
                    <div className="text-[10px] text-muted">Attempt #{a.attempt_number}</div>
                  </div>
                  <Badge tone={a.status === "scored" ? "var(--rag-green)" : "var(--muted)"}>{a.status}</Badge>
                </div>
                <div className="flex items-center gap-2">
                  {a.overall_score != null && (
                    <span className="text-sm font-bold" style={{
                      color: (a.overall_score as number) >= 60 ? "var(--rag-green)" : (a.overall_score as number) >= 40 ? "var(--rag-amber)" : "var(--rag-red)"
                    }}>
                      {(a.overall_score as number).toFixed(1)}
                    </span>
                  )}
                  {a.status === "scored" && (
                    <a href={`/results/${a.id}`} className="btn btn-ghost text-[10px] px-2 py-1 ds-focus">
                      <ExternalLink size={11} /> View
                    </a>
                  )}
                </div>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Link to take a test if no data */}
      {submissions.length === 0 && attempts.length === 0 && (
        <Section>
          <div className="text-center py-8 text-muted">
            <Star size={32} className="mx-auto mb-3 opacity-30" />
            <div className="text-sm font-medium mb-1">No activity yet</div>
            <div className="text-xs">Start a practice or take a test to see your progress here.</div>
            <div className="flex items-center justify-center gap-2 mt-4">
              <Link href="/writing" className="btn btn-primary btn-sm">Writing practice</Link>
              <Link href="/tests" className="btn btn-ghost btn-sm">Take a test</Link>
            </div>
          </div>
        </Section>
      )}
    </>
  );
}

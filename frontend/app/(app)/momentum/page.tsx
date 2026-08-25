"use client";
import { useState } from "react";
import { Flag as FlagIcon, TrendingDown } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import {
  Badge, EmptyState, ErrorNote, PageHeader, Section, Skeleton, Table,
} from "@/components/ui";
import { trainerApi } from "@/lib/api";
import { useData } from "@/lib/useData";

export default function MomentumPage() {
  return (
    <RequireAuth roles={["trainer"]}>
      <Momentum />
    </RequireAuth>
  );
}

/** Who has gone dark, with a drive approaching (TRN-06). */
function Momentum() {
  const { data, loading, error, reload } = useData(() => trainerApi.momentum());
  const [busy, setBusy] = useState("");

  async function flag(userId: string, suggestion: string) {
    setBusy(userId);
    try {
      await trainerApi.raiseFlag(userId, "gone_dark", suggestion);
      reload();
    } finally {
      setBusy("");
    }
  }

  const needing = (data ?? []).filter((r) => r.suggest_flag);

  return (
    <>
      <PageHeader
        title="Momentum"
        sub="Practice consistency across your cohorts. Sorted so the people who need attention are at the top."
      />

      {needing.length > 0 && (
        <div className="ds-card p-4 mb-4" style={{ borderColor: "var(--rag-amber)" }}>
          <div className="text-sm font-bold mb-1">
            {needing.length} student(s) worth a conversation
          </div>
          <p className="text-xs text-muted leading-relaxed">
            Quiet for several days with their drive date close. Nothing has been sent
            to them — this is a suggestion to you.
          </p>
        </div>
      )}

      <Section>
        {loading ? <Skeleton rows={6} /> : error ? <ErrorNote message={error} /> :
         (data ?? []).length === 0 ? (
          <EmptyState icon={TrendingDown} title="No students in your cohorts yet" />
        ) : (
          <Table
            columns={["Student", "Cohort", "Last active", "Attempts", "Streak",
                      "Drive in", "Score", ""]}
            rows={(data ?? []).map((r) => [
              <span key="n">
                <span className="font-medium">{r.full_name}</span>
                {r.suggestion && (
                  <span className="block text-[11px]" style={{ color: "var(--rag-amber)" }}>
                    {r.suggestion}
                  </span>
                )}
              </span>,
              r.cohort_name,
              r.days_since_activity != null
                ? `${r.days_since_activity}d ago`
                : <span key="l" className="text-muted">never</span>,
              r.attempts,
              r.current_streak ? `${r.current_streak}d` : "—",
              r.days_to_drive != null ? `${r.days_to_drive}d` : "—",
              r.overall_score ?? "—",
              r.flagged
                ? <Badge key="f" tone="var(--rag-red)">flagged</Badge>
                : r.suggest_flag
                  ? <button key="f" disabled={busy === r.user_id}
                            onClick={() => void flag(r.user_id, r.suggestion)}
                            className="btn btn-ghost btn-sm ds-focus">
                      <FlagIcon size={12} /> Flag
                    </button>
                  : "",
            ])}
          />
        )}
      </Section>
    </>
  );
}

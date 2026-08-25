"use client";
import { useState } from "react";
import { AlertTriangle, Check, Flag as FlagIcon } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import {
  Badge, EmptyState, ErrorNote, PageHeader, Section, Skeleton, Table,
} from "@/components/ui";
import { trainerApi } from "@/lib/api";
import { useData } from "@/lib/useData";

export default function FlagsPage() {
  return (
    <RequireAuth roles={["trainer"]}>
      <Flags />
    </RequireAuth>
  );
}

/** At-risk flags (TRN-03).
 *
 *  Staff-visible only. Nothing on this screen sends a student anything, and
 *  the copy says so — a trainer needs to know that flagging somebody is a
 *  note to themselves, not a message that lands on the student's phone.
 */
function Flags() {
  const [showResolved, setShowResolved] = useState(false);
  const { data, loading, error, reload } = useData(
    () => trainerApi.flags(showResolved), [showResolved]);

  async function resolve(id: string) {
    await trainerApi.resolveFlag(id);
    reload();
  }

  return (
    <>
      <PageHeader
        title="At-risk flags"
        sub="Visible to staff only. Flagging a student does not notify them — this is your note, and the intervention is yours to make."
      />

      <div className="flex items-center gap-2 mb-4">
        <button onClick={() => setShowResolved(false)}
                className={`btn btn-sm ds-focus ${showResolved ? "btn-ghost" : "btn-soft"}`}>
          Open
        </button>
        <button onClick={() => setShowResolved(true)}
                className={`btn btn-sm ds-focus ${showResolved ? "btn-soft" : "btn-ghost"}`}>
          Including resolved
        </button>
      </div>

      <Section>
        {loading ? <Skeleton rows={4} /> : error ? <ErrorNote message={error} /> :
         (data ?? []).length === 0 ? (
          <EmptyState icon={FlagIcon} title="No open flags"
                      desc="Raise one from the momentum view or a cohort's student list." />
        ) : (
          <Table
            columns={["Student", "Reason", "Note", "Raised by", "Source", ""]}
            rows={(data ?? []).map((f) => [
              <span key="n" className="font-medium">{f.student_name}</span>,
              <Badge key="r" tone="var(--rag-amber)">{f.reason.replace(/_/g, " ")}</Badge>,
              <span key="no" className="text-muted">{f.note || "—"}</span>,
              f.raised_by_name,
              f.auto_suggested
                ? <Badge key="s" tone="var(--muted)">suggested</Badge>
                : <span key="s" className="text-muted">manual</span>,
              f.resolved
                ? <Badge key="d" tone="var(--rag-green)">resolved</Badge>
                : <button key="d" onClick={() => void resolve(f.id)}
                          className="btn btn-ghost btn-sm ds-focus">
                    <Check size={12} /> Resolve
                  </button>,
            ])}
          />
        )}
      </Section>

      <div className="ds-card p-4 mt-4 flex items-start gap-3">
        <AlertTriangle size={15} className="text-muted shrink-0 mt-0.5" />
        <p className="text-xs text-muted leading-relaxed">
          The momentum view suggests who to look at — students who have gone quiet
          with a drive approaching. It suggests to you; it never messages them. A
          student who is struggling does not need an automated reminder that they
          are struggling.
        </p>
      </div>
    </>
  );
}

"use client";
import { AlertTriangle, Check, ChevronLeft, ChevronRight, Eye, X } from "lucide-react";

/**
 * The two pieces of exam chrome the runner was missing: a question map and a
 * real end-exam confirmation.
 *
 * Both are presentation only. The runner is a promise-driven sequence, so it
 * cannot jump backwards through items the way a paged test can — the map is a
 * status view with forward jumps offered only where the runner says they are
 * allowed, and it never claims a score before anything has been evaluated.
 */

export type MapStatus =
  | "answered"
  | "not_answered"
  | "current"
  | "unseen";

export interface MapEntry {
  id: string;
  /** 1-based position among examined items (warm-ups are not numbered). */
  no: number;
  sectionTitle: string;
  status: MapStatus;
}

const STATUS_COPY: Record<MapStatus, { label: string; color: string }> = {
  answered: { label: "Answered", color: "var(--rag-green)" },
  current: { label: "Current", color: "var(--primary)" },
  not_answered: { label: "Not answered", color: "var(--rag-red)" },
  unseen: { label: "Not reached", color: "var(--muted)" },
};

export function ExamMap({
  entries, open, onClose, onJump, examName, studentName, sectionTitle,
}: {
  entries: MapEntry[];
  open: boolean;
  onClose: () => void;
  /** Only ever called for items the runner considered reachable. */
  onJump: (index: number) => void;
  examName?: string;
  studentName?: string;
  sectionTitle?: string;
}) {
  if (!open) return null;

  const counts = entries.reduce<Record<string, number>>((acc, e) => {
    acc[e.status] = (acc[e.status] ?? 0) + 1;
    return acc;
  }, {});
  const total = entries.length;
  const answered = counts.answered ?? 0;
  const progress = total ? Math.round((answered / total) * 100) : 0;

  // Section grouping, in the order the sections appear.
  const sections: { title: string; items: (MapEntry & { index: number })[] }[] = [];
  entries.forEach((e, index) => {
    const last = sections[sections.length - 1];
    if (last && last.title === e.sectionTitle) last.items.push({ ...e, index });
    else sections.push({ title: e.sectionTitle, items: [{ ...e, index }] });
  });

  return (
    <>
      <div className="fixed inset-0 z-[60] bg-black/40" onClick={onClose} />
      <aside
        className="fixed right-0 top-0 bottom-0 z-[61] w-[19rem] max-w-[85vw] flex flex-col border-l border-border bg-surface"
        role="dialog"
        aria-label="Question map"
      >
        <header className="flex items-start justify-between gap-2 px-4 py-3 border-b border-border">
          <div className="min-w-0">
            <div className="text-xs font-bold">Question map</div>
            <div className="text-[10px] text-muted truncate">
              {examName || "Assessment"}{studentName ? ` · ${studentName}` : ""}
            </div>
          </div>
          <button onClick={onClose} className="btn btn-icon btn-ghost ds-focus shrink-0" aria-label="Close question map">
            <X size={16} />
          </button>
        </header>

        {/* Progress + counts, so "how far am I" is answerable at a glance. */}
        <div className="px-4 py-3 border-b border-border">
          <div className="flex items-center justify-between text-[11px] font-semibold">
            <span>{answered} answered</span>
            <span className="text-muted">{total} questions</span>
          </div>
          <div className="mt-2 h-1.5 rounded-full overflow-hidden" style={{ background: "var(--surface-2)" }}>
            <div className="h-full rounded-full" style={{ width: `${progress}%`, background: "var(--rag-green)" }} />
          </div>
          <div className="mt-3 grid grid-cols-2 gap-1.5 text-[10px]">
            {(["answered", "not_answered", "current", "unseen"] as MapStatus[]).map((s) => (
              <span key={s} className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ background: STATUS_COPY[s].color }} />
                <span className="text-muted">{STATUS_COPY[s].label}</span>
                <span className="font-bold ml-auto">{counts[s] ?? 0}</span>
              </span>
            ))}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto thin-scroll px-4 py-3 space-y-4">
          {sections.map((sec) => (
            <div key={sec.title}>
              <div className="text-[10px] font-bold uppercase tracking-wider mb-1.5" style={{ color: "var(--primary)" }}>
                {sec.title || sectionTitle || "Section"}
              </div>
              <div className="grid grid-cols-6 gap-1.5">
                {sec.items.map((e) => {
                  const reachable = e.status === "unseen";
                  return (
                    <button
                      key={e.id}
                      onClick={() => reachable && onJump(e.index)}
                      disabled={!reachable}
                      title={`${STATUS_COPY[e.status].label}${reachable ? " — jump here" : ""}`}
                      className="aspect-square rounded flex items-center justify-center text-[11px] font-bold transition-colors"
                      style={{
                        background: e.status === "current" ? "var(--primary)"
                          : e.status === "answered" ? "color-mix(in srgb, var(--rag-green) 22%, var(--surface))"
                          : e.status === "not_answered" ? "color-mix(in srgb, var(--rag-red) 16%, var(--surface))"
                          : "var(--surface-2)",
                        color: e.status === "current" ? "var(--on-primary)"
                          : e.status === "unseen" ? "var(--muted)" : "var(--fg)",
                        border: e.status === "current" ? "2px solid var(--primary)" : "1px solid var(--border)",
                        cursor: reachable ? "pointer" : "default",
                      }}
                    >
                      {e.status === "answered" ? <Check size={12} /> : e.no}
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>

        <footer className="px-4 py-3 border-t border-border text-[10px] text-muted leading-relaxed">
          Scores appear after your paper is evaluated — not here. Questions already
          answered cannot be revisited.
        </footer>
      </aside>
    </>
  );
}

/** Confirmation before the irreversible action, with the numbers that matter. */
export function EndExamDialog({
  open, answered, total, busy, onCancel, onConfirm, onReview,
}: {
  open: boolean;
  answered: number;
  total: number;
  busy?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
  onReview: () => void;
}) {
  if (!open) return null;
  const unanswered = Math.max(0, total - answered);

  return (
    <>
      <div className="fixed inset-0 z-[70] bg-black/50" onClick={onCancel} />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Submit exam"
        className="fixed z-[71] left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-[22rem] max-w-[92vw] rounded-xl border border-border bg-surface p-4"
        style={{ boxShadow: "0 24px 60px rgba(0,0,0,0.3)" }}
      >
        <div className="flex items-start gap-2">
          <span className="shrink-0 w-7 h-7 rounded-full flex items-center justify-center"
                style={{ background: "color-mix(in srgb, var(--rag-amber) 18%, var(--surface))", color: "var(--rag-amber)" }}>
            <AlertTriangle size={15} />
          </span>
          <div>
            <div className="text-sm font-bold">Submit your exam?</div>
            <div className="text-[11px] text-muted mt-1 leading-relaxed">
              This cannot be undone.
            </div>
          </div>
        </div>

        <div className="mt-3 grid grid-cols-2 gap-2 text-center">
          <div className="rounded-lg py-2" style={{ background: "color-mix(in srgb, var(--rag-green) 12%, var(--surface))" }}>
            <div className="text-lg font-black" style={{ color: "var(--rag-green)" }}>{answered}</div>
            <div className="text-[10px] font-semibold text-muted">Answered</div>
          </div>
          <div className="rounded-lg py-2" style={{ background: "color-mix(in srgb, var(--rag-red) 12%, var(--surface))" }}>
            <div className="text-lg font-black" style={{ color: "var(--rag-red)" }}>{unanswered}</div>
            <div className="text-[10px] font-semibold text-muted">Still unanswered</div>
          </div>
        </div>

        {unanswered > 0 && (
          <p className="text-[11px] mt-3" style={{ color: "var(--rag-amber)" }}>
            {unanswered} question{unanswered === 1 ? "" : "s"} will be marked as not answered.
          </p>
        )}

        <div className="mt-4 flex items-center gap-2">
          <button onClick={onCancel} className="btn btn-ghost btn-sm ds-focus flex-1" disabled={busy}>
            <ChevronLeft size={14} /> Keep going
          </button>
          <button onClick={onReview} className="btn btn-ghost btn-sm ds-focus flex-1" disabled={busy}
                  title="Open the question map to check what is left">
            <Eye size={14} /> Review
          </button>
          <button onClick={onConfirm} disabled={busy}
                  className="btn btn-sm ds-focus flex-1"
                  style={{ background: "var(--rag-red)", color: "#fff" }}>
            {busy ? "Submitting…" : "Submit"}
          </button>
        </div>
      </div>
    </>
  );
}

/** A compact "answered / total" chip for the exam header. */
export function ProgressChip({ answered, total, onClick }: {
  answered: number; total: number; onClick: () => void;
}) {
  return (
    <button onClick={onClick} className="chip ds-focus shrink-0" title="Open the question map"
            style={{ background: "var(--surface-2)", color: "var(--fg)" }}>
      <ChevronRight size={11} /> {answered}/{total}
    </button>
  );
}

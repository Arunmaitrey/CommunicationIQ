"use client";
import { useEffect, useState } from "react";
import { Layers, Archive, Trash2, Check, Clock, Filter } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { useToast } from "@/components/Toast";
import { ErrorNote, PageHeader, Skeleton } from "@/components/ui";
import { PLATFORM_ROLES } from "@/lib/roles";
import { API_BASE, getToken } from "@/lib/api";

const MODULES = ["reading", "listening", "writing", "speaking", "quiz"];
const STATUS_COLORS: Record<string, { bg: string; color: string }> = {
  active: { bg: "color-mix(in srgb, var(--rag-green) 12%, transparent)", color: "var(--rag-green)" },
  draft: { bg: "color-mix(in srgb, var(--rag-amber) 12%, transparent)", color: "var(--rag-amber)" },
  inactive: { bg: "color-mix(in srgb, var(--muted) 12%, transparent)", color: "var(--muted)" },
  archived: { bg: "color-mix(in srgb, var(--rag-red) 12%, transparent)", color: "var(--rag-red)" },
};
const MODULE_LABELS: Record<string, string> = {
  reading: "Reading", listening: "Listening", writing: "Writing",
  speaking: "Speaking", quiz: "Grammar & Vocabulary",
};

interface QuestionSetRow {
  id: string; set_number: string; module: string; company: string;
  question_count: number; question_numbers: string[];
  status: string; is_used: boolean; usage_count: number;
  last_used_at: string | null; created_at: string | null;
  linked_tests: { name: string; slug: string }[];
}

export default function SetsPage() {
  return (
    <RequireAuth roles={PLATFORM_ROLES}>
      <SetsManager />
    </RequireAuth>
  );
}

function SetsManager() {
  const { toast } = useToast();
  const [sets, setSets] = useState<QuestionSetRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [moduleFilter, setModuleFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [companyFilter, setCompanyFilter] = useState("");
  const [page, setPage] = useState(0);
  const PAGE_SIZE = 15;

  const loadSets = async () => {
    setLoading(true);
    const token = getToken();
    try {
      const params = new URLSearchParams();
      if (moduleFilter) params.set("module", moduleFilter);
      if (statusFilter) params.set("status", statusFilter);
      if (companyFilter) params.set("company", companyFilter);
      const res = await fetch(`${API_BASE}/platform/sets?${params}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error("Failed to load sets");
      setSets(await res.json());
      setPage(0);
    } catch (e) {
      setError((e instanceof Error ? e.message : String(e)));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadSets(); }, [moduleFilter, statusFilter, companyFilter]); // eslint-disable-line react-hooks/exhaustive-deps

  const updateSetStatus = async (setId: string, newStatus: string) => {
    const token = getToken();
    try {
      await fetch(`${API_BASE}/platform/sets/${setId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ status: newStatus }),
      });
      toast("success", `Set status changed to ${newStatus}`);
      loadSets();
    } catch (e) {
      toast("error", (e instanceof Error ? e.message : String(e)));
    }
  };

  const deleteSet = async (setId: string) => {
    if (!confirm("Delete this set?")) return;
    const token = getToken();
    try {
      const res = await fetch(`${API_BASE}/platform/sets/${setId}`, {
        method: "DELETE",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail || "Failed"); }
      toast("success", "Set deleted");
      loadSets();
    } catch (e) {
      toast("error", (e instanceof Error ? e.message : String(e)));
    }
  };

  const uniqueCompanies = Array.from(new Set(sets.map((s) => s.company || "General"))).sort();
  const pagedSets = sets.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const totalPages = Math.ceil(sets.length / PAGE_SIZE);

  return (
    <>
      <PageHeader
        title="Question Sets"
        sub={`${sets.length} sets. Sets of 10 questions auto-create when questions accumulate.`}
      />

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4">
        {MODULES.map((m) => {
          const count = sets.filter((s) => s.module === m).length;
          return (
            <div key={m} className="ds-card p-3 text-center">
              <div className="text-xs font-bold">{MODULE_LABELS[m]}</div>
              <div className="text-lg font-bold" style={{ color: "var(--primary)" }}>{count}</div>
            </div>
          );
        })}
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3 mb-4 flex-wrap">
        <select value={moduleFilter} onChange={(e) => setModuleFilter(e.target.value)}
          className="text-xs p-1.5 rounded border bg-transparent" style={{ borderColor: "var(--border)" }}>
          <option value="">All modules</option>
          {MODULES.map((m) => <option key={m} value={m}>{MODULE_LABELS[m]}</option>)}
        </select>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
          className="text-xs p-1.5 rounded border bg-transparent" style={{ borderColor: "var(--border)" }}>
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="draft">Draft</option>
          <option value="inactive">Inactive</option>
          <option value="archived">Archived</option>
        </select>
        <select value={companyFilter} onChange={(e) => setCompanyFilter(e.target.value)}
          className="text-xs p-1.5 rounded border bg-transparent" style={{ borderColor: "var(--border)" }}>
          <option value="">All companies</option>
          {uniqueCompanies.map((c) => <option key={c} value={c === "General" ? "" : c}>{c}</option>)}
        </select>
        <div className="flex items-center gap-1.5 ml-auto">
          <Filter size={12} className="text-muted" />
          <span className="text-[11px] text-muted">{sets.length} sets</span>
        </div>
      </div>

      {loading ? <Skeleton rows={5} /> : error ? <ErrorNote message={error} /> : (
        <div className="ds-card overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b" style={{ borderColor: "var(--border)" }}>
                <th className="text-left p-3 font-medium text-muted">Set Number</th>
                <th className="text-left p-3 font-medium text-muted">Module</th>
                <th className="text-left p-3 font-medium text-muted">Company</th>
                <th className="text-center p-3 font-medium text-muted">Questions</th>
                <th className="text-left p-3 font-medium text-muted">Status</th>
                <th className="text-center p-3 font-medium text-muted">Used</th>
                <th className="text-right p-3 font-medium text-muted">Actions</th>
              </tr>
            </thead>
            <tbody>
              {pagedSets.map((s) => {
                const sc = STATUS_COLORS[s.status] || STATUS_COLORS.draft;
                return (
                  <tr key={s.id} className="border-b last:border-0 hover:bg-surface2 transition-colors"
                    style={{ borderColor: "var(--border)" }}>
                    <td className="p-3 font-mono font-bold">{s.set_number}</td>
                    <td className="p-3">
                      <span className="px-1.5 py-0.5 rounded text-[10px] font-medium"
                        style={{ background: "color-mix(in srgb, var(--primary) 10%, transparent)", color: "var(--primary)" }}>
                        {MODULE_LABELS[s.module] || s.module}
                      </span>
                    </td>
                    <td className="p-3">
                      <span className="text-[11px]">{s.company || "General"}</span>
                    </td>
                    <td className="p-3 text-center font-bold">{s.question_count || 0}</td>
                    <td className="p-3">
                      <span className="px-1.5 py-0.5 rounded text-[9px] font-medium"
                        style={{ background: sc.bg, color: sc.color }}>
                        {s.status}
                      </span>
                    </td>
                    <td className="p-3 text-center">
                      {s.usage_count > 0 ? (
                        <span className="text-[10px] text-muted flex items-center justify-center gap-1">
                          <Clock size={10} /> {s.usage_count}x
                        </span>
                      ) : (
                        <span className="text-[10px] text-muted">—</span>
                      )}
                    </td>
                    <td className="p-3 text-right">
                      <div className="flex items-center justify-end gap-1">
                        {s.status === "active" ? (
                          <button onClick={() => updateSetStatus(s.id, "inactive")}
                            className="p-1.5 rounded hover:bg-surface2 text-muted" title="Deactivate">
                            <Archive size={13} />
                          </button>
                        ) : s.status === "inactive" || s.status === "draft" ? (
                          <button onClick={() => updateSetStatus(s.id, "active")}
                            className="p-1.5 rounded hover:bg-surface2" style={{ color: "var(--rag-green)" }} title="Activate">
                            <Check size={13} />
                          </button>
                        ) : null}
                        {(s.status === "draft" || (s.status === "active" && !s.usage_count)) && (
                          <button onClick={() => deleteSet(s.id)}
                            className="p-1.5 rounded hover:bg-surface2 text-muted hover:text-ragRed" title="Delete">
                            <Trash2 size={13} />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
              {pagedSets.length === 0 && (
                <tr>
                  <td colSpan={7} className="p-8 text-center">
                    <Layers size={32} className="mx-auto mb-2 text-muted" />
                    <div className="text-sm text-muted">No question sets found</div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between p-3 border-t" style={{ borderColor: "var(--border)" }}>
              <span className="text-[11px] text-muted">
                Showing {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, sets.length)} of {sets.length}
              </span>
              <div className="flex items-center gap-2">
                <button onClick={() => setPage(Math.max(0, page - 1))} disabled={page === 0}
                  className="px-2 py-1 text-[11px] rounded border disabled:opacity-40"
                  style={{ borderColor: "var(--border)" }}>Prev</button>
                <span className="text-[11px] text-muted">{page + 1}/{totalPages}</span>
                <button onClick={() => setPage(Math.min(totalPages - 1, page + 1))} disabled={page >= totalPages - 1}
                  className="px-2 py-1 text-[11px] rounded border disabled:opacity-40"
                  style={{ borderColor: "var(--border)" }}>Next</button>
              </div>
            </div>
          )}
        </div>
      )}
    </>
  );
}

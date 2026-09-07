"use client";
import { useState, useEffect } from "react";
import {
  Layers, Plus, Trash2, Play, Pause, Archive, RefreshCw, BookOpen, Headphones,
  PenLine, Mic, BarChart3,
} from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { PageHeader } from "@/components/ui";
import { PLATFORM_ROLES } from "@/lib/roles";
import { API_BASE, getToken } from "@/lib/api";
import { useToast } from "@/components/Toast";

export default function QuestionSetsPage() {
  return (
    <RequireAuth roles={PLATFORM_ROLES}>
      <QuestionSets />
    </RequireAuth>
  );
}

const MODULES = [
  { key: "reading", label: "Reading", icon: BookOpen, color: "var(--rag-green)" },
  { key: "listening", label: "Listening", icon: Headphones, color: "var(--rag-amber)" },
  { key: "writing", label: "Writing", icon: PenLine, color: "var(--accent)" },
  { key: "speaking", label: "Speaking", icon: Mic, color: "var(--secondary)" },
  { key: "quiz", label: "Quiz", icon: BarChart3, color: "var(--primary)" },
];

const STATUS_COLORS: Record<string, string> = {
  draft: "var(--muted)",
  active: "var(--rag-green)",
  inactive: "var(--rag-amber)",
  archived: "var(--rag-red)",
};

interface QuestionSetRow {
  id: string; set_number: string; module: string;
  question_ids: string[]; question_count: number;
  status: string; usage_count: number;
  last_used_at: string | null; created_at: string | null;
}

interface ModuleStat {
  total_questions: number; active_sets: number; draft_sets: number;
  questions_available: number;
}

interface AutoCreateResult { total_questions: number; existing_sets: number; created: number }

function QuestionSets() {
  const { toast } = useToast();
  const [sets, setSets] = useState<QuestionSetRow[]>([]);
  const [stats, setStats] = useState<Record<string, ModuleStat>>({});
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("");
  const [generating, setGenerating] = useState(false);
  const [genModule, setGenModule] = useState("reading");
  const [genCount, setGenCount] = useState(5);

  const load = async () => {
    setLoading(true);
    try {
      const token = getToken();
      const url = filter ? `${API_BASE}/platform/question-sets?module=${filter}` : `${API_BASE}/platform/question-sets`;
      const [setsRes, statsRes] = await Promise.all([
        fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} }),
        fetch(`${API_BASE}/platform/question-sets/stats`, { headers: token ? { Authorization: `Bearer ${token}` } : {} }),
      ]);
      if (setsRes.ok) setSets(await setsRes.json());
      if (statsRes.ok) setStats(await statsRes.json());
    } catch {}
    setLoading(false);
  };

  useEffect(() => { load(); }, [filter]); // eslint-disable-line react-hooks/exhaustive-deps

  const generateSets = async () => {
    setGenerating(true);
    try {
      const token = getToken();
      const res = await fetch(`${API_BASE}/platform/question-sets/generate?module=${genModule}&count=${genCount}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (res.ok) {
        toast("success", `Generated ${data.created} ${genModule} sets`);
        load();
      } else {
        toast("error", data.detail || "Failed to generate sets");
      }
    } catch { toast("error", "Failed to generate sets"); }
    setGenerating(false);
  };

  const autoCreate = async () => {
    setGenerating(true);
    try {
      const token = getToken();
      const res = await fetch(`${API_BASE}/platform/question-sets/auto-create`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (res.ok) {
        const results = data.results as Record<string, AutoCreateResult>;
        const total = Object.values(results).reduce((sum, r) => sum + (r.created || 0), 0);
        toast("success", `Auto-created ${total} sets across all modules`);
        load();
      }
    } catch { toast("error", "Failed to auto-create sets"); }
    setGenerating(false);
  };

  const updateStatus = async (id: string, status: string) => {
    const token = getToken();
    await fetch(`${API_BASE}/platform/question-sets/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ status }),
    });
    toast("success", `Set ${status}`);
    load();
  };

  const deleteSet = async (id: string) => {
    if (!confirm("Delete this set?")) return;
    const token = getToken();
    const res = await fetch(`${API_BASE}/platform/question-sets/${id}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) { toast("success", "Set deleted"); load(); }
    else { const d = await res.json(); toast("error", d.detail || "Cannot delete"); }
  };

  return (
    <>
      <PageHeader title="Question Sets" sub="Manage question sets for assessments" />

      {/* Stats Overview */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4">
        {MODULES.map((m) => {
          const s = stats[m.key] || {};
          return (
            <div key={m.key} className="ds-card p-3 text-center">
              <m.icon size={16} className="mx-auto mb-1" style={{ color: m.color }} />
              <div className="text-lg font-bold">{s.active_sets || 0}</div>
              <div className="text-[10px] text-muted">{m.label} sets</div>
              <div className="text-[9px] text-muted">{s.total_questions || 0} questions</div>
            </div>
          );
        })}
      </div>

      {/* Generate Sets */}
      <div className="ds-card p-4 mb-4">
        <div className="text-xs font-semibold mb-3">Generate New Sets</div>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="block text-[10px] text-muted mb-1">Module</label>
            <select value={genModule} onChange={(e) => setGenModule(e.target.value)}
              className="px-3 py-1.5 text-xs rounded border bg-transparent"
              style={{ borderColor: "var(--border)" }}>
              {MODULES.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-[10px] text-muted mb-1">Sets to create</label>
            <input type="number" value={genCount} onChange={(e) => setGenCount(+e.target.value)}
              min={1} max={50}
              className="w-20 px-3 py-1.5 text-xs rounded border bg-transparent"
              style={{ borderColor: "var(--border)" }} />
          </div>
          <button onClick={generateSets} disabled={generating}
            className="px-3 py-1.5 text-xs rounded-md text-white flex items-center gap-1.5 disabled:opacity-50"
            style={{ background: "var(--brand-grad)" }}>
            <Plus size={12} /> {generating ? "Generating..." : "Generate Sets"}
          </button>
          <button onClick={autoCreate} disabled={generating}
            className="px-3 py-1.5 text-xs rounded-md border flex items-center gap-1.5 disabled:opacity-50"
            style={{ borderColor: "var(--border)" }}>
            <RefreshCw size={12} /> Auto-Create All
          </button>
        </div>
      </div>

      {/* Filter */}
      <div className="flex gap-2 mb-4">
        <button onClick={() => setFilter("")}
          className={`px-3 py-1.5 text-xs rounded-md border ${!filter ? "font-bold" : ""}`}
          style={{ borderColor: !filter ? "var(--primary)" : "var(--border)" }}>
          All ({sets.length})
        </button>
        {MODULES.map((m) => (
          <button key={m.key} onClick={() => setFilter(m.key)}
            className={`px-3 py-1.5 text-xs rounded-md border ${filter === m.key ? "font-bold" : ""}`}
            style={{ borderColor: filter === m.key ? m.color : "var(--border)" }}>
            {m.label}
          </button>
        ))}
      </div>

      {/* Sets List */}
      {loading ? (
        <div className="text-xs text-muted p-4">Loading...</div>
      ) : sets.length === 0 ? (
        <div className="ds-card p-8 text-center">
          <Layers size={32} className="mx-auto mb-2 text-muted" />
          <div className="text-sm text-muted mb-2">No question sets yet</div>
          <div className="text-[11px] text-muted">Generate sets from the question bank above</div>
        </div>
      ) : (
        <div className="space-y-2">
          {sets.map((s) => {
            const mod = MODULES.find((m) => m.key === s.module);
            return (
              <div key={s.id} className="ds-card p-3 flex items-center gap-3">
                {mod && <mod.icon size={14} style={{ color: mod.color }} />}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold">{s.set_number}</span>
                    <span className="px-1.5 py-0.5 rounded text-[9px] font-medium"
                      style={{ background: STATUS_COLORS[s.status] + "20", color: STATUS_COLORS[s.status] }}>
                      {s.status.toUpperCase()}
                    </span>
                  </div>
                  <div className="text-[10px] text-muted">
                    {s.question_count} questions · Used {s.usage_count} times
                    {s.last_used_at && ` · Last: ${new Date(s.last_used_at).toLocaleDateString()}`}
                  </div>
                </div>
                <div className="flex items-center gap-1">
                  {s.status === "draft" && (
                    <button onClick={() => updateStatus(s.id, "active")}
                      className="p-1.5 rounded hover:bg-surface2 text-muted" title="Activate">
                      <Play size={12} />
                    </button>
                  )}
                  {s.status === "active" && (
                    <button onClick={() => updateStatus(s.id, "inactive")}
                      className="p-1.5 rounded hover:bg-surface2 text-muted" title="Deactivate">
                      <Pause size={12} />
                    </button>
                  )}
                  {s.status !== "archived" && (
                    <button onClick={() => updateStatus(s.id, "archived")}
                      className="p-1.5 rounded hover:bg-surface2 text-muted" title="Archive">
                      <Archive size={12} />
                    </button>
                  )}
                  {(s.status === "draft" || s.status === "inactive") && (
                    <button onClick={() => deleteSet(s.id)}
                      className="p-1.5 rounded hover:bg-surface2 text-muted hover:text-ragRed" title="Delete">
                      <Trash2 size={12} />
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </>
  );
}

"use client";
import { useCallback, useEffect, useState } from "react";
import {
  Building2, Plus, Pencil, Trash2, X, Loader2, ChevronDown, ChevronRight,
  BookOpen, Mic, Headphones, PenLine, FileText,
} from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { useToast } from "@/components/Toast";
import { ErrorNote, PageHeader, Skeleton } from "@/components/ui";
import { PLATFORM_ROLES } from "@/lib/roles";
import { API_BASE, getToken } from "@/lib/api";

interface Company {
  id: string; name: string; slug: string; color: string;
  description: string; is_active: boolean;
  question_counts: Record<string, number>;
}

const MOD_ICONS: Record<string, any> = {
  reading: BookOpen, listening: Headphones, writing: PenLine, speaking: Mic, quiz: FileText,
};
const MOD_COLORS: Record<string, string> = {
  reading: "var(--rag-green)", listening: "var(--rag-amber)",
  writing: "var(--accent)", speaking: "var(--secondary)", quiz: "var(--primary)",
};
const MOD_LABELS: Record<string, string> = {
  reading: "Reading", listening: "Listening", writing: "Writing",
  speaking: "Speaking", quiz: "Grammar & Vocabulary (MCQ)",
};
const MODULES = ["reading", "listening", "writing", "speaking", "quiz"];

export default function CompaniesPage() {
  return (
    <RequireAuth roles={PLATFORM_ROLES}>
      <Companies />
    </RequireAuth>
  );
}

function Companies() {
  const { toast } = useToast();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [editing, setEditing] = useState<Company | null>(null);
  const [expandedCompany, setExpandedCompany] = useState<string | null>(null);
  const [companySets, setCompanySets] = useState<Record<string, any[]>>({});
  const [loadingSets, setLoadingSets] = useState(false);

  const loadCompanies = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const token = getToken();
      const res = await fetch(`${API_BASE}/platform/companies`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error("Failed to load companies");
      setCompanies(await res.json());
    } catch {
      setError("Could not load companies");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadCompanies(); }, [loadCompanies]);

  async function loadCompanySets(companyName: string) {
    if (companySets[companyName]) return;
    setLoadingSets(true);
    try {
      const token = getToken();
      const res = await fetch(`${API_BASE}/platform/sets?company=${encodeURIComponent(companyName)}&status=active&limit=5000`,
        { headers: token ? { Authorization: `Bearer ${token}` } : {} });
      if (!res.ok) throw new Error("Failed");
      const d = await res.json();
      setCompanySets(prev => ({ ...prev, [companyName]: Array.isArray(d) ? d : [] }));
    } catch { /* ignore */ }
    finally { setLoadingSets(false); }
  }

  async function handleCreate(name: string, color: string, description: string) {
    try {
      const token = getToken();
      const res = await fetch(`${API_BASE}/platform/companies`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ name, color, description }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to create");
      toast("success", `Company "${name}" created`);
      setShowCreate(false);
      loadCompanies();
    } catch (e: any) { toast("error", e.message); }
  }

  async function handleUpdate(id: string, body: Record<string, unknown>) {
    try {
      const token = getToken();
      const res = await fetch(`${API_BASE}/platform/companies/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error("Failed to update");
      toast("success", "Company updated");
      setEditing(null);
      loadCompanies();
    } catch (e: any) { toast("error", e.message); }
  }

  async function handleDelete(id: string, name: string) {
    if (!confirm(`Deactivate "${name}"? It will be hidden from students but questions remain.`)) return;
    try {
      const token = getToken();
      const res = await fetch(`${API_BASE}/platform/companies/${id}`, {
        method: "DELETE", headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Failed to delete");
      toast("success", `Company "${name}" deactivated`);
      loadCompanies();
    } catch (e: any) { toast("error", e.message); }
  }

  async function toggleActive(company: Company) {
    try {
      const token = getToken();
      const res = await fetch(`${API_BASE}/platform/companies/${company.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ is_active: !company.is_active }),
      });
      if (!res.ok) throw new Error("Failed to update");
      toast("success", company.is_active
        ? `Company "${company.name}" deactivated`
        : `Company "${company.name}" activated`);
      loadCompanies();
    } catch (e: any) { toast("error", e.message); }
  }

  const totalQuestions = companies.reduce((sum, c) => sum + (c.question_counts?.total || 0), 0);

  if (loading) return <Skeleton rows={5} />;
  if (error) return <ErrorNote message={error} />;

  const CATEGORIES = [
    { key: "reading", label: "Reading", icon: BookOpen, color: "var(--rag-green)" },
    { key: "listening", label: "Listening", icon: Headphones, color: "var(--rag-amber)" },
    { key: "speaking", label: "Speaking", icon: Mic, color: "var(--secondary)" },
    { key: "writing", label: "Writing", icon: PenLine, color: "var(--accent)" },
    { key: "quiz", label: "Grammar & Vocabulary (MCQ)", icon: FileText, color: "var(--primary)" },
  ];

  return (
    <>
      <PageHeader
        title="Company Management"
        sub={`${companies.filter(c => c.is_active).length} active companies · ${totalQuestions} total questions across all companies`}
        action={
          <button onClick={() => setShowCreate(true)}
            className="btn btn-primary btn-sm flex items-center gap-1.5">
            <Plus size={14} /> Add Company
          </button>
        }
      />

      <div className="space-y-3">
        {companies.map((company) => {
          const counts = company.question_counts || {};
          const isExpanded = expandedCompany === company.id;
          const sets = companySets[company.name] || [];
          const setsByModule: Record<string, any[]> = {};
          sets.forEach(s => {
            if (!setsByModule[s.module]) setsByModule[s.module] = [];
            setsByModule[s.module].push(s);
          });
          return (
            <div key={company.id} className={`ds-card overflow-hidden ${!company.is_active ? "opacity-50" : ""}`}>
              <div
                className="flex items-center gap-4 p-4 cursor-pointer hover:bg-surface2 transition-colors"
                onClick={() => {
                  setExpandedCompany(isExpanded ? null : company.id);
                  if (!isExpanded && !companySets[company.name]) loadCompanySets(company.name);
                }}
              >
                <div className="w-10 h-10 rounded-lg flex items-center justify-center shrink-0"
                  style={{ background: company.color + "20" }}>
                  <Building2 size={20} style={{ color: company.color }} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-bold">{company.name}</span>
                    {!company.is_active && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-surface2 text-muted">Inactive</span>
                    )}
                    <span className="text-[10px] px-1.5 py-0.5 rounded-full font-medium"
                      style={{ background: company.color + "20", color: company.color }}>
                      {counts.total || 0} questions
                    </span>
                  </div>
                  {company.description && (
                    <p className="text-[11px] text-muted mt-1 truncate">{company.description}</p>
                  )}
                  <div className="flex gap-3 mt-2">
                    {CATEGORIES.map(({ key, label, icon: CIcon, color }) => (
                      <span key={key} className="flex items-center gap-1 text-[10px]" style={{ color }}>
                        <CIcon size={10} /> {label.replace("Grammar & Vocabulary (MCQ)", "Grammar")}: <strong>{counts[key] || 0}</strong>
                      </span>
                    ))}
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {isExpanded ? <ChevronDown size={16} className="text-muted" /> : <ChevronRight size={16} className="text-muted" />}
                  <button onClick={(e) => { e.stopPropagation(); toggleActive(company); }}
                    className="px-2 py-1.5 rounded text-[10px] font-semibold text-white"
                    style={{ background: company.is_active ? "var(--rag-red)" : "var(--rag-green)" }}>
                    {company.is_active ? "Deactivate" : "Activate"}
                  </button>
                  <button onClick={(e) => { e.stopPropagation(); setEditing(company); }}
                    className="p-2 rounded hover:bg-surface2 transition-colors text-muted hover:text-text">
                    <Pencil size={14} />
                  </button>
                  <button onClick={(e) => { e.stopPropagation(); handleDelete(company.id, company.name); }}
                    className="p-2 rounded hover:bg-surface2 transition-colors text-muted hover:text-ragRed">
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>

              {isExpanded && (
                <div className="border-t p-4" style={{ borderColor: "var(--border)" }}>
                  {loadingSets && !companySets[company.name] ? (
                    <div className="text-xs text-muted flex items-center gap-2">
                      <Loader2 size={12} className="animate-spin" /> Loading sets...
                    </div>
                  ) : (
                    <CompanySetView setsByModule={setsByModule} companyColor={company.color} />
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {showCreate && <CompanyModal onClose={() => setShowCreate(false)} onSave={handleCreate} />}
      {editing && (
        <CompanyModal company={editing} onClose={() => setEditing(null)}
          onSave={(name, color, desc) => handleUpdate(editing.id, { name, color, description: desc })} />
      )}
    </>
  );
}

function CompanySetView({ setsByModule, companyColor }: { setsByModule: Record<string, any[]>; companyColor: string }) {
  const [expandedSetIdx, setExpandedSetIdx] = useState<number | null>(null);
  const [expandedModule, setExpandedModule] = useState<string | null>(null);
  const [setQuestions, setSetQuestions] = useState<Record<string, any[]>>({});
  const [loadingQs, setLoadingQs] = useState<string | null>(null);

  // Group sets by position across modules
  const maxSets = Math.max(...MODULES.map(m => (setsByModule[m] || []).length), 0);
  if (maxSets === 0) return <div className="text-xs text-muted">No sets available</div>;

  async function loadQs(setId: string) {
    if (setQuestions[setId]) return;
    setLoadingQs(setId);
    try {
      const token = getToken();
      const res = await fetch(`${API_BASE}/platform/sets/${setId}/questions`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (res.ok) {
        const qs = await res.json();
        setSetQuestions(prev => ({ ...prev, [setId]: qs }));
      }
    } catch {}
    setLoadingQs(null);
  }

  function handleSetClick(idx: number) {
    if (expandedSetIdx === idx) {
      setExpandedSetIdx(null);
      setExpandedModule(null);
    } else {
      setExpandedSetIdx(idx);
      setExpandedModule(null);
      // Load questions for all modules in this set
      MODULES.forEach(m => {
        const s = (setsByModule[m] || [])[idx];
        if (s) loadQs(s.id);
      });
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-1.5">
        {Array.from({ length: maxSets }, (_, i) => (
          <button
            key={i}
            onClick={() => handleSetClick(i)}
            className="px-3 py-1.5 rounded text-xs font-semibold border transition-colors"
            style={{
              borderColor: expandedSetIdx === i ? companyColor : companyColor + "40",
              background: expandedSetIdx === i ? companyColor + "20" : companyColor + "10",
              color: companyColor,
            }}>
            Set {i + 1}
            {expandedSetIdx === i ? " ▾" : " ▸"}
          </button>
        ))}
      </div>

      {expandedSetIdx !== null && (
        <div className="space-y-2 ml-2">
          {MODULES.map(m => {
            const s = (setsByModule[m] || [])[expandedSetIdx];
            if (!s) return null;
            const Icon = MOD_ICONS[m] || FileText;
            const color = MOD_COLORS[m] || "var(--muted)";
            const qs = setQuestions[s.id];
            const isLoading = loadingQs === s.id;
            const isModuleExpanded = expandedModule === m;
            return (
              <div key={m} className="border rounded p-2" style={{ borderColor: color + "30" }}>
                <div
                  className="flex items-center gap-2 cursor-pointer"
                  onClick={() => setExpandedModule(isModuleExpanded ? null : m)}>
                  <Icon size={12} style={{ color }} />
                  <span className="text-[11px] font-semibold" style={{ color }}>{MOD_LABELS[m]}</span>
                  <span className="text-[10px] text-muted">{s.set_number} · {s.question_count}q</span>
                  {isModuleExpanded ? <ChevronDown size={10} className="text-muted ml-auto" /> : <ChevronRight size={10} className="text-muted ml-auto" />}
                </div>
                {isModuleExpanded && (
                  <div className="mt-1.5 space-y-0.5">
                    {isLoading ? (
                      <div className="flex items-center gap-1 text-[9px] text-muted py-1">
                        <Loader2 size={8} className="animate-spin" /> Loading...
                      </div>
                    ) : qs && qs.length > 0 ? (
                      qs.map((q: any, qi: number) => (
                        <div key={qi} className="text-[9px] text-muted pl-4 truncate max-w-[300px]"
                          title={q.body || q.title || ""}>
                          {qi + 1}. {q.title || q.stem || q.prompt_text || q.prompt || "Untitled"}
                        </div>
                      ))
                    ) : (
                      <div className="text-[9px] text-muted pl-4">No questions</div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function CompanyModal({ company, onClose, onSave }: {
  company?: Company; onClose: () => void; onSave: (name: string, color: string, description: string) => void;
}) {
  const [name, setName] = useState(company?.name || "");
  const [color, setColor] = useState(company?.color || "#6366f1");
  const [desc, setDesc] = useState(company?.description || "");
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div className="ds-card p-6 w-full max-w-md" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-bold">{company ? "Edit Company" : "New Company"}</h3>
          <button onClick={onClose} className="p-1 rounded hover:bg-surface2"><X size={14} /></button>
        </div>
        <label className="block text-[11px] font-semibold text-muted mb-1">Name</label>
        <input value={name} onChange={(e) => setName(e.target.value)}
          className="w-full px-3 py-2 text-xs rounded border bg-transparent mb-3" style={{ borderColor: "var(--border)" }}
          placeholder="e.g. Accenture" />
        <label className="block text-[11px] font-semibold text-muted mb-1">Color</label>
        <div className="flex items-center gap-2 mb-3">
          <input type="color" value={color} onChange={(e) => setColor(e.target.value)}
            className="w-8 h-8 rounded border cursor-pointer" style={{ borderColor: "var(--border)" }} />
          <span className="text-[11px] text-muted font-mono">{color}</span>
        </div>
        <label className="block text-[11px] font-semibold text-muted mb-1">Description</label>
        <textarea value={desc} onChange={(e) => setDesc(e.target.value)}
          className="w-full px-3 py-2 text-xs rounded border bg-transparent mb-4" style={{ borderColor: "var(--border)" }}
          rows={3} placeholder="Optional description" />
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-3 py-1.5 text-xs rounded border" style={{ borderColor: "var(--border)" }}>Cancel</button>
          <button onClick={() => { if (name.trim()) onSave(name.trim(), color, desc); }}
            disabled={!name.trim()}
            className="px-3 py-1.5 text-xs font-semibold rounded text-white disabled:opacity-50"
            style={{ background: "var(--brand-grad)" }}>
            {company ? "Save" : "Create"}
          </button>
        </div>
      </div>
    </div>
  );
}

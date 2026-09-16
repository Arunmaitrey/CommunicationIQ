"use client";
import { useEffect, useState } from "react";
import { Layers, Play, CheckCircle, Plus, X, Loader2, Trash2 } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { ErrorNote, PageHeader, Section, Skeleton } from "@/components/ui";
import { useToast } from "@/components/Toast";
import { api, API_BASE, getToken } from "@/lib/api";

export default function TenantProfilesPage() {
  return (
    <RequireAuth roles={["tenant_admin"]}>
      <ProfilesList />
    </RequireAuth>
  );
}

function ProfilesList() {
  const [profiles, setProfiles] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showCreate, setShowCreate] = useState(false);

  const loadData = async () => {
    setLoading(true);
    try {
      const data = await api.tenantProfiles();
      setProfiles(data);
    } catch (e: any) {
      setError(e?.message || "Failed to load");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadData(); }, []);

  if (loading) return <Skeleton rows={5} />;
  if (error) return <ErrorNote message={error} />;

  const grouped: Record<string, any[]> = {};
  for (const p of profiles) {
    const key = p.style || "other";
    (grouped[key] ||= []).push(p);
  }

  const styleLabels: Record<string, string> = {
    diagnostic: "Diagnostic Tests",
    practice: "Practice Assessments",
    company: "Company-Specific Rounds",
  };

  return (
    <>
      <PageHeader
        title="Assessments"
        sub={`${profiles.length} assessment${profiles.length !== 1 ? "s" : ""} available for your institution.`}
      />

      <div className="mb-4">
        <button onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 px-4 py-2 text-xs font-semibold rounded-lg transition-colors"
          style={{ background: "var(--brand-grad)", color: "white" }}>
          <Plus size={14} />
          Create Assessment
        </button>
      </div>

      {Object.entries(grouped).map(([style, items]) => (
        <Section key={style} title={styleLabels[style] || style} className="mb-4">
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {items.map((p) => (
              <div key={p.id} className="ds-card p-4">
                <div className="flex items-start justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <Layers size={14} style={{ color: "var(--primary)" }} />
                    <span className="text-sm font-bold">{p.name}</span>
                  </div>
                  {p.status === "published" ? (
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-[var(--rag-green)]/10 text-[var(--rag-green)]">Active</span>
                  ) : (
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-surface2 text-muted">{p.status}</span>
                  )}
                </div>
                {p.description && (
                  <p className="text-xs text-muted mb-2 line-clamp-2">{p.description}</p>
                )}
                <div className="flex items-center gap-3 text-[11px] text-muted">
                  <span>{p.estimated_minutes} min</span>
                  {p.is_baseline && <span className="font-medium text-[var(--primary)]">Baseline</span>}
                  {p.sections && <span>{p.sections.length} sections</span>}
                </div>
                {p.sections && p.sections.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {p.sections.map((s: any) => (
                      <span key={s.id} className="px-1.5 py-0.5 rounded text-[10px] bg-surface2 text-muted">
                        {s.title}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </Section>
      ))}

      {profiles.length === 0 && (
        <div className="ds-card p-8 text-center text-sm text-muted">
          No assessments configured yet. Create one above.
        </div>
      )}

      {showCreate && (
        <CreateAssessmentModal
          onClose={() => setShowCreate(false)}
          onCreated={() => { setShowCreate(false); loadData(); }}
        />
      )}
    </>
  );
}

function CreateAssessmentModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    name: "",
    description: "",
    style: "practice",
    is_baseline: false,
    estimated_minutes: 30,
  });
  const [sections, setSections] = useState([
    { title: "Reading", task_type: "reading_comprehension", item_count: 10, weight: 10, response_seconds: 0, prep_seconds: 0, prompt_plays_allowed: 0, allow_replay: false, instructions: "Read the passage and answer questions." },
    { title: "Listening", task_type: "listening_comprehension", item_count: 10, weight: 10, response_seconds: 30, prep_seconds: 0, prompt_plays_allowed: 1, allow_replay: false, instructions: "Listen to the audio and answer questions." },
    { title: "Writing", task_type: "writing", item_count: 10, weight: 10, response_seconds: 120, prep_seconds: 0, prompt_plays_allowed: 0, allow_replay: false, instructions: "Write a response to the prompt." },
  ]);

  const set = (k: string, v: any) => setForm((f) => ({ ...f, [k]: v }));
  const setSection = (i: number, k: string, v: any) => {
    setSections((prev) => {
      const next = [...prev];
      next[i] = { ...next[i], [k]: v };
      return next;
    });
  };
  const addSection = () => setSections((prev) => [
    ...prev,
    { title: "New Section", task_type: "reading_comprehension", item_count: 5, weight: 1, response_seconds: 30, prep_seconds: 0, prompt_plays_allowed: 0, allow_replay: false, instructions: "" },
  ]);
  const removeSection = (i: number) => setSections((prev) => prev.filter((_, idx) => idx !== i));

  const handleSubmit = async () => {
    if (!form.name.trim()) { setError("Name is required"); return; }
    if (sections.length === 0) { setError("At least one section is required"); return; }
    setLoading(true);
    setError("");
    const token = getToken();
    try {
      const body = {
        ...form,
        sections: sections.map((s, i) => ({ ...s, position: i })),
      };
      const res = await fetch(`${API_BASE}/tenant/profiles`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Failed" }));
        throw new Error(err.detail || "Failed to create assessment");
      }
      toast("success", "Assessment created");
      onCreated();
    } catch (e: any) {
      setError(e.message);
      toast("error", e.message);
    } finally { setLoading(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div className="bg-white rounded-lg p-6 w-full max-w-lg max-h-[90vh] overflow-y-auto shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-bold">Create Assessment</h2>
          <button onClick={onClose} className="text-muted hover:text-foreground"><X size={16} /></button>
        </div>
        {error && (
          <div className="text-xs mb-3 p-2 rounded" style={{ background: "color-mix(in srgb, var(--rag-red) 10%, transparent)", color: "var(--rag-red)" }}>{error}</div>
        )}
        <div className="space-y-3">
          <label className="block">
            <span className="text-[11px] text-muted font-medium">Name *</span>
            <input value={form.name} onChange={(e) => set("name", e.target.value)}
              className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }}
              placeholder="e.g., Professional English" />
          </label>
          <label className="block">
            <span className="text-[11px] text-muted font-medium">Description</span>
            <textarea value={form.description} onChange={(e) => set("description", e.target.value)}
              className="w-full text-xs p-2 rounded border bg-transparent mt-1 min-h-[60px]" style={{ borderColor: "var(--border)" }}
              placeholder="What this assessment covers..." />
          </label>
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="text-[11px] text-muted font-medium">Type</span>
              <select value={form.style} onChange={(e) => set("style", e.target.value)}
                className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }}>
                <option value="practice">Practice</option>
                <option value="diagnostic">Diagnostic</option>
                <option value="company">Company</option>
              </select>
            </label>
            <label className="block">
              <span className="text-[11px] text-muted font-medium">Est. Minutes</span>
              <input type="number" value={form.estimated_minutes} onChange={(e) => set("estimated_minutes", parseInt(e.target.value))}
                className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }} />
            </label>
          </div>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={form.is_baseline} onChange={(e) => set("is_baseline", e.target.checked)} className="rounded" />
            <span className="text-[11px] text-muted font-medium">Baseline test (taken once before training)</span>
          </label>

          <div className="pt-2 border-t" style={{ borderColor: "var(--border)" }}>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-bold">Sections</span>
              <button onClick={addSection} className="text-[11px] font-semibold flex items-center gap-1" style={{ color: "var(--primary)" }}>
                <Plus size={12} /> Add Section
              </button>
            </div>
            <div className="space-y-2">
              {sections.map((s, i) => (
                <div key={i} className="p-2 rounded border" style={{ borderColor: "var(--border)" }}>
                  <div className="flex items-center justify-between mb-2">
                    <input value={s.title} onChange={(e) => setSection(i, "title", e.target.value)}
                      className="text-[11px] font-bold bg-transparent border-b border-transparent focus:border-current outline-none" style={{ borderColor: "var(--border)" }} />
                    {sections.length > 1 && (
                      <button onClick={() => removeSection(i)} className="text-muted hover:text-ragRed"><Trash2 size={11} /></button>
                    )}
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    <label className="block">
                      <span className="text-[9px] text-muted">Questions</span>
                      <input type="number" value={s.item_count} onChange={(e) => setSection(i, "item_count", parseInt(e.target.value))}
                        className="w-full text-[11px] p-1 rounded border bg-transparent" style={{ borderColor: "var(--border)" }} />
                    </label>
                    <label className="block">
                      <span className="text-[9px] text-muted">Weight</span>
                      <input type="number" value={s.weight} onChange={(e) => setSection(i, "weight", parseFloat(e.target.value))}
                        className="w-full text-[11px] p-1 rounded border bg-transparent" style={{ borderColor: "var(--border)" }} />
                    </label>
                    <label className="block">
                      <span className="text-[9px] text-muted">Sec/Answer</span>
                      <input type="number" value={s.response_seconds} onChange={(e) => setSection(i, "response_seconds", parseInt(e.target.value))}
                        className="w-full text-[11px] p-1 rounded border bg-transparent" style={{ borderColor: "var(--border)" }} />
                    </label>
                  </div>
                  <label className="mt-1 block">
                    <span className="text-[9px] text-muted">Task Type</span>
                    <select value={s.task_type} onChange={(e) => setSection(i, "task_type", e.target.value)}
                      className="w-full text-[11px] p-1 rounded border bg-transparent" style={{ borderColor: "var(--border)" }}>
                      <option value="reading_comprehension">Reading</option>
                      <option value="listening_comprehension">Listening</option>
                      <option value="writing">Writing</option>
                      <option value="open_response">Speaking</option>
                      <option value="read_aloud">Speaking (Read Aloud)</option>
                      <option value="repeat_sentence">Speaking (Repeat)</option>
                      <option value="short_answer">Speaking (Short Answer)</option>
                    </select>
                  </label>
                </div>
              ))}
            </div>
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-5 pt-4 border-t" style={{ borderColor: "var(--border)" }}>
          <button onClick={onClose} disabled={loading} className="px-4 py-2 text-xs rounded-md bg-surface2 text-muted">Cancel</button>
          <button onClick={handleSubmit} disabled={loading}
            className="px-4 py-2 text-xs rounded-md text-white disabled:opacity-50 flex items-center gap-2"
            style={{ background: "var(--primary)" }}>
            {loading ? <><Loader2 size={12} className="animate-spin" /> Creating...</> : "Create Assessment"}
          </button>
        </div>
      </div>
    </div>
  );
}

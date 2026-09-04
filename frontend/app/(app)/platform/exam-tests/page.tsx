"use client";
import { useState, useEffect } from "react";
import {
  ClipboardList, Plus, X, Trash2, Save, BookOpen, Headphones, PenLine, Mic, Clock, Edit,
} from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { PageHeader } from "@/components/ui";
import { PLATFORM_ROLES } from "@/lib/roles";
import { API_BASE, getToken } from "@/lib/api";
import { useToast } from "@/components/Toast";

export default function ExamTestsPage() {
  return (
    <RequireAuth roles={PLATFORM_ROLES}>
      <ExamTests />
    </RequireAuth>
  );
}

const SECTION_FIELDS = [
  { key: "reading_questions", label: "Reading Questions", icon: BookOpen, color: "var(--rag-green)" },
  { key: "listening_questions", label: "Listening Questions", icon: Headphones, color: "var(--rag-amber)" },
  { key: "writing_questions", label: "Writing Questions", icon: PenLine, color: "var(--accent)" },
  { key: "speaking_questions", label: "Speaking Questions", icon: Mic, color: "var(--secondary)" },
];

const TIME_FIELDS = [
  { key: "reading_seconds", label: "Reading Time" },
  { key: "listening_seconds", label: "Listening Time" },
  { key: "writing_seconds", label: "Writing Time" },
  { key: "speaking_seconds", label: "Speaking Time" },
];

function ExamTests() {
  const { toast } = useToast();
  const [tests, setTests] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<any>(null);
  const [setSummary, setSetSummary] = useState<Record<string, any>>({});
  const [companySetSummary, setCompanySetSummary] = useState<Record<string, Record<string, any>>>({});
  const [form, setForm] = useState({
    name: "", description: "", duration_minutes: 30,
    reading_questions: 10, listening_questions: 10,
    writing_questions: 10, speaking_questions: 0,
    reading_seconds: 600, listening_seconds: 600,
    writing_seconds: 600, speaking_seconds: 0,
    allow_pause: false, show_timer: true, one_shot_audio: true,
    is_active: true, is_baseline: false, company: "",
  });

  const load = async () => {
    setLoading(true);
    try {
      const token = getToken();
      const [testsRes, setsRes, companySetsRes] = await Promise.all([
        fetch(`${API_BASE}/platform/exam-tests`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        }),
        fetch(`${API_BASE}/platform/sets/summary`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        }),
        fetch(`${API_BASE}/platform/sets/summary-by-company`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        }),
      ]);
      if (testsRes.ok) {
        const allTests = await testsRes.json();
        setTests(allTests);
      }
      if (setsRes.ok) setSetSummary(await setsRes.json());
      if (companySetsRes.ok) setCompanySetSummary(await companySetsRes.json());
    } catch {}
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const set = (k: string, v: any) => setForm((prev) => ({ ...prev, [k]: v }));

  const save = async () => {
    if (!form.name.trim()) { toast("error", "Name required"); return; }
    const token = getToken();
    const body = { ...form };
    try {
      let res;
      if (editing) {
        res = await fetch(`${API_BASE}/platform/exam-tests/${editing.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
          body: JSON.stringify(body),
        });
      } else {
        res = await fetch(`${API_BASE}/platform/exam-tests`, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
          body: JSON.stringify(body),
        });
      }
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Failed to save");
      }
      toast("success", editing ? "Test updated" : "Test created");
      setShowForm(false);
      setEditing(null);
      load();
    } catch (e: any) {
      toast("error", e.message || "Failed to save");
    }
  };

  const remove = async (id: string) => {
    if (!confirm("Delete this test?")) return;
    const token = getToken();
    await fetch(`${API_BASE}/platform/exam-tests/${id}`, {
      method: "DELETE",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    toast("success", "Test deleted");
    load();
  };

  /** Flip a test's visibility. Only active tests are published to students —
   *  deactivating retires the synced SimulationProfile so the change shows up
   *  on the student side immediately, without a backend restart. */
  const toggleActive = async (t: any) => {
    const token = getToken();
    try {
      const body = {
        name: t.name, description: t.description || "", duration_minutes: t.duration_minutes,
        reading_questions: t.reading_questions, listening_questions: t.listening_questions,
        writing_questions: t.writing_questions, speaking_questions: t.speaking_questions,
        reading_seconds: t.reading_seconds, listening_seconds: t.listening_seconds,
        writing_seconds: t.writing_seconds, speaking_seconds: t.speaking_seconds,
        allow_pause: t.allow_pause, show_timer: t.show_timer, one_shot_audio: t.one_shot_audio,
        is_active: !t.is_active, is_baseline: t.is_baseline, company: t.company || "",
        question_ids: t.question_ids || {},
      };
      const res = await fetch(`${API_BASE}/platform/exam-tests/${t.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Failed to update");
      }
      toast("success", t.is_active ? "Test deactivated — hidden from students" : "Test activated — live for students");
      load();
    } catch (e: any) {
      toast("error", e.message || "Failed to update");
    }
  };

  const startEdit = (t: any) => {
    setEditing(t);
    setForm({
      name: t.name, description: t.description || "", duration_minutes: t.duration_minutes,
      reading_questions: t.reading_questions, listening_questions: t.listening_questions,
      writing_questions: t.writing_questions, speaking_questions: t.speaking_questions,
      reading_seconds: t.reading_seconds, listening_seconds: t.listening_seconds,
      writing_seconds: t.writing_seconds, speaking_seconds: t.speaking_seconds,
      allow_pause: t.allow_pause, show_timer: t.show_timer, one_shot_audio: t.one_shot_audio,
      is_active: t.is_active, is_baseline: t.is_baseline, company: t.company || "",
    });
    setShowForm(true);
  };

  const totalQ = form.reading_questions + form.listening_questions + form.writing_questions + form.speaking_questions;

  return (
    <>
      <PageHeader title="Exam Tests" sub={`${tests.length} tests configured`}
        action={<button onClick={() => { setShowForm(true); setEditing(null); setForm({
          name: "", description: "", duration_minutes: 30,
          reading_questions: 10, listening_questions: 10,
          writing_questions: 10, speaking_questions: 0,
          reading_seconds: 600, listening_seconds: 600,
          writing_seconds: 600, speaking_seconds: 0,
          allow_pause: false, show_timer: true, one_shot_audio: true,
          is_active: true, is_baseline: false, company: "",
        }); }}
          className="px-3 py-1.5 text-xs rounded-md text-white flex items-center gap-1.5"
          style={{ background: "var(--brand-grad)" }}>
          <Plus size={12} /> New Test
        </button>} />

      {showForm && (
        <div className="ds-card p-5 mb-4">
          <div className="flex items-center justify-between mb-4">
            <div className="text-sm font-bold">{editing ? "Edit Test" : "New Test"}</div>
            <button onClick={() => { setShowForm(false); setEditing(null); }}><X size={14} className="text-muted" /></button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-[11px] font-semibold mb-1">Test Name *</label>
              <input value={form.name} onChange={(e) => set("name", e.target.value)}
                className="w-full px-3 py-2 text-xs rounded-md border bg-transparent"
                style={{ borderColor: "var(--border)" }} placeholder="e.g. Professional English Assessment" />
            </div>
            <div>
              <label className="block text-[11px] font-semibold mb-1">Description</label>
              <input value={form.description} onChange={(e) => set("description", e.target.value)}
                className="w-full px-3 py-2 text-xs rounded-md border bg-transparent"
                style={{ borderColor: "var(--border)" }} placeholder="Brief description of the test" />
            </div>
            <div>
              <label className="block text-[11px] font-semibold mb-1">Duration (minutes)</label>
              <input type="number" value={form.duration_minutes} onChange={(e) => set("duration_minutes", +e.target.value)}
                className="w-full px-3 py-2 text-xs rounded-md border bg-transparent"
                style={{ borderColor: "var(--border)" }} min={5} max={300} />
            </div>
            <div>
              <label className="block text-[11px] font-semibold mb-1">Company (empty = general)</label>
              <input value={form.company} onChange={(e) => set("company", e.target.value)}
                className="w-full px-3 py-2 text-xs rounded-md border bg-transparent"
                style={{ borderColor: "var(--border)" }} placeholder="Leave empty for general" />
            </div>
          </div>

          <div className="mt-4">
            <div className="text-[11px] font-semibold mb-2">Question Weightage (Total: {totalQ} questions)</div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {SECTION_FIELDS.map((sf) => (
                <div key={sf.key} className="p-2 rounded" style={{ background: "var(--surface-2)" }}>
                  <div className="flex items-center gap-1.5 mb-1">
                    <sf.icon size={12} style={{ color: sf.color }} />
                    <span className="text-[10px] font-medium">{sf.label}</span>
                  </div>
                  <input type="number" value={(form as any)[sf.key]}
                    onChange={(e) => set(sf.key, +e.target.value)}
                    className="w-full px-2 py-1 text-xs rounded border bg-transparent"
                    style={{ borderColor: "var(--border)" }} min={0} max={50} />
                </div>
              ))}
            </div>
          </div>

          <div className="mt-4">
            <div className="text-[11px] font-semibold mb-2">Section Timing (seconds)</div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {TIME_FIELDS.map((tf) => (
                <div key={tf.key}>
                  <span className="text-[10px] text-muted block mb-1">{tf.label}</span>
                  <input type="number" value={(form as any)[tf.key]}
                    onChange={(e) => set(tf.key, +e.target.value)}
                    className="w-full px-2 py-1 text-xs rounded border bg-transparent"
                    style={{ borderColor: "var(--border)" }} min={0} />
                </div>
              ))}
            </div>
          </div>

          <div className="mt-4 flex flex-wrap gap-3">
            {[
              { k: "allow_pause", l: "Allow Pause" },
              { k: "show_timer", l: "Show Timer" },
              { k: "one_shot_audio", l: "One-shot Audio" },
              { k: "is_active", l: "Active" },
              { k: "is_baseline", l: "Baseline Test" },
            ].map((f) => (
              <label key={f.k} className="flex items-center gap-1.5 text-[11px] cursor-pointer">
                <input type="checkbox" checked={(form as any)[f.k]}
                  onChange={(e) => set(f.k, e.target.checked)}
                  className="rounded" />
                {f.l}
              </label>
            ))}
          </div>

          <div className="flex justify-end gap-2 mt-4 pt-3 border-t" style={{ borderColor: "var(--border)" }}>
            <button onClick={() => { setShowForm(false); setEditing(null); }}
              className="px-3 py-1.5 text-xs rounded-md border" style={{ borderColor: "var(--border)" }}>
              Cancel
            </button>
            <button onClick={save}
              className="px-3 py-1.5 text-xs rounded-md text-white flex items-center gap-1.5"
              style={{ background: "var(--brand-grad)" }}>
              <Save size={12} /> {editing ? "Update" : "Create"}
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="text-xs text-muted p-4">Loading tests...</div>
      ) : tests.length === 0 ? (
        <div className="ds-card p-8 text-center">
          <ClipboardList size={32} className="mx-auto mb-2 text-muted" />
          <div className="text-sm text-muted mb-2">No exam tests yet</div>
          <div className="text-[11px] text-muted">Create your first test to get started</div>
        </div>
      ) : (
        <div className="grid gap-3">
          {tests.map((t) => (
            <div key={t.id} className="ds-card p-4">
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm font-bold">{t.name}</span>
                    {!t.is_active && <span className="px-1.5 py-0.5 rounded text-[9px] bg-gray-100 text-gray-600">Inactive</span>}
                    {t.is_baseline && <span className="px-1.5 py-0.5 rounded text-[9px] bg-blue-100 text-blue-700">Baseline</span>}
                    {t.company && <span className="px-1.5 py-0.5 rounded text-[9px] bg-violet-100 text-violet-700">{t.company}</span>}
                  </div>
                  {t.description && <div className="text-[11px] text-muted mb-2">{t.description}</div>}
                  <div className="flex flex-wrap gap-3 text-[10px] text-muted">
                    <span className="flex items-center gap-1"><Clock size={10} /> {t.duration_minutes} min</span>
                    <span className="flex items-center gap-1"><BookOpen size={10} /> {t.reading_questions} reading</span>
                    <span className="flex items-center gap-1"><Headphones size={10} /> {t.listening_questions} listening</span>
                    <span className="flex items-center gap-1"><PenLine size={10} /> {t.writing_questions} writing</span>
                    <span className="flex items-center gap-1"><Mic size={10} /> {t.speaking_questions} speaking</span>
                    <span className="font-semibold">
                      Total: {t.reading_questions + t.listening_questions + t.writing_questions + t.speaking_questions}
                    </span>
                  </div>
                  {/* Set availability */}
                  <div className="flex flex-wrap gap-2 mt-2">
                    {[{ m: "reading", n: t.reading_questions, c: "var(--rag-green)" },
                      { m: "listening", n: t.listening_questions, c: "var(--rag-amber)" },
                      { m: "writing", n: t.writing_questions, c: "var(--accent)" },
                      { m: "speaking", n: t.speaking_questions, c: "var(--secondary)" },
                    ].filter(x => x.n > 0).map(({ m, n, c }) => {
                      const cs = t.company ? (companySetSummary[t.company]?.[m] || {}) : {};
                      const avail = cs.active_sets ?? setSummary[m]?.active_sets ?? 0;
                      const qAvail = cs.questions_available ?? setSummary[m]?.questions_available ?? 0;
                      const setsNeeded = Math.ceil(n / 10);
                      const enough = avail >= setsNeeded;
                      return (
                        <span key={m} className="px-1.5 py-0.5 rounded text-[9px] font-medium"
                          style={{ background: enough ? "color-mix(in srgb, var(--rag-green) 10%, transparent)" : "color-mix(in srgb, var(--rag-red) 10%, transparent)", color: enough ? "var(--rag-green)" : "var(--rag-red)", border: `1px solid ${enough ? "var(--rag-green)" : "var(--rag-red)"}20` }}>
                          {m}: {avail} sets ({qAvail} q) {enough ? "OK" : "NEED MORE"}
                        </span>
                      );
                    })}
                  </div>
                </div>
                <div className="flex flex-col items-end gap-1.5">
                  <div className="flex items-center gap-1.5">
                    <button onClick={() => startEdit(t)} className="p-1.5 rounded hover:bg-surface2 text-muted" title="Edit">
                      <Edit size={13} />
                    </button>
                    <button onClick={() => remove(t.id)} className="p-1.5 rounded hover:bg-surface2 text-muted hover:text-red-500" title="Delete">
                      <Trash2 size={13} />
                    </button>
                  </div>
                  <button onClick={() => toggleActive(t)}
                    className="px-2 py-1 rounded text-[10px] font-semibold text-white"
                    style={{ background: t.is_active ? "var(--rag-red)" : "var(--rag-green)" }}
                    title={t.is_active ? "Hide from students" : "Publish to students"}>
                    {t.is_active ? "Deactivate" : "Activate"}
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}

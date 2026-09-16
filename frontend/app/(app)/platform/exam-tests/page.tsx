"use client";
import { useState, useEffect } from "react";
import {
  ClipboardList, Plus, X, Trash2, Save, BookOpen, Headphones, PenLine, Mic, Clock, Edit,
  ChevronDown, ChevronRight, Loader2, Check, Volume2, Play, Square,
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
  { key: "quiz_questions", label: "Grammar & Vocabulary (MCQ)", icon: BookOpen, color: "var(--primary)" },
];

const TIME_FIELDS = [
  { key: "reading_seconds", label: "Reading Time" },
  { key: "listening_seconds", label: "Listening Time" },
  { key: "writing_seconds", label: "Writing Time" },
  { key: "speaking_seconds", label: "Speaking Time" },
  { key: "quiz_seconds", label: "Grammar Time" },
];

function ExamTests() {
  const { toast } = useToast();
  const [tests, setTests] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<any>(null);
  const [setSummary, setSetSummary] = useState<Record<string, any>>({});
  const [companySetSummary, setCompanySetSummary] = useState<Record<string, Record<string, any>>>({});
  const [expandedTest, setExpandedTest] = useState<string | null>(null);
  const [form, setForm] = useState({
    name: "", description: "", duration_minutes: 30,
    reading_questions: 10, listening_questions: 10,
    writing_questions: 10, speaking_questions: 0, quiz_questions: 0,
    reading_seconds: 600, listening_seconds: 600,
    writing_seconds: 600, speaking_seconds: 0, quiz_seconds: 300,
    allow_pause: false, show_timer: true, one_shot_audio: true,
    is_active: true, is_baseline: false, company: "",
  });

  const load = async () => {
    setLoading(true);
    try {
      const token = getToken();
      const authHeaders: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
      const testsRes = await fetch(`${API_BASE}/platform/exam-tests`, { headers: authHeaders });
      if (testsRes.ok) {
        setTests(await testsRes.json());
      }
      try {
        const setsRes = await fetch(`${API_BASE}/platform/sets/summary`, { headers: authHeaders });
        if (setsRes.ok) setSetSummary(await setsRes.json());
      } catch {}
      try {
        const companySetsRes = await fetch(`${API_BASE}/platform/sets/summary-by-company`, { headers: authHeaders });
        if (companySetsRes.ok) setCompanySetSummary(await companySetsRes.json());
      } catch {}
    } catch (e: any) {
      console.error("Failed to load exam tests:", e);
    }
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

  const toggleActive = async (t: any) => {
    const token = getToken();
    try {
      const body = {
        name: t.name, description: t.description || "", duration_minutes: t.duration_minutes,
        reading_questions: t.reading_questions, listening_questions: t.listening_questions,
        writing_questions: t.writing_questions, speaking_questions: t.speaking_questions,
        quiz_questions: t.quiz_questions || 0,
        reading_seconds: t.reading_seconds, listening_seconds: t.listening_seconds,
        writing_seconds: t.writing_seconds, speaking_seconds: t.speaking_seconds,
        quiz_seconds: t.quiz_seconds || 300,
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
      toast("success", t.is_active ? "Test deactivated" : "Test activated");
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
      quiz_questions: t.quiz_questions || 0,
      reading_seconds: t.reading_seconds, listening_seconds: t.listening_seconds,
      writing_seconds: t.writing_seconds, speaking_seconds: t.speaking_seconds,
      quiz_seconds: t.quiz_seconds || 300,
      allow_pause: t.allow_pause, show_timer: t.show_timer, one_shot_audio: t.one_shot_audio,
      is_active: t.is_active, is_baseline: t.is_baseline, company: t.company || "",
    });
    setShowForm(true);
  };

  const totalQ = form.reading_questions + form.listening_questions + form.writing_questions + form.speaking_questions + form.quiz_questions;

  return (
    <>
      <PageHeader title="Exam Tests" sub={`${tests.length} tests configured`}
        action={<button onClick={() => { setShowForm(true); setEditing(null); setForm({
          name: "", description: "", duration_minutes: 30,
          reading_questions: 10, listening_questions: 10,
          writing_questions: 10, speaking_questions: 0, quiz_questions: 0,
          reading_seconds: 600, listening_seconds: 600,
          writing_seconds: 600, speaking_seconds: 0, quiz_seconds: 300,
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
        <div className="flex flex-col items-center justify-center py-16 gap-3">
          <div className="w-10 h-10 rounded-full border-[3px] border-[var(--border)] border-t-[var(--primary)] animate-spin" />
          <div className="text-xs text-muted">Loading tests...</div>
        </div>
      ) : tests.length === 0 ? (
        <div className="ds-card p-8 text-center">
          <ClipboardList size={32} className="mx-auto mb-2 text-muted" />
          <div className="text-sm text-muted mb-2">No exam tests yet</div>
          <div className="text-[11px] text-muted">Create your first test to get started</div>
        </div>
      ) : (
        <div className="grid gap-3">
          {tests.map((t) => (
            <div key={t.id} className="ds-card overflow-hidden">
              <div className="p-4">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-sm font-bold">{t.name}</span>
                      {!t.is_active && <span className="px-1.5 py-0.5 rounded text-[9px] bg-surface2 text-muted">Inactive</span>}
                      {t.is_baseline && <span className="px-1.5 py-0.5 rounded text-[9px] status-pill status-info">Baseline</span>}
                      {t.company && <span className="px-1.5 py-0.5 rounded text-[9px] status-pill status-brand">{t.company}</span>}
                    </div>
                    {t.description && <div className="text-[11px] text-muted mb-2">{t.description}</div>}
                    <div className="flex flex-wrap gap-3 text-[10px] text-muted">
                      <span className="flex items-center gap-1"><Clock size={10} /> {t.duration_minutes} min</span>
                      <span className="font-semibold">
                        Total: {t.reading_questions + t.listening_questions + t.writing_questions + t.speaking_questions + (t.quiz_questions || 0)}
                      </span>
                    </div>
                    {/* Available sets per category */}
                    {t.sets_by_module && Object.keys(t.sets_by_module).length > 0 && (
                      <div className="flex flex-wrap gap-1.5 mt-2">
                        {[
                          { key: "reading", label: "Reading", icon: BookOpen, color: "var(--rag-green)" },
                          { key: "listening", label: "Listening", icon: Headphones, color: "var(--rag-amber)" },
                          { key: "writing", label: "Writing", icon: PenLine, color: "var(--accent)" },
                          { key: "speaking", label: "Speaking", icon: Mic, color: "var(--secondary)" },
                          { key: "quiz", label: "Grammar & Vocabulary (MCQ)", icon: BookOpen, color: "var(--muted)" },
                        ].map(({ key, label, icon: CIcon, color }) => {
                          const count = t.sets_by_module[key] || 0;
                          if (count <= 0) return null;
                          return (
                            <span key={key} className="flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-medium"
                              style={{ background: `color-mix(in srgb, ${color} 10%, transparent)`, color }}>
                              <CIcon size={9} /> {label}: {count}
                            </span>
                          );
                        })}
                      </div>
                    )}
                  </div>
                  <div className="flex flex-col items-end gap-1.5">
                    <div className="flex items-center gap-1.5">
                      <button onClick={() => startEdit(t)} className="p-1.5 rounded hover:bg-surface2 text-muted" title="Edit">
                        <Edit size={13} />
                      </button>
                      <button onClick={() => remove(t.id)} className="p-1.5 rounded hover:bg-surface2 text-muted hover:text-ragRed" title="Delete">
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

              {/* Question Bank Panel */}
              <button onClick={() => setExpandedTest(expandedTest === t.id ? null : t.id)}
                className="w-full flex items-center gap-2 px-4 py-2 text-[11px] font-semibold border-t transition-colors"
                style={{ borderColor: "var(--border)", background: "color-mix(in srgb, var(--surface-2) 60%, transparent)" }}>
                {expandedTest === t.id ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                Question Bank
                <span className="text-muted font-normal ml-1">
                  ({Object.values(t.question_ids || {}).reduce((a: number, b: any) => a + (Array.isArray(b) ? b.length : 0), 0)} assigned)
                </span>
              </button>
              {expandedTest === t.id && (
                <ExamTestQuestionBank test={t} onRefresh={load} />
              )}
            </div>
          ))}
        </div>
      )}
    </>
  );
}


/* -----------------------------------------------------------------------
   Question Sets per Exam Test — browse sets, see questions inside each set
   ----------------------------------------------------------------------- */

const MOD_COLORS: Record<string, string> = {
  reading: "var(--rag-green)", listening: "var(--rag-amber)",
  writing: "var(--accent)", speaking: "var(--secondary)",
  quiz: "var(--primary)",
};
const MOD_LABELS: Record<string, string> = {
  reading: "Reading", listening: "Listening",
  writing: "Writing", speaking: "Speaking",
  quiz: "Grammar & Vocabulary (MCQ)",
};
const MOD_ICONS: Record<string, any> = {
  reading: BookOpen, listening: Headphones, writing: PenLine, speaking: Mic,
  quiz: BookOpen,
};
const MODULES = ["reading", "listening", "writing", "speaking", "quiz"];

function AudioInline({ audioKey }: { audioKey: string }) {
  const [playing, setPlaying] = useState(false);
  const [audio, setAudio] = useState<HTMLAudioElement | null>(null);
  if (!audioKey) return null;
  const toggle = () => {
    if (playing && audio) { audio.pause(); audio.currentTime = 0; setPlaying(false); setAudio(null); return; }
    const url = `${API_BASE}/platform/assets/${audioKey}`;
    const a = new Audio(url);
    a.onended = () => { setPlaying(false); setAudio(null); };
    a.onerror = () => { setPlaying(false); setAudio(null); };
    a.play().then(() => setPlaying(true)).catch(() => {});
    setAudio(a);
  };
  return (
    <button onClick={toggle} className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-medium hover:bg-surface2"
      style={{ background: "color-mix(in srgb, var(--secondary) 10%, transparent)", color: "var(--secondary)" }}>
      {playing ? <><Square size={8} /> Stop</> : <><Play size={8} /> Audio</>}
    </button>
  );
}

function ExamTestQuestionBank({ test, onRefresh }: { test: any; onRefresh: () => void }) {
  const [questions, setQuestions] = useState<Record<string, any[]>>({});
  const [loading, setLoading] = useState<Record<string, boolean>>({});
  const [expandedQ, setExpandedQ] = useState<string | null>(null);
  const [activeMod, setActiveMod] = useState<string | null>(null);

  const modules = ["reading", "listening", "writing", "speaking", "quiz"];

  const loadQuestions = async (mod: string) => {
    if (questions[mod] || loading[mod]) return;
    const qids = test.question_ids?.[mod] || [];
    if (!qids.length) return;
    
    setLoading(prev => ({ ...prev, [mod]: true }));
    try {
      const token = getToken();
      const res = await fetch(`${API_BASE}/platform/exam-tests/${test.id}/questions?module=${mod}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (res.ok) {
        const data = await res.json();
        setQuestions(prev => ({ ...prev, [mod]: data.questions?.[mod] || [] }));
      }
    } catch {}
    setLoading(prev => ({ ...prev, [mod]: false }));
  };

  // Load all modules on mount
  useEffect(() => {
    modules.forEach(loadQuestions);
  }, [test.id]);

  const totalQuestions = modules.reduce((sum, m) => sum + (test.question_ids?.[m]?.length || 0), 0);

  return (
    <div className="border-t" style={{ borderColor: "var(--border)" }}>
      {/* Set header - single set for exam test */}
      <div className="px-4 py-2 border-b" style={{ borderColor: "var(--border)" }}>
        <div className="flex items-center gap-3">
          <span className="px-3 py-1 rounded text-xs font-semibold text-white" style={{ background: "var(--primary)" }}>
            Set 1
          </span>
          <span className="text-[11px] text-muted">{totalQuestions} questions across {modules.filter(m => test.question_ids?.[m]?.length).length} skills</span>
        </div>
      </div>

      {/* All 5 skills */}
      <div className="p-3 space-y-3">
        {modules.map((mod) => {
          const qids = test.question_ids?.[mod] || [];
          if (!qids.length) return null;
          const qs = questions[mod] || [];
          const isLoading = loading[mod];
          const color = MOD_COLORS[mod];
          const Icon = MOD_ICONS[mod];
          const isActive = activeMod === mod;

          return (
            <div key={mod}>
              <button
                onClick={() => setActiveMod(isActive ? null : mod)}
                className="w-full flex items-center gap-1.5 mb-1.5 text-left"
              >
                <Icon size={11} style={{ color }} />
                <span className="text-[10px] font-semibold uppercase" style={{ color }}>{MOD_LABELS[mod]}</span>
                <span className="text-[9px] px-1 py-0.5 rounded bg-surface2 text-muted">{qids.length} questions</span>
                {isActive ? <ChevronDown size={10} className="ml-auto text-muted" /> : <ChevronRight size={10} className="ml-auto text-muted" />}
              </button>
              {isActive && (
                <div className="pl-5 space-y-1">
                  {isLoading ? (
                    <div className="flex items-center gap-2 text-[10px] text-muted py-2">
                      <Loader2 size={10} className="animate-spin" /> Loading...
                    </div>
                  ) : qs.length > 0 ? (
                    qs.map((q: any, idx: number) => {
                      const qKey = `${mod}-${q.id || idx}`;
                      const qExpanded = expandedQ === qKey;
                      return (
                        <div key={qKey} className="rounded border" style={{ borderColor: "var(--border)" }}>
                          <button onClick={() => setExpandedQ(qExpanded ? null : qKey)}
                            className="w-full flex items-center gap-1.5 px-2 py-1 hover:bg-surface2 text-[10px] text-left">
                            <ChevronRight size={8} className={`shrink-0 transition-transform ${qExpanded ? "rotate-90" : ""}`} />
                            <span className="flex-1 truncate">{idx + 1}. {q.title || q.stem || q.prompt_text || q.prompt || "Untitled"}</span>
                            {q.audio_key && <AudioInline audioKey={q.audio_key} />}
                            {q.category && <span className="shrink-0 text-[8px] px-1 py-0.5 rounded bg-surface2 text-muted">{q.category}</span>}
                          </button>
                          {qExpanded && (
                            <div className="px-3 pb-2 pt-1 border-t space-y-1" style={{ borderColor: "var(--border)" }}>
                              {q.body && <div className="text-[9px] text-muted leading-relaxed">{q.body.slice(0, 200)}{q.body.length > 200 ? "..." : ""}</div>}
                              {q.transcript && <div className="text-[9px] text-muted leading-relaxed">{q.transcript.slice(0, 200)}{q.transcript.length > 200 ? "..." : ""}</div>}
                              {q.prompt && <div className="text-[9px] text-muted leading-relaxed">{q.prompt.slice(0, 200)}{q.prompt.length > 200 ? "..." : ""}</div>}
                              {q.options && q.options.length > 0 && q.options.map((opt: string, oi: number) => (
                                <div key={oi} className={`px-2 py-0.5 rounded text-[10px] ${oi === q.correct_index ? "font-medium" : ""}`}
                                  style={oi === q.correct_index ? { background: "color-mix(in srgb, var(--rag-green) 12%, transparent)", color: "var(--rag-green)" } : {}}>
                                  {String.fromCharCode(65 + oi)}. {opt}
                                  {oi === q.correct_index && <span className="ml-1 text-[8px] font-bold">(Correct)</span>}
                                </div>
                              ))}
                              {q.explanation && <div className="text-[9px] text-muted mt-1"><strong>Explanation:</strong> {q.explanation}</div>}
                            </div>
                          )}
                        </div>
                      );
                    })
                  ) : (
                    <div className="text-[10px] text-muted py-1">No questions loaded</div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

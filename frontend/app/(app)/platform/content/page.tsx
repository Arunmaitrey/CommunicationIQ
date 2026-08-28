"use client";
import { useEffect, useState } from "react";
import { BookOpen, Mic, Headphones, PenLine, FileText, Plus, X, Trash2, Building2 } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { useToast } from "@/components/Toast";
import { ErrorNote, PageHeader, Section, Skeleton } from "@/components/ui";
import { PLATFORM_ROLES } from "@/lib/roles";
import { API_BASE, getToken } from "@/lib/api";

const COMPANIES = ["", "Accenture", "TCS", "Cognizant", "Wipro", "Infosys"];
const CATEGORIES = [
  { key: "reading_comprehension", label: "Reading Comprehension" },
  { key: "vocabulary", label: "Vocabulary" },
  { key: "grammar", label: "Grammar" },
  { key: "audio_comprehension", label: "Audio Comprehension" },
  { key: "email", label: "Email Writing" },
  { key: "essay", label: "Essay Writing" },
];

export default function QuestionBankPage() {
  return (
    <RequireAuth roles={PLATFORM_ROLES}>
      <QuestionBank />
    </RequireAuth>
  );
}

function QuestionBank() {
  const { toast } = useToast();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<"all" | "quiz" | "task" | "writing" | "listening" | "reading">("all");
  const [companyFilter, setCompanyFilter] = useState("");
  const [showAdd, setShowAdd] = useState(false);
  const [addType, setAddType] = useState("");
  const [deleting, setDeleting] = useState("");

  const loadData = () => {
    setLoading(true);
    const token = getToken();
    const params = new URLSearchParams();
    if (companyFilter) params.set("company", companyFilter);
    fetch(`${API_BASE}/platform/questions?${params}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((r) => { if (!r.ok) throw new Error("Failed to load"); return r.json(); })
      .then((d) => { setData(d); setLoading(false); })
      .catch((e) => { setError(e?.message || "Failed"); setLoading(false); });
  };

  useEffect(() => { loadData(); }, [companyFilter]);

  const handleDelete = async (collection: string, itemId: string) => {
    if (!confirm("Delete this question?")) return;
    setDeleting(itemId);
    const token = getToken();
    try {
      await fetch(`${API_BASE}/platform/questions/${collection}/${itemId}`, {
        method: "DELETE",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      toast("success", "Question deleted");
      loadData();
    } catch {
      toast("error", "Failed to delete question");
    } finally {
      setDeleting("");
    }
  };

  if (loading && !data) return <Skeleton rows={5} />;
  if (error && !data) return <ErrorNote message={error} />;

  const counts = data?.counts || {};
  const allItems = [
    ...(data?.quiz_items || []).map((i: any) => ({ ...i, _source: "Quiz", _collection: "quiz" })),
    ...(data?.task_items || []).map((i: any) => ({ ...i, _source: "Task", _collection: "task" })),
    ...(data?.writing_prompts || []).map((i: any) => ({ ...i, _source: "Writing", _collection: "writing" })),
    ...(data?.listening_passages || []).map((i: any) => ({ ...i, _source: "Listening", _collection: "listening" })),
    ...(data?.reading_passages || []).map((i: any) => ({ ...i, _source: "Reading", _collection: "reading" })),
  ];

  const filtered = tab === "all" ? allItems : allItems.filter((i) => {
    if (tab === "quiz") return i._source === "Quiz";
    if (tab === "task") return i._source === "Task";
    if (tab === "writing") return i._source === "Writing";
    if (tab === "listening") return i._source === "Listening";
    if (tab === "reading") return i._source === "Reading";
    return true;
  });

  // Group by company
  const byCompany: Record<string, any[]> = {};
  for (const item of filtered) {
    const c = item.company || "General (No Company)";
    (byCompany[c] ||= []).push(item);
  }

  const tabs = [
    { key: "all", label: "All", count: allItems.length },
    { key: "quiz", label: "Quiz/MCQ", count: counts.quiz_items || 0 },
    { key: "task", label: "Speaking", count: counts.task_items || 0 },
    { key: "writing", label: "Writing", count: counts.writing_prompts || 0 },
    { key: "listening", label: "Listening", count: counts.listening_passages || 0 },
    { key: "reading", label: "Reading", count: counts.reading_passages || 0 },
  ];

  const kindIcon: Record<string, any> = {
    Quiz: BookOpen, Task: Mic, Writing: PenLine, Listening: Headphones, Reading: FileText,
  };

  return (
    <>
      <PageHeader
        title="Question Bank"
        sub="Manage questions for reading, writing, listening and speaking across all institutions."
      />

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
        {[
          { label: "Quiz/MCQ", count: counts.quiz_items, color: "var(--primary)" },
          { label: "Speaking", count: counts.task_items, color: "var(--secondary)" },
          { label: "Writing", count: counts.writing_prompts, color: "var(--accent)" },
          { label: "Listening", count: counts.listening_passages, color: "var(--rag-amber)" },
          { label: "Reading", count: counts.reading_passages, color: "var(--rag-green)" },
        ].map((c) => (
          <div key={c.label} className="ds-card p-3 text-center">
            <div className="text-2xl font-bold" style={{ color: c.color }}>{c.count ?? 0}</div>
            <div className="text-[11px] text-muted">{c.label}</div>
          </div>
        ))}
      </div>

      {/* Filters and add button */}
      <div className="flex items-center gap-3 mb-4 flex-wrap">
        <select
          value={companyFilter}
          onChange={(e) => setCompanyFilter(e.target.value)}
          className="text-xs p-1.5 rounded border bg-transparent"
          style={{ borderColor: "var(--border)" }}
        >
          <option value="">All companies</option>
          {COMPANIES.filter(Boolean).map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        <button
          onClick={() => { setShowAdd(true); setAddType("quiz"); }}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md bg-[var(--primary)] text-white hover:opacity-90"
        >
          <Plus size={12} /> Add Question
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-4 overflow-x-auto">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key as any)}
            className={`px-3 py-1.5 text-xs rounded-md whitespace-nowrap transition-colors ${
              tab === t.key
                ? "bg-[var(--primary)] text-white font-medium"
                : "bg-surface2 text-muted hover:text-foreground"
            }`}
          >
            {t.label} ({t.count})
          </button>
        ))}
      </div>

      {/* Items grouped by company */}
      {Object.entries(byCompany).map(([company, items]) => (
        <Section key={company} title={`${company} (${items.length})`} className="mb-4">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b" style={{ borderColor: "var(--border)" }}>
                  <th className="text-left p-2 font-medium text-muted">Type</th>
                  <th className="text-left p-2 font-medium text-muted">Category</th>
                  <th className="text-left p-2 font-medium text-muted">Content</th>
                  <th className="text-left p-2 font-medium text-muted">Difficulty</th>
                  <th className="text-right p-2 font-medium text-muted">Actions</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item: any, idx: number) => {
                  const Icon = kindIcon[item._source] || BookOpen;
                  return (
                    <tr key={item.id || idx} className="border-b last:border-0 hover:bg-surface2 transition-colors" style={{ borderColor: "var(--border)" }}>
                      <td className="p-2">
                        <div className="flex items-center gap-1.5">
                          <Icon size={12} style={{ color: "var(--muted)" }} />
                          <span>{item._source}</span>
                        </div>
                      </td>
                      <td className="p-2 text-muted">{item.category || "—"}</td>
                      <td className="p-2 max-w-xs truncate">{item.title || "—"}</td>
                      <td className="p-2 text-muted">{typeof item.difficulty === "number" ? item.difficulty.toFixed(1) : "—"}</td>
                      <td className="p-2 text-right">
                        <button
                          onClick={() => handleDelete(item._collection, item.id)}
                          disabled={deleting === item.id}
                          className="text-muted hover:text-red-500 transition-colors disabled:opacity-50"
                          title="Delete"
                        >
                          <Trash2 size={12} />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Section>
      ))}

      {filtered.length === 0 && !loading && (
        <div className="ds-card p-8 text-center text-sm text-muted">No items found.</div>
      )}

      {/* Add Question Modal */}
      {showAdd && (
        <AddQuestionModal
          type={addType}
          onTypeChange={setAddType}
          onClose={() => setShowAdd(false)}
          onCreated={() => { setShowAdd(false); loadData(); }}
        />
      )}
    </>
  );
}

function AddQuestionModal({ type, onTypeChange, onClose, onCreated }: {
  type: string; onTypeChange: (t: string) => void; onClose: () => void; onCreated: () => void;
}) {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState<any>({
    stem: "", category: "reading_comprehension",
    options: ["", "", "", ""], correct_index: 0, explanation: "",
    company: "", difficulty: 0.3,
  });

  const set = (k: string, v: any) => setForm((f: any) => ({ ...f, [k]: v }));

  const handleSubmit = async () => {
    setLoading(true);
    setError("");
    const token = getToken();
    try {
      let url = `${API_BASE}/platform/questions/${type}`;
      let body: any;

      if (type === "quiz") {
        body = form;
      } else if (type === "speaking") {
        body = {
          task_type: form.task_type || "open_response",
          prompt_text: form.prompt_text || form.stem,
          company: form.company, reference_text: form.reference_text || "",
          difficulty: form.difficulty,
        };
      } else if (type === "writing") {
        body = {
          title: form.title, kind: form.kind || "essay", prompt: form.prompt || form.stem,
          company: form.company, scenario: form.scenario || "",
          key_points: form.key_points || [], min_words: form.min_words || 150,
          suggested_minutes: form.suggested_minutes || 20, difficulty: form.difficulty,
        };
      } else if (type === "listening") {
        // Upload audio first if present
        let audioKey = form.audioKey || "";
        if (form.audioFile) {
          const fd = new FormData();
          fd.append("file", form.audioFile);
          const upRes = await fetch(`${API_BASE}/platform/questions/audio`, {
            method: "POST",
            headers: token ? { Authorization: `Bearer ${token}` } : {},
            body: fd,
          });
          if (upRes.ok) {
            const upData = await upRes.json();
            audioKey = upData.key;
          }
        }
        // Parse comprehension questions
        const questions = parseQuestions(form.questions_text || "");
        body = {
          title: form.title, kind: "short_talk", transcript: form.transcript || "",
          company: form.company, audio_key: audioKey, accent: "indian",
          plays_allowed: form.plays_allowed || 1,
          approx_seconds: form.approx_seconds || 45,
          difficulty: form.difficulty, questions,
        };
      } else if (type === "reading") {
        const questions = parseQuestions(form.questions_text || "");
        body = {
          title: form.title, kind: form.kind || "article", body: form.body || "",
          company: form.company, difficulty: form.difficulty, questions,
        };
      }

      const res = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Failed" }));
        throw new Error(err.detail || "Failed");
      }
      onCreated();
      toast("success", "Question created successfully");
    } catch (e: any) {
      setError(e.message);
      toast("error", e.message || "Failed to create question");
    } finally {
      setLoading(false);
    }
  };

  const parseQuestions = (text: string) => {
    if (!text.trim()) return [];
    const blocks = text.split("\n\n").filter(Boolean);
    const questions: any[] = [];
    for (const block of blocks) {
      const lines = block.trim().split("\n").filter(Boolean);
      if (lines.length < 6) continue;
      const stem = lines[0];
      const options = lines.slice(1, 5).map((l) => l.replace(/^[A-D]\)\s*/, ""));
      const correct = { A: 0, B: 1, C: 2, D: 3 }[lines[5].trim().toUpperCase()] ?? 0;
      questions.push({ stem, options, correct_index: correct, explanation: "" });
    }
    if (questions.length === 0 && text.trim()) {
      const lines = text.trim().split("\n").filter(Boolean);
      if (lines.length >= 6) {
        const stem = lines[0];
        const options = lines.slice(1, 5).map((l) => l.replace(/^[A-D]\)\s*/, ""));
        const correct = { A: 0, B: 1, C: 2, D: 3 }[lines[5].trim().toUpperCase()] ?? 0;
        questions.push({ stem, options, correct_index: correct, explanation: "" });
      }
    }
    return questions;
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div className="bg-background rounded-lg p-6 w-full max-w-lg max-h-[90vh] overflow-y-auto shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-bold">Add Question</h2>
          <button onClick={onClose} className="text-muted hover:text-foreground"><X size={16} /></button>
        </div>

        {/* Type selector */}
        <div className="flex gap-1 mb-4 flex-wrap">
          {["quiz", "speaking", "writing", "listening", "reading"].map((t) => (
            <button
              key={t}
              onClick={() => onTypeChange(t)}
              className={`px-3 py-1.5 text-xs rounded-md capitalize ${
                type === t ? "bg-[var(--primary)] text-white" : "bg-surface2 text-muted"
              }`}
            >
              {t}
            </button>
          ))}
        </div>

        {error && <div className="text-xs text-red-500 mb-3">{error}</div>}

        <div className="space-y-3">
          {type === "quiz" && (
            <>
              <label className="block">
                <span className="text-[11px] text-muted">Category</span>
                <select value={form.category} onChange={(e) => set("category", e.target.value)}
                  className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }}>
                  {CATEGORIES.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
                </select>
              </label>
              <label className="block">
                <span className="text-[11px] text-muted">Question (Stem)</span>
                <textarea value={form.stem} onChange={(e) => set("stem", e.target.value)}
                  className="w-full text-xs p-2 rounded border bg-transparent mt-1 min-h-[60px]" style={{ borderColor: "var(--border)" }} />
              </label>
              {form.options.map((opt: string, i: number) => (
                <label key={i} className="block">
                  <span className="text-[11px] text-muted">Option {String.fromCharCode(65 + i)} {i === form.correct_index && "(Correct)"}</span>
                  <div className="flex gap-1 mt-1">
                    <button onClick={() => set("correct_index", i)}
                      className={`w-6 h-6 rounded text-[10px] font-bold flex-shrink-0 ${i === form.correct_index ? "bg-[var(--rag-green)] text-white" : "bg-surface2 text-muted"}`}>
                      {String.fromCharCode(65 + i)}
                    </button>
                    <input value={opt} onChange={(e) => {
                      const opts = [...form.options]; opts[i] = e.target.value; set("options", opts);
                    }} className="flex-1 text-xs p-1.5 rounded border bg-transparent" style={{ borderColor: "var(--border)" }} />
                  </div>
                </label>
              ))}
              <label className="block">
                <span className="text-[11px] text-muted">Explanation</span>
                <textarea value={form.explanation} onChange={(e) => set("explanation", e.target.value)}
                  className="w-full text-xs p-2 rounded border bg-transparent mt-1 min-h-[40px]" style={{ borderColor: "var(--border)" }} />
              </label>
            </>
          )}

          {type === "speaking" && (
            <>
              <label className="block">
                <span className="text-[11px] text-muted">Task Type</span>
                <select value={form.task_type || "open_response"} onChange={(e) => set("task_type", e.target.value)}
                  className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }}>
                  {["open_response", "read_aloud", "repeat_sentence", "short_answer", "story_retell",
                    "spoken_completion", "spoken_correction", "sentence_build", "conversation_question"].map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="text-[11px] text-muted">Prompt Text</span>
                <textarea value={form.prompt_text || form.stem} onChange={(e) => { set("prompt_text", e.target.value); set("stem", e.target.value); }}
                  className="w-full text-xs p-2 rounded border bg-transparent mt-1 min-h-[60px]" style={{ borderColor: "var(--border)" }} />
              </label>
              <label className="block">
                <span className="text-[11px] text-muted">Reference Text (expected answer)</span>
                <textarea value={form.reference_text || ""} onChange={(e) => set("reference_text", e.target.value)}
                  className="w-full text-xs p-2 rounded border bg-transparent mt-1 min-h-[40px]" style={{ borderColor: "var(--border)" }} />
              </label>
            </>
          )}

          {type === "writing" && (
            <>
              <label className="block">
                <span className="text-[11px] text-muted">Title</span>
                <input value={form.title || ""} onChange={(e) => set("title", e.target.value)}
                  className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }} />
              </label>
              <label className="block">
                <span className="text-[11px] text-muted">Kind</span>
                <select value={form.kind || "essay"} onChange={(e) => set("kind", e.target.value)}
                  className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }}>
                  <option value="essay">Essay</option>
                  <option value="email">Email</option>
                </select>
              </label>
              <label className="block">
                <span className="text-[11px] text-muted">Prompt</span>
                <textarea value={form.prompt || form.stem} onChange={(e) => { set("prompt", e.target.value); set("stem", e.target.value); }}
                  className="w-full text-xs p-2 rounded border bg-transparent mt-1 min-h-[80px]" style={{ borderColor: "var(--border)" }} />
              </label>
              <div className="grid grid-cols-2 gap-3">
                <label className="block">
                  <span className="text-[11px] text-muted">Min Words</span>
                  <input type="number" value={form.min_words || 150} onChange={(e) => set("min_words", parseInt(e.target.value))}
                    className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }} />
                </label>
                <label className="block">
                  <span className="text-[11px] text-muted">Suggested Minutes</span>
                  <input type="number" value={form.suggested_minutes || 20} onChange={(e) => set("suggested_minutes", parseInt(e.target.value))}
                    className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }} />
                </label>
              </div>
            </>
          )}

          {type === "listening" && (
            <>
              <label className="block">
                <span className="text-[11px] text-muted">Title</span>
                <input value={form.title || ""} onChange={(e) => set("title", e.target.value)}
                  className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }} />
              </label>
              <label className="block">
                <span className="text-[11px] text-muted">Transcript</span>
                <textarea value={form.transcript || ""} onChange={(e) => set("transcript", e.target.value)}
                  className="w-full text-xs p-2 rounded border bg-transparent mt-1 min-h-[80px]" style={{ borderColor: "var(--border)" }} />
              </label>
              <label className="block">
                <span className="text-[11px] text-muted">Audio File</span>
                <input type="file" accept="audio/*" onChange={(e) => set("audioFile", e.target.files?.[0] || null)}
                  className="w-full text-xs mt-1" />
                {form.audioKey && <span className="text-[10px] text-green-600 mt-1 block">Uploaded: {form.audioKey}</span>}
              </label>
              <div className="grid grid-cols-2 gap-3">
                <label className="block">
                  <span className="text-[11px] text-muted">Approx Seconds</span>
                  <input type="number" value={form.approx_seconds || 45} onChange={(e) => set("approx_seconds", parseInt(e.target.value))}
                    className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }} />
                </label>
                <label className="block">
                  <span className="text-[11px] text-muted">Plays Allowed</span>
                  <input type="number" value={form.plays_allowed || 1} onChange={(e) => set("plays_allowed", parseInt(e.target.value))}
                    className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }} />
                </label>
              </div>
              <label className="block">
                <span className="text-[11px] text-muted">Comprehension Questions (one per line: Q | A | B | C | D | correct_letter)</span>
                <textarea value={form.questions_text || ""} onChange={(e) => set("questions_text", e.target.value)}
                  placeholder={"What is the main topic?\nA) Topic1\nB) Topic2\nC) Topic3\nD) Topic4\nB"}
                  className="w-full text-xs p-2 rounded border bg-transparent mt-1 min-h-[100px] font-mono" style={{ borderColor: "var(--border)" }} />
              </label>
            </>
          )}

          {type === "reading" && (
            <>
              <label className="block">
                <span className="text-[11px] text-muted">Title</span>
                <input value={form.title || ""} onChange={(e) => set("title", e.target.value)}
                  className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }} />
              </label>
              <label className="block">
                <span className="text-[11px] text-muted">Kind</span>
                <select value={form.kind || "article"} onChange={(e) => set("kind", e.target.value)}
                  className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }}>
                  <option value="article">Article</option>
                  <option value="passage">Passage</option>
                  <option value="paragraph">Paragraph</option>
                </select>
              </label>
              <label className="block">
                <span className="text-[11px] text-muted">Body Text</span>
                <textarea value={form.body || ""} onChange={(e) => set("body", e.target.value)}
                  className="w-full text-xs p-2 rounded border bg-transparent mt-1 min-h-[100px]" style={{ borderColor: "var(--border)" }} />
              </label>
              <label className="block">
                <span className="text-[11px] text-muted">Comprehension Questions (one per line: Q | A | B | C | D | correct_letter)</span>
                <textarea value={form.questions_text || ""} onChange={(e) => set("questions_text", e.target.value)}
                  placeholder={"What is the main idea?\nA) Idea1\nB) Idea2\nC) Idea3\nD) Idea4\nA"}
                  className="w-full text-xs p-2 rounded border bg-transparent mt-1 min-h-[100px] font-mono" style={{ borderColor: "var(--border)" }} />
              </label>
            </>
          )}

          {/* Common fields */}
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="text-[11px] text-muted">Company</span>
              <select value={form.company} onChange={(e) => set("company", e.target.value)}
                className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }}>
                <option value="">General (All)</option>
                {COMPANIES.filter(Boolean).map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </label>
            <label className="block">
              <span className="text-[11px] text-muted">Difficulty (0-1)</span>
              <input type="number" step="0.1" min="0" max="1" value={form.difficulty}
                onChange={(e) => set("difficulty", parseFloat(e.target.value))}
                className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }} />
            </label>
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-5">
          <button onClick={onClose} className="px-3 py-1.5 text-xs rounded-md bg-surface2 text-muted">Cancel</button>
          <button
            onClick={handleSubmit}
            disabled={loading}
            className="px-3 py-1.5 text-xs rounded-md bg-[var(--primary)] text-white disabled:opacity-50"
          >
            {loading ? "Saving..." : "Save Question"}
          </button>
        </div>
      </div>
    </div>
  );
}

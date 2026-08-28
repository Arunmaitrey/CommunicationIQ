"use client";
import { useEffect, useState } from "react";
import {
  BookOpen, Mic, Headphones, PenLine, FileText, Plus, X, Trash2,
  ChevronDown, ChevronRight, ChevronLeft, AlertTriangle, Upload, Volume2, Loader2, Play,
} from "lucide-react";
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

const SECTION_CONFIG = [
  {
    key: "reading", label: "Reading", icon: FileText,
    color: "var(--rag-green)", bg: "color-mix(in srgb, var(--rag-green) 8%, transparent)",
    addType: "reading",
  },
  {
    key: "listening", label: "Listening", icon: Headphones,
    color: "var(--rag-amber)", bg: "color-mix(in srgb, var(--rag-amber) 8%, transparent)",
    addType: "listening",
  },
  {
    key: "speaking", label: "Speaking", icon: Mic,
    color: "var(--secondary)", bg: "color-mix(in srgb, var(--secondary) 8%, transparent)",
    addType: "speaking",
  },
  {
    key: "writing", label: "Writing", icon: PenLine,
    color: "var(--accent)", bg: "color-mix(in srgb, var(--accent) 8%, transparent)",
    addType: "writing",
  },
  {
    key: "quiz", label: "Grammar & Vocabulary (MCQ)", icon: BookOpen,
    color: "var(--primary)", bg: "color-mix(in srgb, var(--primary) 8%, transparent)",
    addType: "quiz",
  },
];

const PAGE_SIZE = 15;

export default function QuestionBankPage() {
  return (
    <RequireAuth roles={PLATFORM_ROLES}>
      <QuestionBank />
    </RequireAuth>
  );
}

function AudioPlayer({ audioKey, color, bg }: { audioKey: string; color: string; bg: string }) {
  const [playing, setPlaying] = useState(false);
  const ref = useState<{ el: HTMLAudioElement | null }>({ el: null });

  const toggle = () => {
    if (!audioKey) return;
    const url = `${API_BASE}/platform/assets/${audioKey}`;
    if (ref[0].el && !ref[0].el.paused) {
      ref[0].el.pause();
      ref[0].el.currentTime = 0;
      setPlaying(false);
      return;
    }
    const a = ref[0].el || new Audio();
    ref[0].el = a;
    a.src = url;
    a.onended = () => setPlaying(false);
    a.onerror = () => { setPlaying(false); };
    a.play().then(() => setPlaying(true)).catch(() => {});
  };

  return (
    <button onClick={toggle}
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium hover:bg-surface2 transition-colors"
      style={{ background: bg, color }}>
      {playing ? <><X size={11} /> Stop</> : <><Volume2 size={11} /> Play</>}
    </button>
  );
}

function QuestionBank() {
  const { toast } = useToast();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [showAdd, setShowAdd] = useState(false);
  const [addType, setAddType] = useState("");
  const [items, setItems] = useState<Record<string, any[]>>({});
  const [page, setPage] = useState<Record<string, number>>({});
  const [companyFilter, setCompanyFilter] = useState("");
  const [promptAudioFiles, setPromptAudioFiles] = useState<any[]>([]);
  const [audioExpanded, setAudioExpanded] = useState(false);
  const [audioPage, setAudioPage] = useState(0);
  const AUDIO_PAGE_SIZE = 20;

  const loadData = () => {
    setLoading(true);
    const token = getToken();
    const params = new URLSearchParams();
    if (companyFilter) params.set("company", companyFilter);
    fetch(`${API_BASE}/platform/questions?${params}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((r) => { if (!r.ok) throw new Error("Failed to load"); return r.json(); })
      .then((d) => {
        setData(d);
        const grouped: Record<string, any[]> = {
          reading: (d.reading_passages || []).map((i: any) => ({ ...i, _source: "Reading", _collection: "reading" })),
          listening: (d.listening_passages || []).map((i: any) => ({ ...i, _source: "Listening", _collection: "listening" })),
          speaking: (d.task_items || []).map((i: any) => ({ ...i, _source: "Speaking", _collection: "task" })),
          writing: (d.writing_prompts || []).map((i: any) => ({ ...i, _source: "Writing", _collection: "writing" })),
          quiz: (d.quiz_items || []).map((i: any) => ({ ...i, _source: "Quiz", _collection: "quiz" })),
        };
        setItems(grouped);
        setLoading(false);
      })
      .catch((e) => { setError(e?.message || "Failed"); setLoading(false); });
    fetch(`${API_BASE}/platform/prompt-audio`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    }).then((r) => r.ok ? r.json() : { files: [] })
      .then((d) => setPromptAudioFiles(d.files || []))
      .catch(() => {});
  };

  useEffect(() => { loadData(); }, [companyFilter]);

  const handleDelete = async (collection: string, itemId: string) => {
    if (!confirm("Delete this question?")) return;
    const token = getToken();
    try {
      await fetch(`${API_BASE}/platform/questions/${collection}/${itemId}`, {
        method: "DELETE", headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      toast("success", "Question deleted");
      loadData();
    } catch { toast("error", "Failed to delete question"); }
  };

  const toggleSection = (key: string) => {
    setExpanded((prev) => ({ ...prev, [key]: !prev[key] }));
    if (!expanded[key]) setPage((prev) => ({ ...prev, [key]: 0 }));
  };

  const openAdd = (type: string) => { setAddType(type); setShowAdd(true); };

  const getPageItems = (sectionKey: string) => {
    const allItems = items[sectionKey] || [];
    const p = page[sectionKey] || 0;
    return allItems.slice(p * PAGE_SIZE, (p + 1) * PAGE_SIZE);
  };

  const totalPages = (sectionKey: string) => Math.ceil((items[sectionKey]?.length || 0) / PAGE_SIZE);

  if (loading && !data) return <Skeleton rows={5} />;
  if (error && !data) return <ErrorNote message={error} />;

  const counts = data?.counts || {};
  const totalQuestions = (counts.quiz_items || 0) + (counts.task_items || 0) +
    (counts.writing_prompts || 0) + (counts.listening_passages || 0) + (counts.reading_passages || 0);

  return (
    <>
      <PageHeader title="Question Bank" sub="Manage questions for reading, writing, listening, speaking and grammar across all institutions." />

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
        {SECTION_CONFIG.map((s) => {
          const Icon = s.icon;
          const countKey = s.key === "reading" ? "reading_passages" : s.key === "listening" ? "listening_passages" :
            s.key === "speaking" ? "task_items" : s.key === "writing" ? "writing_prompts" : "quiz_items";
          const count = counts[countKey] || 0;
          return (
            <div key={s.key} className="ds-card p-3 text-center cursor-pointer hover:bg-surface2 transition-colors"
              onClick={() => { toggleSection(s.key); if (!expanded[s.key]) setTimeout(() => document.getElementById(`section-${s.key}`)?.scrollIntoView({ behavior: "smooth", block: "start" }), 100); }}>
              <Icon size={18} style={{ color: s.color }} className="mx-auto mb-1" />
              <div className="text-2xl font-bold" style={{ color: s.color }}>{count}</div>
              <div className="text-[11px] text-muted">{s.label}</div>
            </div>
          );
        })}
      </div>

      <div className="ds-card p-3 mb-4">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-4">
            <span className="text-xs font-semibold">Total: {totalQuestions} questions across all categories</span>
            <select value={companyFilter} onChange={(e) => setCompanyFilter(e.target.value)}
              className="text-xs p-1.5 rounded border bg-transparent" style={{ borderColor: "var(--border)" }}>
              <option value="">All Companies</option>
              {COMPANIES.filter(Boolean).map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>
          <span className="text-[11px] text-muted">{PAGE_SIZE} per page</span>
        </div>
        {companyFilter && (
          <div className="mt-2 text-[11px] text-muted">
            Showing only <strong style={{ color: "var(--primary)" }}>{companyFilter}</strong> questions
            <button onClick={() => setCompanyFilter("")} className="ml-2 underline">Show all</button>
          </div>
        )}
      </div>

      {/* Prompt Audio Bank */}
      <div className="ds-card overflow-hidden mb-4">
        <button onClick={() => setAudioExpanded(!audioExpanded)}
          className="w-full flex items-center gap-3 p-4 text-left hover:bg-surface2 transition-colors">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: "color-mix(in srgb, var(--primary) 8%, transparent)" }}>
            <Volume2 size={16} style={{ color: "var(--primary)" }} />
          </div>
          <div className="flex-1">
            <div className="text-sm font-bold">Prompt Audio Bank</div>
            <div className="text-[11px] text-muted">{promptAudioFiles.length} pre-rendered clips (M4A + WAV)</div>
          </div>
          {audioExpanded ? <ChevronDown size={16} className="text-muted" /> : <ChevronRight size={16} className="text-muted" />}
        </button>
        {audioExpanded && (
          <div className="border-t p-4" style={{ borderColor: "var(--border)" }}>
            {promptAudioFiles.length === 0 ? (
              <p className="text-xs text-muted">No pre-rendered audio files found.</p>
            ) : (
              <>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2 max-h-72 overflow-y-auto">
                  {promptAudioFiles.slice(audioPage * AUDIO_PAGE_SIZE, (audioPage + 1) * AUDIO_PAGE_SIZE).map((f: any) => (
                    <div key={f.name} className="flex items-center gap-2 p-2 rounded border text-xs" style={{ borderColor: "var(--border)" }}>
                      <button onClick={() => {
                        const a = new Audio(`${API_BASE}/platform/assets/${f.name}`);
                        a.play().catch(() => toast("error", "Could not play audio"));
                      }} className="shrink-0 w-6 h-6 rounded flex items-center justify-center hover:bg-surface2 transition-colors"
                        style={{ background: "color-mix(in srgb, var(--primary) 10%, transparent)", color: "var(--primary)" }}>
                        <Volume2 size={12} />
                      </button>
                      <div className="flex-1 min-w-0">
                        <div className="truncate font-mono text-[10px]">{f.name}</div>
                        <div className="text-muted text-[10px]">{f.ext.toUpperCase()} · {(f.size / 1024).toFixed(0)} KB</div>
                      </div>
                    </div>
                  ))}
                </div>
                {promptAudioFiles.length > AUDIO_PAGE_SIZE && (
                  <div className="flex items-center justify-between mt-3 pt-3 border-t" style={{ borderColor: "var(--border)" }}>
                    <span className="text-[11px] text-muted">
                      Showing {audioPage * AUDIO_PAGE_SIZE + 1}–{Math.min((audioPage + 1) * AUDIO_PAGE_SIZE, promptAudioFiles.length)} of {promptAudioFiles.length}
                    </span>
                    <div className="flex items-center gap-1">
                      <button disabled={audioPage === 0} onClick={() => setAudioPage(audioPage - 1)}
                        className="p-1 rounded disabled:opacity-30 hover:bg-surface2"><ChevronLeft size={14} /></button>
                      {Array.from({ length: Math.ceil(promptAudioFiles.length / AUDIO_PAGE_SIZE) }, (_, i) => (
                        <button key={i} onClick={() => setAudioPage(i)}
                          className="w-6 h-6 rounded text-[11px] font-medium"
                          style={{ background: i === audioPage ? "var(--primary)" : "transparent", color: i === audioPage ? "white" : "var(--muted)" }}>
                          {i + 1}
                        </button>
                      ))}
                      <button disabled={audioPage >= Math.ceil(promptAudioFiles.length / AUDIO_PAGE_SIZE) - 1}
                        onClick={() => setAudioPage(audioPage + 1)}
                        className="p-1 rounded disabled:opacity-30 hover:bg-surface2"><ChevronRight size={14} /></button>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>

      <div className="space-y-3">
        {SECTION_CONFIG.map((section) => {
          const Icon = section.icon;
          const sectionItems = items[section.key] || [];
          const isExpanded = expanded[section.key] || false;
          const countKey = section.key === "reading" ? "reading_passages" : section.key === "listening" ? "listening_passages" :
            section.key === "speaking" ? "task_items" : section.key === "writing" ? "writing_prompts" : "quiz_items";
          const count = counts[countKey] || 0;
          const p = page[section.key] || 0;
          const tp = totalPages(section.key);
          const pageItems = getPageItems(section.key);

          return (
            <div key={section.key} id={`section-${section.key}`} className="ds-card overflow-hidden">
              <button onClick={() => toggleSection(section.key)}
                className="w-full flex items-center gap-3 p-4 text-left hover:bg-surface2 transition-colors">
                <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: section.bg }}>
                  <Icon size={16} style={{ color: section.color }} />
                </div>
                <div className="flex-1">
                  <div className="text-sm font-bold">{section.label}</div>
                  <div className="text-[11px] text-muted">{count} question{count !== 1 ? "s" : ""} available</div>
                  {sectionItems.length > 0 && (
                    <div className="flex gap-1.5 mt-1.5 flex-wrap">
                      {Object.entries(
                        sectionItems.reduce((acc: Record<string, number>, item: any) => {
                          const c = item.company || "General";
                          acc[c] = (acc[c] || 0) + 1;
                          return acc;
                        }, {})
                      ).map(([company, n]) => (
                        <span key={company}
                          className="px-1.5 py-0.5 rounded text-[10px] font-medium"
                          style={{ background: section.bg, color: section.color }}>
                          {company}: {n}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                <button onClick={(e) => { e.stopPropagation(); openAdd(section.addType); }}
                  className="flex items-center gap-1 px-3 py-1.5 text-xs rounded-md transition-colors"
                  style={{ background: section.bg, color: section.color }}>
                  <Plus size={12} /> Add
                </button>
                {isExpanded ? <ChevronDown size={16} className="text-muted" /> : <ChevronRight size={16} className="text-muted" />}
              </button>

              {isExpanded && (
                <div className="border-t" style={{ borderColor: "var(--border)" }}>
                  {sectionItems.length === 0 ? (
                    <div className="p-6 text-center">
                      <p className="text-xs text-muted mb-3">No {section.label.toLowerCase()} questions yet.</p>
                      <button onClick={() => openAdd(section.addType)} className="text-xs px-3 py-1.5 rounded-md"
                        style={{ background: section.bg, color: section.color }}>
                        <Plus size={12} className="inline mr-1" /> Add first question
                      </button>
                    </div>
                  ) : (
                    <>
                      <div className="overflow-x-auto">
                        <table className="w-full text-xs">
                          <thead>
                            <tr className="border-b" style={{ borderColor: "var(--border)" }}>
                              <th className="text-left p-2 font-medium text-muted w-8">#</th>
                              <th className="text-left p-2 font-medium text-muted">Company</th>
                              <th className="text-left p-2 font-medium text-muted">Question / Content</th>
                              {(section.key === "listening" || section.key === "speaking") && (
                                <th className="text-left p-2 font-medium text-muted w-24">Audio</th>
                              )}
                              <th className="text-left p-2 font-medium text-muted w-16">Diff</th>
                              <th className="text-right p-2 font-medium text-muted w-16">Actions</th>
                            </tr>
                          </thead>
                          <tbody>
                            {pageItems.map((item: any, idx: number) => (
                              <tr key={item.id || idx} className="border-b last:border-0 hover:bg-surface2 transition-colors"
                                style={{ borderColor: "var(--border)" }}>
                                <td className="p-2 text-muted">{p * PAGE_SIZE + idx + 1}</td>
                                <td className="p-2">
                                  {item.company ? (
                                    <span className="px-1.5 py-0.5 rounded text-[10px] font-medium"
                                      style={{ background: section.bg, color: section.color }}>
                                      {item.company}
                                    </span>
                                  ) : <span className="text-[10px] text-muted">General</span>}
                                </td>
                                <td className="p-2">
                                  <div className="flex items-start gap-2">
                                    <span className="px-1.5 py-0.5 rounded text-[10px] font-medium shrink-0"
                                      style={{ background: section.bg, color: section.color }}>
                                      {item.category || item.task_type || item.kind || "—"}
                                    </span>
                                    <span className="text-xs leading-relaxed">{item.title || "—"}</span>
                                  </div>
                                </td>
                                {(section.key === "listening" || section.key === "speaking") && (
                                  <td className="p-2">
                                    {item.audio_key ? (
                                      <AudioPlayer audioKey={item.audio_key} color={section.color} bg={section.bg} />
                                    ) : <span className="text-[10px] text-muted">No audio</span>}
                                  </td>
                                )}
                                <td className="p-2 text-muted">{typeof item.difficulty === "number" ? item.difficulty.toFixed(1) : "—"}</td>
                                <td className="p-2 text-right">
                                  <button onClick={() => handleDelete(item._collection, item.id)}
                                    className="text-muted hover:text-red-500 transition-colors" title="Delete">
                                    <Trash2 size={12} />
                                  </button>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                      {tp > 1 && (
                        <div className="flex items-center justify-between p-3 border-t" style={{ borderColor: "var(--border)" }}>
                          <span className="text-[11px] text-muted">Showing {p * PAGE_SIZE + 1}–{Math.min((p + 1) * PAGE_SIZE, sectionItems.length)} of {sectionItems.length}</span>
                          <div className="flex items-center gap-1">
                            <button disabled={p === 0} onClick={() => setPage((prev) => ({ ...prev, [section.key]: p - 1 }))}
                              className="p-1 rounded disabled:opacity-30 hover:bg-surface2"><ChevronLeft size={14} /></button>
                            {Array.from({ length: tp }, (_, i) => (
                              <button key={i} onClick={() => setPage((prev) => ({ ...prev, [section.key]: i }))}
                                className="w-6 h-6 rounded text-[11px] font-medium"
                                style={{ background: i === p ? section.color : "transparent", color: i === p ? "white" : "var(--muted)" }}>
                                {i + 1}
                              </button>
                            ))}
                            <button disabled={p >= tp - 1} onClick={() => setPage((prev) => ({ ...prev, [section.key]: p + 1 }))}
                              className="p-1 rounded disabled:opacity-30 hover:bg-surface2"><ChevronRight size={14} /></button>
                          </div>
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {showAdd && <AddQuestionModal type={addType} onClose={() => setShowAdd(false)} onCreated={() => { setShowAdd(false); loadData(); }} />}
    </>
  );
}

function AddQuestionModal({ type, onClose, onCreated }: { type: string; onClose: () => void; onCreated: () => void; }) {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState<any>({
    // quiz
    stem: "", category: "reading_comprehension",
    options: ["", "", "", ""], correct_index: 0, explanation: "",
    // speaking
    task_type: "open_response", prompt_text: "", reference_text: "", audioKey: "", audioFile: null,
    // writing
    title: "", kind: "essay", prompt: "", scenario: "", key_points: [], min_words: 150, suggested_minutes: 20,
    // listening
    transcript: "", approx_seconds: 45, plays_allowed: 1, questions_text: "",
    // reading
    body: "",
    // common
    company: "", difficulty: 0.3,
  });

  const set = (k: string, v: any) => setForm((f: any) => ({ ...f, [k]: v }));

  const setOption = (i: number, val: string) => {
    setForm((f: any) => {
      const opts = [...f.options];
      opts[i] = val;
      return { ...f, options: opts };
    });
  };

  const validate = (): string => {
    if (type === "quiz") {
      if (!form.stem.trim()) return "Question stem is required";
      if (form.options.some((o: string) => !o.trim())) return "All 4 options are required";
      if (form.correct_index < 0 || form.correct_index > 3) return "Select a correct answer (A, B, C, or D)";
    } else if (type === "speaking") {
      if (!(form.prompt_text || form.stem).trim()) return "Prompt text is required";
    } else if (type === "writing") {
      if (!form.title?.trim()) return "Title is required";
      if (!(form.prompt || form.stem).trim()) return "Prompt is required";
    } else if (type === "listening") {
      if (!form.title?.trim()) return "Title is required";
      if (!form.transcript?.trim()) return "Transcript is required";
    } else if (type === "reading") {
      if (!form.title?.trim()) return "Title is required";
      if (!form.body?.trim()) return "Body text is required";
    }
    return "";
  };

  const handleSubmit = async () => {
    const vError = validate();
    if (vError) { setError(vError); return; }

    setLoading(true);
    setError("");
    const token = getToken();
    try {
      let url = `${API_BASE}/platform/questions/${type}`;
      let body: any;

      if (type === "quiz") {
        body = {
          category: form.category,
          stem: form.stem.trim(),
          options: form.options.map((o: string) => o.trim()),
          correct_index: form.correct_index,
          explanation: form.explanation || "",
          company: form.company || "",
          difficulty: form.difficulty,
        };
      } else if (type === "speaking") {
        let audioKey = form.audioKey || "";
        if (form.audioFile) {
          const fd = new FormData(); fd.append("file", form.audioFile);
          const upRes = await fetch(`${API_BASE}/platform/questions/audio`, {
            method: "POST", headers: token ? { Authorization: `Bearer ${token}` } : {}, body: fd,
          });
          if (upRes.ok) { audioKey = (await upRes.json()).key; }
        }
        body = {
          task_type: form.task_type || "open_response",
          prompt_text: form.prompt_text || form.stem,
          company: form.company || "", reference_text: form.reference_text || "",
          audio_key: audioKey, difficulty: form.difficulty,
        };
      } else if (type === "writing") {
        body = {
          title: form.title, kind: form.kind || "essay",
          prompt: form.prompt || form.stem, company: form.company || "",
          scenario: form.scenario || "", key_points: form.key_points || [],
          min_words: form.min_words || 150, suggested_minutes: form.suggested_minutes || 20,
          difficulty: form.difficulty,
        };
      } else if (type === "listening") {
        let audioKey = form.audioKey || "";
        if (form.audioFile) {
          const fd = new FormData(); fd.append("file", form.audioFile);
          const upRes = await fetch(`${API_BASE}/platform/questions/audio`, {
            method: "POST", headers: token ? { Authorization: `Bearer ${token}` } : {}, body: fd,
          });
          if (upRes.ok) { audioKey = (await upRes.json()).key; }
        }
        body = {
          title: form.title, kind: "short_talk", transcript: form.transcript || "",
          company: form.company || "", audio_key: audioKey, accent: "indian",
          plays_allowed: form.plays_allowed || 1, approx_seconds: form.approx_seconds || 45,
          difficulty: form.difficulty, questions: parseQuestions(form.questions_text || ""),
        };
      } else if (type === "reading") {
        body = {
          title: form.title, kind: form.kind || "article",
          body: form.body || "", company: form.company || "",
          difficulty: form.difficulty, questions: parseQuestions(form.questions_text || ""),
        };
      }

      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Failed" }));
        throw new Error(err.detail || "Failed to create question");
      }
      toast("success", "Question created successfully");
      onCreated();
    } catch (e: any) {
      setError(e.message);
      toast("error", e.message || "Failed to create question");
    } finally { setLoading(false); }
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
    return questions;
  };

  const sectionConfig = SECTION_CONFIG.find((s) => s.addType === type);
  const color = sectionConfig?.color || "var(--primary)";
  const bg = sectionConfig?.bg || "color-mix(in srgb, var(--primary) 8%, transparent)";

return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div className="bg-white rounded-lg p-6 w-full max-w-lg max-h-[90vh] overflow-y-auto shadow-xl"
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-bold" style={{ color }}>Add {sectionConfig?.label || type} Question</h2>
          <button onClick={onClose} className="text-muted hover:text-foreground"><X size={16} /></button>
        </div>

        {error && (
          <div className="text-xs mb-3 p-2 rounded flex items-start gap-2"
            style={{ background: "color-mix(in srgb, var(--rag-red) 10%, transparent)", color: "var(--rag-red)" }}>
            <AlertTriangle size={12} className="shrink-0 mt-0.5" /> {error}
          </div>
        )}

        <div className="space-y-3">
          {type === "quiz" && (
            <>
              <label className="block">
                <span className="text-[11px] text-muted font-medium">Category *</span>
                <select value={form.category} onChange={(e) => set("category", e.target.value)}
                  className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }}>
                  {CATEGORIES.map((c) => (<option key={c.key} value={c.key}>{c.label}</option>))}
                </select>
              </label>
              <label className="block">
                <span className="text-[11px] text-muted font-medium">Question (Stem) *</span>
                <textarea value={form.stem} onChange={(e) => set("stem", e.target.value)}
                  className="w-full text-xs p-2 rounded border bg-transparent mt-1 min-h-[60px]"
                  style={{ borderColor: "var(--border)" }} placeholder="Enter the question..." />
              </label>

              {/* Options with correct answer selector */}
              <div>
                <span className="text-[11px] text-muted font-medium">Options * (click A/B/C/D to mark correct) *</span>
                <div className="space-y-2 mt-1">
                  {form.options.map((opt: string, i: number) => (
                    <div key={i} className="flex gap-1.5 items-center">
                      <button type="button" onClick={() => set("correct_index", i)}
                        className="w-8 h-8 rounded-lg text-xs font-bold flex-shrink-0 transition-all"
                        style={{
                          background: i === form.correct_index ? "var(--rag-green)" : "var(--surface-2)",
                          color: i === form.correct_index ? "white" : "var(--muted)",
                          border: i === form.correct_index ? "2px solid var(--rag-green)" : "2px solid transparent",
                          boxShadow: i === form.correct_index ? "0 0 0 2px color-mix(in srgb, var(--rag-green) 30%, transparent)" : "none",
                        }}>
                        {String.fromCharCode(65 + i)}
                      </button>
                      <input value={opt} onChange={(e) => setOption(i, e.target.value)}
                        className="flex-1 text-xs p-2 rounded border bg-transparent"
                        style={{ borderColor: "var(--border)" }}
                        placeholder={`Option ${String.fromCharCode(65 + i)}...`} />
                    </div>
                  ))}
                </div>
                <div className="text-[10px] text-muted mt-1">
                  Currently correct: <strong style={{ color: "var(--rag-green)" }}>{String.fromCharCode(65 + form.correct_index)}</strong>
                </div>
              </div>

              <label className="block">
                <span className="text-[11px] text-muted font-medium">Explanation</span>
                <textarea value={form.explanation} onChange={(e) => set("explanation", e.target.value)}
                  className="w-full text-xs p-2 rounded border bg-transparent mt-1 min-h-[40px]"
                  style={{ borderColor: "var(--border)" }} placeholder="Why is this the correct answer?" />
              </label>
            </>
          )}

          {type === "speaking" && (
            <>
              <label className="block">
                <span className="text-[11px] text-muted font-medium">Task Type *</span>
                <select value={form.task_type || "open_response"} onChange={(e) => set("task_type", e.target.value)}
                  className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }}>
                  {["open_response", "read_aloud", "repeat_sentence", "short_answer", "story_retell",
                    "spoken_completion", "spoken_correction", "sentence_build", "conversation_question"
                  ].map((t) => (<option key={t} value={t}>{t.replace(/_/g, " ")}</option>))}
                </select>
              </label>
              <label className="block">
                <span className="text-[11px] text-muted font-medium">Prompt Text *</span>
                <textarea value={form.prompt_text || form.stem}
                  onChange={(e) => { set("prompt_text", e.target.value); set("stem", e.target.value); }}
                  className="w-full text-xs p-2 rounded border bg-transparent mt-1 min-h-[60px]"
                  style={{ borderColor: "var(--border)" }} placeholder="What should the student say or read?" />
              </label>
              <label className="block">
                <span className="text-[11px] text-muted font-medium">Reference Text (expected answer)</span>
                <textarea value={form.reference_text || ""} onChange={(e) => set("reference_text", e.target.value)}
                  className="w-full text-xs p-2 rounded border bg-transparent mt-1 min-h-[40px]"
                  style={{ borderColor: "var(--border)" }} placeholder="Expected answer for scoring..." />
              </label>
              <label className="block">
                <span className="text-[11px] text-muted font-medium flex items-center gap-1"><Upload size={11} /> Audio File (optional)</span>
                <input type="file" accept="audio/*" onChange={(e) => set("audioFile", e.target.files?.[0] || null)} className="w-full text-xs mt-1" />
                {form.audioKey && <span className="text-[10px] text-green-600 mt-1 block">Uploaded: {form.audioKey}</span>}
              </label>
            </>
          )}

          {type === "writing" && (
            <>
              <label className="block">
                <span className="text-[11px] text-muted font-medium">Title *</span>
                <input value={form.title || ""} onChange={(e) => set("title", e.target.value)}
                  className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }}
                  placeholder="e.g., Write a professional email" />
              </label>
              <label className="block">
                <span className="text-[11px] text-muted font-medium">Kind *</span>
                <select value={form.kind || "essay"} onChange={(e) => set("kind", e.target.value)}
                  className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }}>
                  <option value="essay">Essay</option><option value="email">Email</option>
                  <option value="report">Report</option><option value="summary">Summary</option>
                  <option value="complaint">Complaint</option>
                </select>
              </label>
              <label className="block">
                <span className="text-[11px] text-muted font-medium">Prompt *</span>
                <textarea value={form.prompt || form.stem}
                  onChange={(e) => { set("prompt", e.target.value); set("stem", e.target.value); }}
                  className="w-full text-xs p-2 rounded border bg-transparent mt-1 min-h-[80px]"
                  style={{ borderColor: "var(--border)" }} placeholder="What should the student write about?" />
              </label>
              <div className="grid grid-cols-2 gap-3">
                <label className="block">
                  <span className="text-[11px] text-muted font-medium">Min Words</span>
                  <input type="number" value={form.min_words || 150} onChange={(e) => set("min_words", parseInt(e.target.value))}
                    className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }} />
                </label>
                <label className="block">
                  <span className="text-[11px] text-muted font-medium">Suggested Minutes</span>
                  <input type="number" value={form.suggested_minutes || 20} onChange={(e) => set("suggested_minutes", parseInt(e.target.value))}
                    className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }} />
                </label>
              </div>
            </>
          )}

          {type === "listening" && (
            <>
              <label className="block">
                <span className="text-[11px] text-muted font-medium">Title *</span>
                <input value={form.title || ""} onChange={(e) => set("title", e.target.value)}
                  className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }}
                  placeholder="e.g., Airport Announcement" />
              </label>
              <label className="block">
                <span className="text-[11px] text-muted font-medium">Transcript *</span>
                <textarea value={form.transcript || ""} onChange={(e) => set("transcript", e.target.value)}
                  className="w-full text-xs p-2 rounded border bg-transparent mt-1 min-h-[80px]"
                  style={{ borderColor: "var(--border)" }} placeholder="What the audio says..." />
              </label>
              <label className="block">
                <span className="text-[11px] text-muted font-medium flex items-center gap-1"><Upload size={11} /> Audio File *</span>
                <input type="file" accept="audio/*" onChange={(e) => set("audioFile", e.target.files?.[0] || null)} className="w-full text-xs mt-1" />
                {form.audioKey && <span className="text-[10px] text-green-600 mt-1 block">Uploaded: {form.audioKey}</span>}
              </label>
              <div className="grid grid-cols-2 gap-3">
                <label className="block">
                  <span className="text-[11px] text-muted font-medium">Approx Seconds</span>
                  <input type="number" value={form.approx_seconds || 45} onChange={(e) => set("approx_seconds", parseInt(e.target.value))}
                    className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }} />
                </label>
                <label className="block">
                  <span className="text-[11px] text-muted font-medium">Plays Allowed</span>
                  <input type="number" value={form.plays_allowed || 1} onChange={(e) => set("plays_allowed", parseInt(e.target.value))}
                    className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }} />
                </label>
              </div>
              <label className="block">
                <span className="text-[11px] text-muted font-medium">Comprehension Questions</span>
                <textarea value={form.questions_text || ""} onChange={(e) => set("questions_text", e.target.value)}
                  placeholder={"What is the main topic?\nA) Topic1\nB) Topic2\nC) Topic3\nD) Topic4\nB"}
                  className="w-full text-xs p-2 rounded border bg-transparent mt-1 min-h-[100px] font-mono"
                  style={{ borderColor: "var(--border)" }} />
              </label>
            </>
          )}

          {type === "reading" && (
            <>
              <label className="block">
                <span className="text-[11px] text-muted font-medium">Title *</span>
                <input value={form.title || ""} onChange={(e) => set("title", e.target.value)}
                  className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }}
                  placeholder="e.g., Digital Transformation Report" />
              </label>
              <label className="block">
                <span className="text-[11px] text-muted font-medium">Kind *</span>
                <select value={form.kind || "article"} onChange={(e) => set("kind", e.target.value)}
                  className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }}>
                  <option value="article">Article</option><option value="passage">Passage</option>
                  <option value="notice">Notice</option><option value="instructions">Instructions</option>
                </select>
              </label>
              <label className="block">
                <span className="text-[11px] text-muted font-medium">Body Text *</span>
                <textarea value={form.body || ""} onChange={(e) => set("body", e.target.value)}
                  className="w-full text-xs p-2 rounded border bg-transparent mt-1 min-h-[100px]"
                  style={{ borderColor: "var(--border)" }} placeholder="The passage text..." />
              </label>
              <label className="block">
                <span className="text-[11px] text-muted font-medium">Comprehension Questions</span>
                <textarea value={form.questions_text || ""} onChange={(e) => set("questions_text", e.target.value)}
                  placeholder={"What is the main idea?\nA) Idea1\nB) Idea2\nC) Idea3\nD) Idea4\nA"}
                  className="w-full text-xs p-2 rounded border bg-transparent mt-1 min-h-[100px] font-mono"
                  style={{ borderColor: "var(--border)" }} />
              </label>
            </>
          )}

          {/* Common fields */}
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="text-[11px] text-muted font-medium">Company</span>
              <select value={form.company} onChange={(e) => set("company", e.target.value)}
                className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }}>
                <option value="">General (All)</option>
                {COMPANIES.filter(Boolean).map((c) => (<option key={c} value={c}>{c}</option>))}
              </select>
            </label>
            <label className="block">
              <span className="text-[11px] text-muted font-medium">Difficulty (0-1)</span>
              <input type="number" step="0.1" min="0" max="1" value={form.difficulty}
                onChange={(e) => set("difficulty", parseFloat(e.target.value))}
                className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }} />
            </label>
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-5 pt-4 border-t" style={{ borderColor: "var(--border)" }}>
          <button onClick={onClose} disabled={loading}
            className="px-4 py-2 text-xs rounded-md bg-surface2 text-muted hover:bg-surface transition-colors">
            Cancel
          </button>
          <button onClick={handleSubmit} disabled={loading}
            className="px-4 py-2 text-xs rounded-md text-white disabled:opacity-50 flex items-center gap-2 transition-colors"
            style={{ background: color }}>
            {loading ? <><Loader2 size={12} className="animate-spin" /> Saving...</> : "Save Question"}
          </button>
        </div>
      </div>
    </div>
  );
}

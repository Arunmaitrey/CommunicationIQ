"use client";
import { useState, useEffect, useCallback } from "react";
import {
  BookOpen, FileText, Headphones, Mic, Plus, Pencil, Trash2, ChevronDown, ChevronRight,
  ChevronLeft, X, Save,
} from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { PLATFORM_ROLES } from "@/lib/roles";
import { Badge, EmptyState, ErrorNote, PageHeader, Section, Skeleton } from "@/components/ui";
import { api, type TenantRow } from "@/lib/api";
import { useData } from "@/lib/useData";
import { useToast } from "@/components/Toast";

type Category = "reading" | "writing" | "listening" | "speaking" | "grammar" | "vocabulary";

interface QuestionItem {
  id: string;
  title?: string;
  stem?: string;
  prompt_text?: string;
  task_type?: string;
  kind?: string;
  company?: string;
  options: string[];
  correct_index: number;
  explanation?: string;
  body?: string;
  transcript?: string;
  prompt?: string;
  min_words?: number;
  reference_text?: string;
}
interface PlatformQuestionsResponse {
  tenants: TenantStatRecord[];
}
interface TenantStatRecord {
  reading_passages?: number;
  writing_prompts?: number;
  listening_passages?: number;
  speaking_items?: number;
  quiz_items?: Record<string, number>;
}

const CAT_ICONS: Record<Category, typeof BookOpen> = {
  reading: BookOpen, writing: FileText, listening: Headphones, speaking: Mic,
  grammar: FileText, vocabulary: BookOpen,
};
const CAT_LABELS: Record<Category, string> = {
  reading: "Reading Comprehension", writing: "Writing Prompts",
  listening: "Listening Comprehension", speaking: "Speaking Tasks",
  grammar: "Grammar", vocabulary: "Vocabulary",
};

export default function ContentPage() {
  return (
    <RequireAuth roles={PLATFORM_ROLES}>
      <Content />
    </RequireAuth>
  );
}

function Content() {
  const { data: tenants, loading: tenantsLoading } = useData(() => api.platformTenants());
  const [activeCategory, setActiveCategory] = useState<Category>("reading");
  const [items, setItems] = useState<QuestionItem[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [editItem, setEditItem] = useState<QuestionItem | null>(null);
  const { toast } = useToast();
  const PAGE_SIZE = 10;

  const sourceTenant = tenants?.[0] as TenantRow | undefined;

  const loadItems = useCallback(async (category: Category, p: number) => {
    if (!sourceTenant) return;
    setLoading(true);
    setError("");
    try {
      const data = await api.platformQuestionItems(sourceTenant.id, category, p, PAGE_SIZE);
      setItems(data.items as QuestionItem[]);
      setTotalCount(data.total);
      setPage(data.page);
      setTotalPages(data.total_pages);
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : "Failed to load questions";
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [sourceTenant]);

  const loadCounts = useCallback(async () => {
    if (!sourceTenant) return;
try {
      const data = await api.platformQuestions(sourceTenant.id);
      const t = (data as PlatformQuestionsResponse)?.tenants?.[0];
      if (t) {
        const quizItems: Record<string, number> = t.quiz_items && typeof t.quiz_items === 'object' ? t.quiz_items : {};
        setCounts({
          reading_passages: Number(t.reading_passages) || 0,
          writing_prompts: Number(t.writing_prompts) || 0,
          listening_passages: Number(t.listening_passages) || 0,
          speaking_items: Number(t.speaking_items) || 0,
          grammar: Number(quizItems.grammar) || 0,
          vocabulary: Number(quizItems.vocabulary) || 0,
        });
      }
    } catch { /* ignore */ }
  }, [sourceTenant]);

  useEffect(() => {
    if (sourceTenant) {
      loadCounts();
      loadItems(activeCategory, 1);
      setPage(1);
      setExpandedId(null);
      setShowAdd(false);
      setEditItem(null);
    }
  }, [sourceTenant, activeCategory, loadCounts, loadItems]);

  function getCategoryCount(cat: Category): number {
    switch (cat) {
      case "reading": return counts.reading_passages || 0;
      case "writing": return counts.writing_prompts || 0;
      case "listening": return counts.listening_passages || 0;
      case "speaking": return counts.speaking_items || 0;
      case "grammar": return counts.grammar || 0;
      case "vocabulary": return counts.vocabulary || 0;
    }
  }

  async function deleteItem(collection: string, itemId: string) {
    if (!confirm("Delete this item?")) return;
    if (!sourceTenant) return;
    try {
      await api.platformDeleteQuestion(collection, itemId, sourceTenant.id);
      setItems((prev) => prev.filter((i: QuestionItem) => i.id !== itemId));
      loadCounts();
      toast("success", "Question deleted");
    } catch { toast("error", "Failed to delete"); }
  }

  function getDeleteCollection(cat: Category): string {
    switch (cat) {
      case "reading": return "reading_passages";
      case "writing": return "writing_prompts";
      case "listening": return "listening_passages";
      default: return "quiz_items";
    }
  }

  function goToPage(p: number) {
    if (p < 1 || p > totalPages) return;
    setPage(p);
    loadItems(activeCategory, p);
    setExpandedId(null);
  }

  if (tenantsLoading) return <Skeleton rows={5} />;
  if (!sourceTenant) return <EmptyState title="No institutions found" />;

  return (
    <>
      <PageHeader
        title="Question Bank"
        sub="All institutions share the same question pool. Questions added here are available to every institution."
      />

      <Section title="Questions by category">
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2 mb-4">
          {(Object.keys(CAT_ICONS) as Category[]).map((cat) => {
            const Icon = CAT_ICONS[cat];
            const isActive = activeCategory === cat;
            const count = getCategoryCount(cat);
            return (
              <button
                key={cat}
                onClick={() => setActiveCategory(cat)}
                className={`p-3 rounded-ds border text-left transition-colors ${
                  isActive
                    ? "border-primary bg-primary/10"
                    : "border-line hover:bg-surface2"
                }`}
                style={isActive ? { borderColor: "var(--primary)" } : {}}
              >
                <Icon size={16} style={{ color: isActive ? "var(--primary)" : "var(--muted)" }} />
                <div className="text-xs font-bold mt-1.5">{CAT_LABELS[cat]}</div>
                <div className="text-[11px] text-muted mt-0.5">{count} items</div>
              </button>
            );
          })}
        </div>
      </Section>

      <Section
        title={`${CAT_LABELS[activeCategory]} (${totalCount} total)`}
        action={
          <button
            className="btn btn-primary btn-sm ds-focus"
            onClick={() => { setShowAdd(!showAdd); setEditItem(null); }}
          >
            {showAdd ? <X size={13} /> : <Plus size={13} />}
            {showAdd ? "Cancel" : "Add Question"}
          </button>
        }
      >
        {(showAdd || editItem) && (
          <AddQuestionForm
            category={activeCategory}
            tenantId={sourceTenant.id}
            editItem={editItem}
            onCreated={() => { setShowAdd(false); setEditItem(null); loadItems(activeCategory, page); loadCounts(); }}
            onCancelEdit={() => { setEditItem(null); setShowAdd(false); }}
          />
        )}
        {error && <ErrorNote message={error} />}
        {loading ? (
          <Skeleton rows={4} />
        ) : items.length === 0 ? (
          <EmptyState title={`No ${CAT_LABELS[activeCategory]} items yet`} desc="Add one using the button above." />
        ) : (
          <>
            <div className="space-y-2 mt-3">
              {items.map((item: QuestionItem) =>
                <div key={item.id} className="border rounded-ds p-3" style={{ borderColor: "var(--line)" }}>
                  <div
                    className="flex items-center gap-2 cursor-pointer"
                    onClick={() => setExpandedId(expandedId === item.id ? null : item.id)}
                  >
                    {expandedId === item.id ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    <span className="text-sm font-medium flex-1 truncate">
                      {item.title || item.stem || item.prompt_text || `Item ${item.id?.slice(0, 8)}`}
                    </span>
                    {item.kind && <Badge>{item.kind}</Badge>}
                    {item.task_type && <Badge>{item.task_type}</Badge>}
                    {item.company && <Badge>{item.company}</Badge>}
                    <button
                      onClick={(e) => { e.stopPropagation(); setEditItem(item); setShowAdd(false); }}
                      className="p-1 hover:bg-primary/10 rounded text-primary"
                      title="Edit"
                    >
                      <Pencil size={13} />
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); deleteItem(getDeleteCollection(activeCategory), item.id); }}
                      className="p-1 hover:bg-rag-red/10 rounded text-rag-red"
                      title="Delete"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                  {expandedId === item.id && (
                    <div className="mt-2 pl-6 text-xs text-muted leading-relaxed">
                      {item.body && <p className="mb-2">{item.body}</p>}
                      {item.transcript && <p className="mb-2 italic">"{item.transcript}"</p>}
                      {item.prompt && <p className="mb-2">{item.prompt}</p>}
                      {item.stem && <p className="mb-2 font-medium text-text">{item.stem}</p>}
                      {item.prompt_text && <p className="mb-2 font-medium text-text">{item.prompt_text}</p>}
                      {item.reference_text && <p className="mb-2 italic">Reference: {item.reference_text}</p>}
                      {item.options && (
                        <ul className="space-y-1 mt-2">
                          {item.options.map((opt: string, i: number) => (
                            <li key={i} className={i === item.correct_index ? "font-bold text-rag-green" : ""}>
                              {String.fromCharCode(65 + i)}. {opt}
                            </li>
                          ))}
                        </ul>
                      )}
                      {item.explanation && <p className="mt-2 italic">Explanation: {item.explanation}</p>}
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between mt-4 pt-3" style={{ borderTop: "1px solid var(--border)" }}>
                <span className="text-[11px] text-muted">
                  Page {page} of {totalPages} ({totalCount} items)
                </span>
                <div className="flex items-center gap-1">
                  <button
                    className="btn btn-ghost btn-sm ds-focus"
                    disabled={page <= 1}
                    onClick={() => goToPage(page - 1)}
                  >
                    <ChevronLeft size={14} /> Prev
                  </button>
                  {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                    const start = Math.max(1, Math.min(page - 2, totalPages - 4));
                    const p = start + i;
                    if (p > totalPages) return null;
                    return (
                      <button
                        key={p}
                        className={`px-2 py-1 text-[11px] font-semibold rounded ds-focus ${
                          p === page ? "text-white" : "text-muted hover:text-text"
                        }`}
                        style={p === page ? { background: "var(--primary)" } : { background: "var(--surface)" }}
                        onClick={() => goToPage(p)}
                      >
                        {p}
                      </button>
                    );
                  })}
                  <button
                    className="btn btn-ghost btn-sm ds-focus"
                    disabled={page >= totalPages}
                    onClick={() => goToPage(page + 1)}
                  >
                    Next <ChevronLeft size={14} className="rotate-180" />
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </Section>
    </>
  );
}

/* ---------- Add Question Form ---------- */

function AddQuestionForm({ category, tenantId, editItem, onCreated, onCancelEdit }: {
  category: Category; tenantId: string; editItem: QuestionItem | null;
  onCreated: () => void; onCancelEdit: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const { toast } = useToast();

  const [title, setTitle] = useState("");
  const [bodyText, setBodyText] = useState("");
  const [kind, setKind] = useState("article");
  const [stem, setStem] = useState("");
  const [options, setOptions] = useState(["", "", "", ""]);
  const [correctIndex, setCorrectIndex] = useState(0);
  const [explanation, setExplanation] = useState("");
  const [prompt, setPrompt] = useState("");
  const [minWords, setMinWords] = useState(150);
  const [transcript, setTranscript] = useState("");
  const [taskType, setTaskType] = useState("open_response");
  const [promptText, setPromptText] = useState("");
  const [referenceText, setReferenceText] = useState("");
  const [company, setCompany] = useState("");

  const COMPANIES = ["", "TCS", "Infosys", "Wipro", "Accenture", "Cognizant", "General"];

  useEffect(() => {
    if (editItem) {
      setTitle(editItem.title || "");
      setBodyText(editItem.body || "");
      setKind(editItem.kind || "article");
      setStem(editItem.stem || "");
      setOptions(editItem.options?.length === 4 ? editItem.options : ["", "", "", ""]);
      setCorrectIndex(editItem.correct_index || 0);
      setExplanation(editItem.explanation || "");
      setPrompt(editItem.prompt || "");
      setMinWords(editItem.min_words || 150);
      setTranscript(editItem.transcript || "");
      setTaskType(editItem.task_type || "open_response");
      setPromptText(editItem.prompt_text || "");
      setReferenceText(editItem.reference_text || "");
      setCompany(editItem.company || "");
    }
  }, [editItem]);

  function getDeleteCollection(cat: Category): string {
    switch (cat) {
      case "reading": return "reading_passages";
      case "writing": return "writing_prompts";
      case "listening": return "listening_passages";
      default: return "quiz_items";
    }
  }

  async function submit() {
    setBusy(true);
    setError("");
    try {
      let body: Record<string, unknown> = {};
      switch (category) {
        case "reading":
          body = {
            title, kind, body: bodyText, company,
            questions: stem ? [{ stem, options, correct_index: correctIndex, explanation }] : [],
          };
          break;
        case "writing":
          body = { title, kind, prompt, min_words: minWords, company };
          break;
        case "listening":
          body = {
            title, kind, transcript, company,
            questions: stem ? [{ stem, options, correct_index: correctIndex, explanation }] : [],
          };
          break;
        case "speaking":
          body = { task_type: taskType, prompt_text: promptText, reference_text: referenceText, company };
          break;
        case "grammar":
          body = { stem, options, correct_index: correctIndex, explanation, company };
          break;
        case "vocabulary":
          body = { stem, options, correct_index: correctIndex, explanation, company };
          break;
      }
      if (editItem) {
        await api.platformDeleteQuestion(getDeleteCollection(category), editItem.id, tenantId);
        await api.platformCreateQuestion(category, tenantId, body);
        toast("success", `${CAT_LABELS[category]} question updated`);
      } else {
        await api.platformCreateQuestion(category, tenantId, body);
        toast("success", `${CAT_LABELS[category]} question added to all institutions`);
      }
      onCreated();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : editItem ? "Failed to update question" : "Failed to create question");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="border rounded-ds p-4 mb-4" style={{ borderColor: "var(--primary)", background: "color-mix(in srgb, var(--primary) 4%, var(--surface))" }}>
      <div className="text-xs font-bold mb-3" style={{ color: "var(--primary)" }}>
        {editItem ? "Edit" : "Add new"} {CAT_LABELS[category]} question {editItem ? "" : "(saves to all institutions)"}
      </div>
      {error && <div className="text-xs mb-3 px-2 py-1 rounded" style={{ background: "color-mix(in srgb, var(--rag-red) 10%, transparent)", color: "var(--rag-red)" }}>{error}</div>}

      <div className="grid md:grid-cols-2 gap-3">
        <div>
          <label className="ds-label">Company</label>
          <select className="ds-input w-full" value={company} onChange={(e) => setCompany(e.target.value)}>
            {COMPANIES.map(c => <option key={c} value={c}>{c || "All / General"}</option>)}
          </select>
        </div>

        {(category === "reading" || category === "writing" || category === "listening") && (
          <div>
            <label className="ds-label">Title</label>
            <input className="ds-input w-full" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Question title" />
          </div>
        )}

        {(category === "reading" || category === "writing" || category === "listening") && (
          <div>
            <label className="ds-label">Type</label>
            <select className="ds-input w-full" value={kind} onChange={(e) => setKind(e.target.value)}>
              {category === "reading" && <><option value="article">Article</option><option value="passage">Passage</option></>}
              {category === "writing" && <><option value="essay">Essay</option><option value="email">Email</option></>}
              {category === "listening" && <><option value="short_talk">Short Talk</option><option value="dialogue">Dialogue</option></>}
            </select>
          </div>
        )}

        {category === "speaking" && (
          <div>
            <label className="ds-label">Task Type</label>
            <select className="ds-input w-full" value={taskType} onChange={(e) => setTaskType(e.target.value)}>
              <option value="open_response">Open Response</option>
              <option value="read_aloud">Read Aloud</option>
              <option value="repeat">Repeat</option>
              <option value="short_answer">Short Answer</option>
            </select>
          </div>
        )}

        {category === "reading" && (
          <div className="md:col-span-2">
            <label className="ds-label">Passage Text</label>
            <textarea className="ds-input w-full" rows={4} value={bodyText} onChange={(e) => setBodyText(e.target.value)} placeholder="The passage text..." />
          </div>
        )}

        {category === "writing" && (
          <>
            <div className="md:col-span-2">
              <label className="ds-label">Prompt</label>
              <textarea className="ds-input w-full" rows={3} value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="What the student should write about..." />
            </div>
            <div>
              <label className="ds-label">Minimum Words</label>
              <input className="ds-input w-full" type="number" value={minWords} onChange={(e) => setMinWords(Number(e.target.value))} />
            </div>
          </>
        )}

        {category === "listening" && (
          <div className="md:col-span-2">
            <label className="ds-label">Transcript</label>
            <textarea className="ds-input w-full" rows={3} value={transcript} onChange={(e) => setTranscript(e.target.value)} placeholder="Audio transcript..." />
          </div>
        )}

        {category === "speaking" && (
          <>
            <div className="md:col-span-2">
              <label className="ds-label">Prompt Text</label>
              <textarea className="ds-input w-full" rows={2} value={promptText} onChange={(e) => setPromptText(e.target.value)} placeholder="What the student should say..." />
            </div>
            <div className="md:col-span-2">
              <label className="ds-label">Reference Text (optional)</label>
              <textarea className="ds-input w-full" rows={2} value={referenceText} onChange={(e) => setReferenceText(e.target.value)} placeholder="Reference text for scoring..." />
            </div>
          </>
        )}

        {(category === "reading" || category === "listening" || category === "grammar" || category === "vocabulary") && (
          <>
            <div className="md:col-span-2">
              <label className="ds-label">Question Stem</label>
              <input className="ds-input w-full" value={stem} onChange={(e) => setStem(e.target.value)} placeholder="Which statement is NOT supported?" />
            </div>
            {options.map((opt, i) => (
              <div key={i}>
                <label className="ds-label">Option {String.fromCharCode(65 + i)} {i === correctIndex && <span className="text-rag-green">(correct)</span>}</label>
                <input className="ds-input w-full" value={opt} onChange={(e) => {
                  const next = [...options]; next[i] = e.target.value; setOptions(next);
                }} placeholder={`Option ${String.fromCharCode(65 + i)}`} />
              </div>
            ))}
            <div>
              <label className="ds-label">Correct Answer</label>
              <select className="ds-input w-full" value={correctIndex} onChange={(e) => setCorrectIndex(Number(e.target.value))}>
                {options.map((_, i) => <option key={i} value={i}>{String.fromCharCode(65 + i)}</option>)}
              </select>
            </div>
            <div className="md:col-span-2">
              <label className="ds-label">Explanation (optional)</label>
              <input className="ds-input w-full" value={explanation} onChange={(e) => setExplanation(e.target.value)} placeholder="Why this is correct..." />
            </div>
          </>
        )}
      </div>

      <div className="flex gap-2 mt-3">
        <button className="btn btn-primary btn-sm ds-focus" disabled={busy} onClick={() => void submit()}>
          <Save size={13} /> {busy ? "Saving..." : editItem ? "Update Question" : "Save Question"}
        </button>
        <button className="btn btn-ghost btn-sm ds-focus" onClick={editItem ? onCancelEdit : onCreated}>
          {editItem ? "Cancel Edit" : "Cancel"}
        </button>
      </div>
    </div>
  );
}

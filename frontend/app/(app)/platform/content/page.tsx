"use client";
import { useState, useEffect, useCallback } from "react";
import {
  BookOpen, FileText, Headphones, Mic, Plus, Pencil, Trash2, ChevronDown, ChevronRight,
  ChevronLeft, X, Save, Filter, Building2, Globe,
} from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { PLATFORM_ROLES } from "@/lib/roles";
import { Badge, EmptyState, ErrorNote, PageHeader, Section, Skeleton } from "@/components/ui";
import { api, type TenantRow } from "@/lib/api";
import { useData } from "@/lib/useData";
import { useToast } from "@/components/Toast";

/* ------------------------------------------------------------------ */
/*  Categories                                                         */
/* ------------------------------------------------------------------ */

type BaseCategory = "reading" | "writing" | "listening" | "speaking" | "grammar" | "vocabulary";

type CompanyKey = "accenture" | "cognizant" | "wipro" | "tcs" | "infosys";

type Category = BaseCategory | CompanyKey;

const BASE_CATEGORIES: BaseCategory[] = [
  "reading", "writing", "listening", "speaking", "grammar", "vocabulary",
];

const COMPANY_EXAMS: { key: CompanyKey; label: string; color: string }[] = [
  { key: "accenture", label: "Accenture-style Comm Round", color: "var(--accent)" },
  { key: "cognizant", label: "Cognizant-style Comm Assessment", color: "#8b5cf6" },
  { key: "wipro",     label: "Wipro-style Voice Round",      color: "#f59e0b" },
  { key: "tcs",       label: "TCS-style Ninja",              color: "#10b981" },
  { key: "infosys",   label: "Infosys-style",                color: "#3b82f6" },
];

const COMPANY_NAME_MAP: Record<CompanyKey, string> = {
  accenture: "Accenture", cognizant: "Cognizant", wipro: "Wipro",
  tcs: "TCS", infosys: "Infosys",
};

/* Sub-types within a company round (what the admin adds) */
type CompanySubType = "reading" | "writing" | "listening" | "speaking";

const SUB_ICONS: Record<CompanySubType, typeof BookOpen> = {
  reading: BookOpen, writing: FileText, listening: Headphones, speaking: Mic,
};
const SUB_LABELS: Record<CompanySubType, string> = {
  reading: "Reading", writing: "Writing", listening: "Listening", speaking: "Speaking",
};

function isCompanyKey(c: Category): c is CompanyKey {
  return c in COMPANY_NAME_MAP;
}

const CAT_ICONS_BASE: Record<BaseCategory, typeof BookOpen> = {
  reading: BookOpen, writing: FileText, listening: Headphones, speaking: Mic,
  grammar: FileText, vocabulary: BookOpen,
};
const CAT_LABELS_BASE: Record<BaseCategory, string> = {
  reading: "Reading Comprehension", writing: "Writing Prompts",
  listening: "Listening Comprehension", speaking: "Speaking Tasks",
  grammar: "Grammar", vocabulary: "Vocabulary",
};

/* ------------------------------------------------------------------ */
/*  API helpers                                                        */
/* ------------------------------------------------------------------ */

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

/* ------------------------------------------------------------------ */
/*  Page root                                                          */
/* ------------------------------------------------------------------ */

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
  const [companyFilter, setCompanyFilter] = useState("");
  const [companySubType, setCompanySubType] = useState<CompanySubType>("reading");
  const { toast } = useToast();
  const PAGE_SIZE = 10;

  const COMPANIES = ["", "TCS", "Infosys", "Wipro", "Accenture", "Cognizant"];
  const sourceTenant = tenants?.[0] as TenantRow | undefined;

  /* ---- Determine which base categories to load for company rounds ---- */
  const activeCompany = isCompanyKey(activeCategory) ? COMPANY_NAME_MAP[activeCategory] : null;

  const loadItems = useCallback(async (category: Category, p: number) => {
    if (!sourceTenant) return;
    setLoading(true);
    setError("");
    try {
      if (isCompanyKey(category)) {
        const companyName = COMPANY_NAME_MAP[category];
        const baseCat = companySubType as BaseCategory;
        const data = await api.platformQuestionItems(sourceTenant.id, baseCat, p, PAGE_SIZE);
        const filtered = (data.items as QuestionItem[]).filter(
          (i) => (i.company || "").toLowerCase() === companyName.toLowerCase(),
        );
        setItems(filtered);
        setTotalCount(filtered.length);
        setPage(data.page);
        setTotalPages(Math.max(1, Math.ceil(filtered.length / PAGE_SIZE)));
      } else {
        const data = await api.platformQuestionItems(sourceTenant.id, category, p, PAGE_SIZE);
        setItems(data.items as QuestionItem[]);
        setTotalCount(data.total);
        setPage(data.page);
        setTotalPages(data.total_pages);
      }
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : "Failed to load questions";
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [sourceTenant, companySubType]);

  const loadCounts = useCallback(async () => {
    if (!sourceTenant) return;
    try {
      const data = await api.platformQuestions(sourceTenant.id);
      const t = (data as { tenants?: Record<string, unknown>[] })?.tenants?.[0];
      if (t) {
        const qi = t.quiz_items && typeof t.quiz_items === 'object' ? t.quiz_items as Record<string, number> : {};
        setCounts({
          reading_passages: Number(t.reading_passages) || 0,
          writing_prompts: Number(t.writing_prompts) || 0,
          listening_passages: Number(t.listening_passages) || 0,
          speaking_items: Number(t.speaking_items) || 0,
          grammar: Number(qi.grammar) || 0,
          vocabulary: Number(qi.vocabulary) || 0,
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
      setCompanyFilter("");
    }
  }, [sourceTenant, activeCategory, loadCounts, loadItems, companySubType]);

  function getCategoryCount(cat: Category): number {
    if (isCompanyKey(cat)) {
      const companyName = COMPANY_NAME_MAP[cat];
      let total = 0;
      for (const k of ["reading_passages", "writing_prompts", "listening_passages", "speaking_items"] as const) {
        total += counts[k] || 0;
      }
      return total;
    }
    switch (cat) {
      case "reading": return counts.reading_passages || 0;
      case "writing": return counts.writing_prompts || 0;
      case "listening": return counts.listening_passages || 0;
      case "speaking": return counts.speaking_items || 0;
      case "grammar": return counts.grammar || 0;
      case "vocabulary": return counts.vocabulary || 0;
    }
  }

  function getDeleteCollection(cat: BaseCategory): string {
    switch (cat) {
      case "reading": return "reading_passages";
      case "writing": return "writing_prompts";
      case "listening": return "listening_passages";
      default: return "quiz_items";
    }
  }

  async function deleteItem(collection: string, itemId: string) {
    if (!confirm("Delete this item?")) return;
    if (!sourceTenant) return;
    try {
      await api.platformDeleteQuestion(collection, itemId, sourceTenant.id);
      setItems((prev) => prev.filter((i) => i.id !== itemId));
      loadCounts();
      toast("success", "Question deleted");
    } catch { toast("error", "Failed to delete"); }
  }

  function goToPage(p: number) {
    if (p < 1 || p > totalPages) return;
    setPage(p);
    loadItems(activeCategory, p);
    setExpandedId(null);
  }

  if (tenantsLoading) return <Skeleton rows={5} />;
  if (!sourceTenant) return <EmptyState title="No institutions found" />;

  const sectionTitle = activeCompany
    ? `${COMPANY_EXAMS.find((c) => c.key === activeCategory)?.label ?? activeCompany} (${totalCount} items)`
    : `${CAT_LABELS_BASE[activeCategory as BaseCategory]} (${totalCount} total)`;

  return (
    <>
      <PageHeader
        title="Question Bank"
        sub="All institutions share the same question pool. Questions added here are available to every institution."
      />

      {/* ---- Category grid ---- */}
      <Section title="Questions by category">
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2 mb-3">
          {(BASE_CATEGORIES).map((cat) => {
            const Icon = CAT_ICONS_BASE[cat];
            const isActive = !isCompanyKey(activeCategory) && activeCategory === cat;
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
                <div className="text-xs font-bold mt-1.5">{CAT_LABELS_BASE[cat]}</div>
                <div className="text-[11px] text-muted mt-0.5">{getCategoryCount(cat)} items</div>
              </button>
            );
          })}
        </div>
      </Section>

      {/* ---- Company Rounds ---- */}
      <Section title="Company Rounds">
        <p className="text-xs text-muted mb-3 leading-relaxed">
          Add company-specific questions for each employer's communication round.
          These questions appear when a student sits that company's exam.
        </p>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-2">
          {COMPANY_EXAMS.map((comp) => {
            const isActive = activeCategory === comp.key;
            return (
              <button
                key={comp.key}
                onClick={() => setActiveCategory(comp.key)}
                className={`p-3 rounded-ds border text-left transition-colors ${
                  isActive ? "border-primary bg-primary/10" : "border-line hover:bg-surface2"
                }`}
                style={isActive ? { borderColor: comp.color } : {}}
              >
                <Building2 size={16} style={{ color: comp.color }} />
                <div className="text-xs font-bold mt-1.5">{comp.label}</div>
                <div className="text-[11px] text-muted mt-0.5">Questions for {comp.label.split("-")[0].trim()}</div>
              </button>
            );
          })}
        </div>
      </Section>

      {/* ---- Content section ---- */}
      <Section
        title={sectionTitle}
        action={
          <div className="flex items-center gap-2">
            {activeCompany && (
              <div className="flex items-center gap-1.5">
                {Object.keys(SUB_ICONS).map((st) => {
                  const SubIcon = SUB_ICONS[st as CompanySubType];
                  return (
                    <button
                      key={st}
                      className={`px-2 py-1 text-[11px] font-semibold rounded-ds border transition-colors ${
                        companySubType === st
                          ? "border-primary bg-primary/10 text-primary"
                          : "border-line text-muted hover:bg-surface2"
                      }`}
                      style={companySubType === st ? { borderColor: COMPANY_EXAMS.find((c) => c.key === activeCategory)?.color } : {}}
                      onClick={() => setCompanySubType(st as CompanySubType)}
                    >
                      <SubIcon size={11} className="inline mr-1" />
                      {SUB_LABELS[st as CompanySubType]}
                    </button>
                  );
                })}
              </div>
            )}
            {!activeCompany && (
              <div className="flex items-center gap-1.5">
                <Filter size={12} className="text-muted" />
                <select
                  className="ds-input text-xs py-1 px-2"
                  style={{ minWidth: 120 }}
                  value={companyFilter}
                  onChange={(e) => setCompanyFilter(e.target.value)}
                >
                  {COMPANIES.map(c => (
                    <option key={c} value={c}>{c || "All Companies"}</option>
                  ))}
                </select>
              </div>
            )}
            <button
              className="btn btn-primary btn-sm ds-focus"
              onClick={() => { setShowAdd(!showAdd); setEditItem(null); }}
            >
              {showAdd ? <X size={13} /> : <Plus size={13} />}
              {showAdd ? "Cancel" : "Add Question"}
            </button>
          </div>
        }
      >
        {(showAdd || editItem) && (
          <AddQuestionForm
            category={activeCompany ? companySubType as BaseCategory : (activeCategory as BaseCategory)}
            tenantId={sourceTenant.id}
            editItem={editItem}
            forceCompany={activeCompany || ""}
            onCreated={() => { setShowAdd(false); setEditItem(null); loadItems(activeCategory, page); loadCounts(); }}
            onCancelEdit={() => { setEditItem(null); setShowAdd(false); }}
          />
        )}
        {error && <ErrorNote message={error} />}
        {loading ? (
          <Skeleton rows={4} />
        ) : items.length === 0 ? (
          <EmptyState
            title={`No ${activeCompany ? activeCompany : CAT_LABELS_BASE[activeCategory as BaseCategory]} items yet`}
            desc="Add one using the button above."
          />
        ) : (
          <>
            {(() => {
              const filteredItems = (!activeCompany && companyFilter)
                ? items.filter((i) => (i.company || "") === companyFilter)
                : items;
              return (
                <>
                  {filteredItems.length === 0 && companyFilter && (
                    <div className="text-xs text-muted py-4 text-center">
                      No {companyFilter} questions in this page. Try another page or clear the filter.
                    </div>
                  )}
                  <div className="space-y-2 mt-3">
                    {filteredItems.map((item) =>
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
                          {item.company && <Badge tone={COMPANY_EXAMS.find((c) => c.key === activeCategory)?.color}>{item.company}</Badge>}
                          <button
                            onClick={(e) => { e.stopPropagation(); setEditItem(item); setShowAdd(false); }}
                            className="p-1 hover:bg-primary/10 rounded text-primary"
                            title="Edit"
                          >
                            <Pencil size={13} />
                          </button>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              const col = getDeleteCollection(activeCompany ? (companySubType as BaseCategory) : (activeCategory as BaseCategory));
                              deleteItem(col, item.id);
                            }}
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
                            {item.options && item.options.length > 0 && (
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
                </>
              );
            })()}

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

/* ------------------------------------------------------------------ */
/*  Add / Edit Question Form                                           */
/* ------------------------------------------------------------------ */

function AddQuestionForm({ category, tenantId, editItem, forceCompany, onCreated, onCancelEdit }: {
  category: BaseCategory; tenantId: string; editItem: QuestionItem | null;
  forceCompany?: string; onCreated: () => void; onCancelEdit: () => void;
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
  const [company, setCompany] = useState(forceCompany || "");

  const COMPANIES = ["", "TCS", "Infosys", "Wipro", "Accenture", "Cognizant"];

  useEffect(() => {
    if (forceCompany) setCompany(forceCompany);
  }, [forceCompany]);

  useEffect(() => {
    if (editItem) {
      setTitle(editItem.title || "");
      setBodyText(editItem.body || "");
      setKind(editItem.kind || "article");
      setStem(editItem.stem || "");
      setOptions(editItem.options?.length >= 4 ? editItem.options.slice(0, 4) : ["", "", "", ""]);
      setCorrectIndex(editItem.correct_index || 0);
      setExplanation(editItem.explanation || "");
      setPrompt(editItem.prompt || "");
      setMinWords(editItem.min_words || 150);
      setTranscript(editItem.transcript || "");
      setTaskType(editItem.task_type || "open_response");
      setPromptText(editItem.prompt_text || "");
      setReferenceText(editItem.reference_text || "");
      setCompany(editItem.company || forceCompany || "");
    }
  }, [editItem, forceCompany]);

  function getDeleteCollection(cat: BaseCategory): string {
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
        toast("success", `${CAT_LABELS_BASE[category]} question updated`);
      } else {
        await api.platformCreateQuestion(category, tenantId, body);
        toast("success", `${CAT_LABELS_BASE[category]} question added${company ? ` for ${company}` : " to all institutions"}`);
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
        {editItem ? "Edit" : "Add new"} {CAT_LABELS_BASE[category]} question
        {company ? ` for ${company}` : editItem ? "" : " (saves to all institutions)"}
      </div>
      {error && <div className="text-xs mb-3 px-2 py-1 rounded" style={{ background: "color-mix(in srgb, var(--rag-red) 10%, transparent)", color: "var(--rag-red)" }}>{error}</div>}

      <div className="grid md:grid-cols-2 gap-3">
        {!forceCompany && (
          <div>
            <label className="ds-label">Company</label>
            <select className="ds-input w-full" value={company} onChange={(e) => setCompany(e.target.value)}>
              {COMPANIES.map(c => <option key={c} value={c}>{c || "All / General"}</option>)}
            </select>
          </div>
        )}
        {forceCompany && (
          <div>
            <label className="ds-label">Company</label>
            <div className="ds-input w-full bg-surface2" style={{ opacity: 0.7 }}>{forceCompany}</div>
          </div>
        )}

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

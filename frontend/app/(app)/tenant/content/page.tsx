"use client";
import { useState } from "react";
import { BookOpen } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import {
  Badge, EmptyState, ErrorNote, PageHeader, Section, Skeleton, Table,
} from "@/components/ui";
import { api, ApiError, type ContentBankItemOut, type ContentBankSummaryRow } from "@/lib/api";
import { useData } from "@/lib/useData";

export default function TenantContentPage() {
  return (
    <RequireAuth roles={["tenant_admin"]}>
      <ContentBank />
    </RequireAuth>
  );
}

const SOURCE_LABEL: Record<string, string> = {
  quiz: "Quiz items",
  task: "Speaking tasks",
  writing_prompt: "Writing prompts",
  reading_passage: "Reading passages",
  listening_passage: "Listening passages",
};

/** What the profile-publish guard already checks per section — see
 *  ``_sections_without_items`` on the backend — surfaced here so an admin
 *  can see the bank's shape directly instead of discovering a gap only when
 *  publishing an assessment fails. Read-only: authoring content is a
 *  separate, larger piece of work.
 */
function ContentBank() {
  const { data, loading, error } = useData(() => api.contentSummary());
  const [selected, setSelected] = useState<{ source: string; key: string } | null>(null);
  const [items, setItems] = useState<ContentBankItemOut[]>([]);
  const [itemsLoading, setItemsLoading] = useState(false);
  const [itemsError, setItemsError] = useState("");

  async function select(source: string, key: string) {
    setSelected({ source, key });
    setItemsLoading(true);
    setItemsError("");
    try {
      setItems(await api.contentItems(source, key));
    } catch (err) {
      setItemsError(err instanceof ApiError ? err.detail : "Could not load these items");
    } finally {
      setItemsLoading(false);
    }
  }

  const bySource = (data ?? []).reduce<Record<string, ContentBankSummaryRow[]>>((acc, row) => {
    (acc[row.source] ??= []).push(row);
    return acc;
  }, {});

  return (
    <>
      <PageHeader
        title="Item bank"
        sub="What the assessments in Assessments actually draw on. A category with zero items is a section that will publish short or empty."
      />

      {loading ? <Skeleton rows={5} /> : error ? <ErrorNote message={error} /> : (
        !data || data.every((r) => r.count === 0) ? (
          <EmptyState icon={BookOpen} title="No published content yet"
                      desc="Nothing in the bank has status=published for this institution." />
        ) : (
          <div className="space-y-4">
            {Object.entries(SOURCE_LABEL).map(([source, label]) => {
              const rows = bySource[source] ?? [];
              const total = rows.reduce((n, r) => n + r.count, 0);
              return (
                <Section key={source} title={`${label} · ${total}`}>
                  <div className="flex flex-wrap gap-2">
                    {rows.filter((r) => r.count > 0).map((r) => (
                      <button
                        key={r.key || "_"}
                        onClick={() => select(source, r.key)}
                        className="chip ds-focus transition-colors"
                        style={
                          selected?.source === source && selected?.key === r.key
                            ? { background: "var(--primary)", color: "#fff", borderColor: "var(--primary)" }
                            : undefined
                        }
                      >
                        {r.key || label} <span className="opacity-70">· {r.count}</span>
                      </button>
                    ))}
                    {rows.length === 0 && (
                      <Badge tone="var(--rag-red)">nothing published</Badge>
                    )}
                  </div>
                </Section>
              );
            })}
          </div>
        )
      )}

      {selected && (
        <Section
          className="mt-4"
          title={`${SOURCE_LABEL[selected.source]}${selected.key ? ` — ${selected.key}` : ""}`}
        >
          {itemsLoading ? <Skeleton rows={4} /> : itemsError ? <ErrorNote message={itemsError} /> : (
            <Table
              columns={["Title", "Status", "Difficulty"]}
              rows={items.map((it) => [
                <span key="t" className="line-clamp-2 max-w-lg">{it.title || "(untitled)"}</span>,
                <Badge key="s" tone={it.status === "published" ? "var(--rag-green)" : "var(--muted)"}>
                  {it.status}
                </Badge>,
                it.difficulty.toFixed(2),
              ])}
            />
          )}
        </Section>
      )}
    </>
  );
}

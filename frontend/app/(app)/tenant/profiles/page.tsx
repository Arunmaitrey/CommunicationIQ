"use client";
import { useEffect, useState } from "react";
import { Layers, Play, CheckCircle } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { ErrorNote, PageHeader, Section, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";

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

  useEffect(() => {
    (async () => {
      try {
        const data = await api.tenantProfiles();
        setProfiles(data);
      } catch (e: any) {
        setError(e?.message || "Failed to load");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

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
          No assessments configured yet. Ask your platform admin to create one.
        </div>
      )}
    </>
  );
}

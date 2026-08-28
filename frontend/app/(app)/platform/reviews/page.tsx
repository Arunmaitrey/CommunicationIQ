"use client";
import { Star } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { EmptyState, ErrorNote, PageHeader, Section, Skeleton, Table } from "@/components/ui";
import { api, type ReviewRow } from "@/lib/api";
import { PLATFORM_ROLES } from "@/lib/roles";
import { useData } from "@/lib/useData";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
  PieChart, Pie, Legend,
} from "recharts";

function Stars({ rating }: { rating: number }) {
  return (
    <span className="inline-flex gap-0.5">
      {[1, 2, 3, 4, 5].map((i) => (
        <Star
          key={i}
          size={14}
          className={i <= rating ? "text-amber-400 fill-amber-400" : "text-muted/30"}
        />
      ))}
    </span>
  );
}

function DifficultyBadge({ d }: { d: string }) {
  const label = d === "easy" ? "Easy" : d === "hard" ? "Hard" : "Just Right";
  const cls =
    d === "easy"
      ? "bg-emerald-500/15 text-emerald-400"
      : d === "hard"
        ? "bg-rose-500/15 text-rose-400"
        : "bg-amber-500/15 text-amber-400";
  return <span className={`badge text-[10px] ${cls}`}>{label}</span>;
}

export default function PlatformReviewsPage() {
  return (
    <RequireAuth roles={PLATFORM_ROLES}>
      <Reviews />
    </RequireAuth>
  );
}

function Reviews() {
  const { data, loading, error } = useData(() => api.platformReviews());

  if (loading) return <><PageHeader title="Reviews" sub="Student feedback on completed exams." /><Skeleton rows={6} /></>;
  if (error) return <><PageHeader title="Reviews" sub="Student feedback on completed exams." /><ErrorNote message={error} /></>;

  const reviews = data ?? [];

  // Chart data
  const ratingDist = [1, 2, 3, 4, 5].map((r) => ({
    name: `${r} star${r > 1 ? "s" : ""}`,
    value: reviews.filter((rev) => rev.rating === r).length,
  }));
  const difficultyDist = [
    { name: "Easy", value: reviews.filter((r) => r.difficulty === "easy").length, color: "var(--rag-green)" },
    { name: "Just Right", value: reviews.filter((r) => r.difficulty === "just_right").length, color: "var(--rag-amber)" },
    { name: "Hard", value: reviews.filter((r) => r.difficulty === "hard").length, color: "var(--rag-red)" },
  ];
  const avgRating = reviews.length > 0 ? reviews.reduce((s, r) => s + r.rating, 0) / reviews.length : 0;

  // Institution distribution
  const tenantMap = new Map<string, number>();
  reviews.forEach((r) => {
    const name = r.tenant_id || "Unknown";
    tenantMap.set(name, (tenantMap.get(name) || 0) + 1);
  });
  const tenantDist = Array.from(tenantMap.entries()).map(([name, value]) => ({ name: name.length > 15 ? name.slice(0, 15) + '...' : name, value }));

  return (
    <>
      <PageHeader
        title="Reviews"
        sub={`${reviews.length} student review${reviews.length !== 1 ? "s" : ""} across all institutions. Average rating: ${avgRating.toFixed(1)}/5`}
      />

      {reviews.length > 0 && (
        <div className="grid md:grid-cols-3 gap-4 mb-4">
          <Section title="Rating distribution">
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={ratingDist} barSize={24}>
                  <XAxis dataKey="name" tick={{ fontSize: 9 }} />
                  <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                  <Tooltip />
                  <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                    {ratingDist.map((_, i) => (
                      <Cell key={i} fill={i >= 3 ? "var(--rag-green)" : i >= 2 ? "var(--rag-amber)" : "var(--rag-red)"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Section>

          <Section title="Difficulty perception">
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={difficultyDist}
                    cx="50%"
                    cy="50%"
                    innerRadius={30}
                    outerRadius={55}
                    paddingAngle={3}
                    dataKey="value"
                    label={({ name, percent }) => `${name} ${((percent ?? 0) * 100).toFixed(0)}%`}
                    labelLine={false}
                  >
                    {difficultyDist.map((d, i) => (
                      <Cell key={i} fill={d.color} />
                    ))}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </Section>

          <Section title="Reviews by institution">
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={tenantDist} barSize={24}>
                  <XAxis dataKey="name" tick={{ fontSize: 9 }} interval={0} angle={-30} textAnchor="end" height={50} />
                  <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                  <Tooltip />
                  <Bar dataKey="value" radius={[4, 4, 0, 0]} fill="var(--primary)" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Section>
        </div>
      )}

      <Section>
        {reviews.length === 0 ? (
          <EmptyState icon={Star} title="No reviews" desc="No reviews have been submitted yet." />
        ) : (
          <Table
            columns={["Student", "Institution", "Assessment", "Rating", "Difficulty", "Comment", "Date"]}
            rows={reviews.map((r: ReviewRow) => [
              <div key="name">
                <div className="text-sm font-medium">{r.user_name || "—"}</div>
                <div className="text-[10px] text-muted">{r.user_email}</div>
              </div>,
              r.tenant_id ? <span className="badge bg-sky-500/15 text-sky-400 text-[10px]">{r.tenant_id}</span> : "—",
              r.profile_name || "—",
              <Stars key="stars" rating={r.rating} />,
              <DifficultyBadge key="diff" d={r.difficulty} />,
              <span key="comment" className="text-xs text-muted max-w-[200px] truncate block" title={r.comment || ""}>
                {r.comment || "—"}
              </span>,
              r.created_at ? new Date(r.created_at).toLocaleDateString() : "—",
            ])}
          />
        )}
      </Section>
    </>
  );
}

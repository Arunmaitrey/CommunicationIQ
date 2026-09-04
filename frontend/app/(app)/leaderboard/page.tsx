"use client";
import { useEffect, useMemo, useState } from "react";
import { Medal, Search, Trophy, Users, Building2 } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { PageHeader, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { STUDENT_ROLES } from "@/lib/roles";

export default function LeaderboardPage() {
  return (
    <RequireAuth roles={STUDENT_ROLES}>
      <Leaderboard />
    </RequireAuth>
  );
}

interface Row {
  rank: number;
  user_id: string;
  full_name: string;
  email: string;
  roll_number: string;
  institution: string;
  best_score: number;
  attempts: number;
  last_attempt_at?: string | null;
  is_me: boolean;
}

function rankColor(rank: number): string {
  if (rank === 1) return "#f59e0b";
  if (rank === 2) return "#94a3b8";
  if (rank === 3) return "#b45309";
  return "var(--muted)";
}

function Leaderboard() {
  const [scope, setScope] = useState<"institution" | "global">("institution");
  const [rows, setRows] = useState<Row[]>([]);
  const [me, setMe] = useState<{ rank: number; best_score: number } | null>(null);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [instFilter, setInstFilter] = useState("");

  const load = async (s: "institution" | "global") => {
    setLoading(true);
    try {
      const data = await api.studentLeaderboard(s);
      setRows(data?.rows ?? []);
      setMe(data?.me ?? null);
      setTotal(data?.total ?? 0);
      setInstFilter("");
    } catch {
      setRows([]);
    }
    setLoading(false);
  };

  useEffect(() => { void load(scope); }, [scope]);

  const institutions = useMemo(
    () => Array.from(new Set(rows.map((r) => r.institution).filter(Boolean))).sort(),
    [rows],
  );

  const visible = useMemo(() => {
    let out = rows;
    if (query.trim()) {
      const q = query.trim().toLowerCase();
      out = out.filter((r) =>
        r.full_name.toLowerCase().includes(q)
        || r.email.toLowerCase().includes(q)
        || (r.roll_number || "").toLowerCase().includes(q));
    }
    if (scope === "global" && instFilter) out = out.filter((r) => r.institution === instFilter);
    return out;
  }, [rows, query, instFilter, scope]);

  return (
    <>
      <PageHeader
        title="Leaderboard"
        sub={`${total} ranked student${total === 1 ? "" : "s"} · best overall exam score`}
      />

      {/* Scope toggle + filters */}
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <div className="flex rounded-lg overflow-hidden border" style={{ borderColor: "var(--border)" }}>
          {([["institution", "My institution"], ["global", "All institutions"]] as const).map(([key, label]) => (
            <button key={key}
              onClick={() => setScope(key)}
              className="px-3 py-1.5 text-[11px] font-semibold transition-colors flex items-center gap-1.5"
              style={{
                background: scope === key ? "var(--primary)" : "transparent",
                color: scope === key ? "white" : "var(--muted)",
              }}>
              {key === "institution" ? <Building2 size={12} /> : <Trophy size={12} />}
              {label}
            </button>
          ))}
        </div>

        <div className="relative flex-1 min-w-[160px] max-w-xs">
          <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2" style={{ color: "var(--muted)" }} />
          <input value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search name, email, roll…"
            className="w-full pl-8 pr-3 py-1.5 text-[11px] rounded-md border bg-transparent"
            style={{ borderColor: "var(--border)" }} />
        </div>

        {scope === "global" && institutions.length > 1 && (
          <select value={instFilter}
            onChange={(e) => setInstFilter(e.target.value)}
            className="px-2 py-1.5 text-[11px] rounded-md border bg-transparent"
            style={{ borderColor: "var(--border)" }}>
            <option value="">All institutions</option>
            {institutions.map((i) => <option key={i} value={i}>{i}</option>)}
          </select>
        )}
      </div>

      {/* Personal standing card */}
      {me && (
        <div className="ds-card p-4 mb-4 flex items-center gap-3"
          style={{ background: "color-mix(in srgb, var(--primary) 6%, transparent)" }}>
          <Medal size={22} style={{ color: "var(--primary)" }} />
          <div className="text-xs">
            <span className="font-bold">You are ranked #{me.rank}</span>
            <span className="text-muted"> of {total} · best score {me.best_score}</span>
          </div>
        </div>
      )}

      {loading ? (
        <Skeleton rows={6} />
      ) : visible.length === 0 ? (
        <div className="ds-card p-10 text-center">
          <Trophy size={32} className="mx-auto mb-2 text-muted" />
          <div className="text-sm font-semibold mb-1">No rankings yet</div>
          <div className="text-[11px] text-muted">Take a scored exam to appear on the board.</div>
        </div>
      ) : (
        <div className="ds-card overflow-hidden">
          <table className="w-full text-left">
            <thead>
              <tr className="text-[10px] uppercase tracking-wider text-muted border-b"
                style={{ borderColor: "var(--border)" }}>
                <th className="px-3 py-2 font-bold w-12">#</th>
                <th className="px-3 py-2 font-bold">Student</th>
                {scope === "global" && <th className="px-3 py-2 font-bold">Institution</th>}
                <th className="px-3 py-2 font-bold text-right">Best score</th>
                <th className="px-3 py-2 font-bold text-right">Attempts</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((r) => (
                <tr key={r.user_id}
                  className="text-xs border-b last:border-0"
                  style={{
                    borderColor: "var(--border)",
                    background: r.is_me ? "color-mix(in srgb, var(--primary) 8%, transparent)" : "transparent",
                  }}>
                  <td className="px-3 py-2.5">
                    <span className="font-bold text-[13px]" style={{ color: rankColor(r.rank) }}>
                      {r.rank <= 3 ? <Medal size={14} className="inline mr-1" style={{ color: rankColor(r.rank) }} /> : null}
                      {r.rank}
                    </span>
                  </td>
                  <td className="px-3 py-2.5">
                    <div className="font-semibold">
                      {r.full_name || r.email}
                      {r.is_me && <span className="ml-1.5 text-[9px] px-1 py-0.5 rounded font-bold"
                        style={{ background: "var(--primary)", color: "white" }}>You</span>}
                    </div>
                    <div className="text-[10px] text-muted">{r.email}{r.roll_number ? ` · ${r.roll_number}` : ""}</div>
                  </td>
                  {scope === "global" && (
                    <td className="px-3 py-2.5 text-muted">{r.institution || "—"}</td>
                  )}
                  <td className="px-3 py-2.5 text-right">
                    <span className="font-bold" style={{ color: "var(--primary)" }}>{r.best_score}</span>
                  </td>
                  <td className="px-3 py-2.5 text-right text-muted">{r.attempts}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

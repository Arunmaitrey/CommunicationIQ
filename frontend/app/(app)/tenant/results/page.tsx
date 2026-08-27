"use client";
import { useState } from "react";
import { ChevronDown, Clock, Download, ExternalLink, FileText, Globe, Search, User } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { Badge, EmptyState, ErrorNote, PageHeader, Section, Skeleton, Table, Tabs } from "@/components/ui";
import { api, attemptApi, type Attempt, type UserRow, type AttemptResult } from "@/lib/api";
import { useData } from "@/lib/useData";
import { useToast } from "@/components/Toast";

export default function TenantResultsPage() {
  return (
    <RequireAuth roles={["tenant_admin"]}>
      <Results />
    </RequireAuth>
  );
}

function Results() {
  const { toast } = useToast();
  const [selectedStudent, setSelectedStudent] = useState<string>("");
  const [searchTerm, setSearchTerm] = useState("");

  // Get all users
  const users = useData(() => api.tenantUsers());
  const cohorts = useData(() => api.tenantCohorts());

  const students = (users.data ?? []).filter((u) => u.role === "student");
  const filteredStudents = searchTerm
    ? students.filter((s) =>
        s.full_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        s.email.toLowerCase().includes(searchTerm.toLowerCase()) ||
        (s.roll_number || "").toLowerCase().includes(searchTerm.toLowerCase())
      )
    : students;

  const selectedUserData = students.find((s) => s.id === selectedStudent);

  // Summary stats
  const totalStudents = students.length;
  const activeStudents = students.filter((s) => s.active).length;
  const totalCohorts = cohorts.data?.length ?? 0;

  return (
    <>
      <PageHeader
        title="Exam Results"
        sub="Select a student to view their exam history, scores, and downloadable reports."
      />

      {/* Summary stats */}
      <div className="grid sm:grid-cols-3 gap-3 mb-4">
        <div className="ds-card p-4">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-muted">Total students</div>
          <div className="text-2xl font-bold mt-2" style={{ color: "var(--primary)" }}>{totalStudents}</div>
        </div>
        <div className="ds-card p-4">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-muted">Active students</div>
          <div className="text-2xl font-bold mt-2" style={{ color: "var(--rag-green)" }}>{activeStudents}</div>
        </div>
        <div className="ds-card p-4">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-muted">Cohorts</div>
          <div className="text-2xl font-bold mt-2" style={{ color: "var(--accent)" }}>{totalCohorts}</div>
        </div>
      </div>

      {/* Student selector */}
      <Section title="Select student" className="mb-4">
        {users.loading ? <Skeleton rows={2} /> : users.error ? <ErrorNote message={users.error} /> : (
          <div className="space-y-3">
            {/* Search */}
            <div className="relative">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
              <input
                type="text"
                placeholder="Search by name, email or roll number..."
                value={searchTerm}
                onChange={(e) => { setSearchTerm(e.target.value); setSelectedStudent(""); }}
                className="w-full pl-9 pr-3 py-2 text-[13px] bg-surface border border-border rounded-lg ds-focus"
              />
            </div>

            {/* Student dropdown */}
            <div className="grid sm:grid-cols-2 md:grid-cols-3 gap-2">
              {filteredStudents.slice(0, 50).map((s) => (
                <button
                  key={s.id}
                  onClick={() => setSelectedStudent(s.id)}
                  className={`flex items-center gap-2.5 p-2.5 rounded-lg text-left text-[12px] transition-colors ${
                    selectedStudent === s.id
                      ? "ring-2"
                      : "hover:bg-surface"
                  }`}
                  style={selectedStudent === s.id
                    ? { background: "color-mix(in srgb, var(--primary) 8%, transparent)", borderColor: "var(--primary)", borderWidth: 1 }
                    : { background: "var(--surface)", border: "1px solid var(--border)" }
                  }
                >
                  <div className="w-7 h-7 rounded-full flex items-center justify-center text-[10px] font-bold shrink-0"
                       style={{ background: "color-mix(in srgb, var(--primary) 15%, transparent)", color: "var(--primary)" }}>
                    {s.full_name.charAt(0).toUpperCase()}
                  </div>
                  <div className="min-w-0">
                    <div className="font-medium truncate">{s.full_name}</div>
                    <div className="text-[10px] text-muted truncate">{s.roll_number || s.email}</div>
                  </div>
                </button>
              ))}
            </div>
            {filteredStudents.length > 50 && (
              <p className="text-[10px] text-muted">Showing 50 of {filteredStudents.length} students. Use search to narrow.</p>
            )}
          </div>
        )}
      </Section>

      {/* Student attempt history */}
      {selectedStudent && (
        <StudentAttemptHistory
          studentId={selectedStudent}
          student={selectedUserData}
        />
      )}

      {!selectedStudent && (
        <EmptyState
          icon={User}
          title="Select a student"
          desc="Choose a student above to view their exam history and download reports."
        />
      )}
    </>
  );
}

function StudentAttemptHistory({ studentId, student }: { studentId: string; student?: UserRow }) {
  const { toast } = useToast();
  const [expandedAttempt, setExpandedAttempt] = useState<string | null>(null);

  const attempts = useData(() => api.cohortStudentAttempts(studentId), [studentId]);

  const scoredAttempts = (attempts.data ?? []).filter((a) => a.status === "scored");
  const inProgressAttempts = (attempts.data ?? []).filter((a) =>
    a.status === "in_progress" || a.status === "created" || a.status === "scoring"
  );

  // Calculate best scores
  const bestOverall = scoredAttempts.length > 0
    ? Math.max(...scoredAttempts.map((a) => a.overall_score ?? 0))
    : null;

  return (
    <Section title={`Exam history — ${student?.full_name ?? "Student"}`} className="mb-4">
      {attempts.loading ? <Skeleton rows={4} /> : attempts.error ? <ErrorNote message={attempts.error} /> : (
        <>
          {/* Quick stats for this student */}
          <div className="grid sm:grid-cols-4 gap-3 mb-4">
            <div className="p-3 rounded-lg" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
              <div className="text-[10px] font-semibold uppercase text-muted">Total attempts</div>
              <div className="text-lg font-bold mt-1" style={{ color: "var(--primary)" }}>
                {attempts.data?.length ?? 0}
              </div>
            </div>
            <div className="p-3 rounded-lg" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
              <div className="text-[10px] font-semibold uppercase text-muted">Scored</div>
              <div className="text-lg font-bold mt-1" style={{ color: "var(--rag-green)" }}>
                {scoredAttempts.length}
              </div>
            </div>
            <div className="p-3 rounded-lg" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
              <div className="text-[10px] font-semibold uppercase text-muted">In progress</div>
              <div className="text-lg font-bold mt-1" style={{ color: "var(--rag-amber)" }}>
                {inProgressAttempts.length}
              </div>
            </div>
            <div className="p-3 rounded-lg" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
              <div className="text-[10px] font-semibold uppercase text-muted">Best score</div>
              <div className="text-lg font-bold mt-1" style={{ color: "var(--accent)" }}>
                {bestOverall !== null ? bestOverall.toFixed(1) : "—"}
              </div>
            </div>
          </div>

          {/* Student info */}
          {student && (
            <div className="flex items-center gap-4 mb-4 p-3 rounded-lg" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
              <div className="w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold"
                   style={{ background: "color-mix(in srgb, var(--primary) 15%, transparent)", color: "var(--primary)" }}>
                {student.full_name.charAt(0).toUpperCase()}
              </div>
              <div>
                <div className="text-sm font-semibold">{student.full_name}</div>
                <div className="text-[11px] text-muted">{student.email}</div>
              </div>
              {student.roll_number && (
                <Badge tone="var(--secondary)">Roll: {student.roll_number}</Badge>
              )}
              {student.branch && (
                <Badge tone="var(--accent)">{student.branch}</Badge>
              )}
              <Badge tone={student.active ? "var(--rag-green)" : "var(--muted)"}>
                {student.active ? "Active" : "Inactive"}
              </Badge>
            </div>
          )}

          {/* Attempts list */}
          <Table
            columns={["Assessment", "Attempt", "Status", "Score", "Started", "Duration", "IP", "Actions"]}
            rows={(attempts.data ?? []).map((a) => {
              const isOpen = expandedAttempt === a.id;
              const duration = a.started_at && a.submitted_at
                ? Math.round((new Date(a.submitted_at).getTime() - new Date(a.started_at).getTime()) / 60000)
                : null;
              return [
                <span key="name" className="font-medium text-[12px]">{a.profile_name}</span>,
                <span key="num" className="text-[11px] text-muted">#{a.attempt_number}</span>,
                <Badge key="status" tone={
                  a.status === "scored" ? "var(--rag-green)" :
                  a.status === "scoring" ? "var(--rag-amber)" :
                  a.status === "in_progress" ? "var(--primary)" :
                  "var(--muted)"
                }>{a.status}</Badge>,
                <span key="score" className="font-semibold" style={{
                  color: a.overall_score != null
                    ? (a.overall_score >= 60 ? "var(--rag-green)" : a.overall_score >= 40 ? "var(--rag-amber)" : "var(--rag-red)")
                    : "var(--muted)"
                }}>
                  {a.overall_score != null ? (a.overall_score as number).toFixed(1) : "—"}
                </span>,
                <span key="started" className="text-[11px] text-muted">
                  {a.started_at
                    ? new Date(a.started_at).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })
                    : "—"
                  }
                </span>,
                <span key="duration" className="text-[11px] text-muted">
                  {duration !== null ? `${duration}m` : "—"}
                </span>,
                <span key="ip" className="text-[10px] text-muted font-mono">
                  {a.ip_address || "—"}
                </span>,
                <div key="actions" className="flex items-center gap-1.5">
                  {a.status === "scored" && (
                    <>
                      <button
                        onClick={() => window.open(attemptApi.reportUrl(a.id), "_blank")}
                        className="btn btn-ghost text-[10px] px-2 py-1 ds-focus"
                        title="Open report (print or save as PDF)"
                      >
                        <FileText size={11} /> Report
                      </button>
                      <a
                        href={`/results/${a.id}`}
                        className="btn btn-ghost text-[10px] px-2 py-1 ds-focus"
                      >
                        <ExternalLink size={11} /> View
                      </a>
                    </>
                  )}
                  {(a.status === "in_progress" || a.status === "created") && (
                    <a
                      href={`/attempt/${a.id}/check`}
                      className="btn btn-ghost text-[10px] px-2 py-1 ds-focus"
                    >
                      Resume
                    </a>
                  )}
                </div>,
              ];
            })}
          />

          {attempts.data?.length === 0 && (
            <EmptyState
              icon={FileText}
              title="No attempts yet"
              desc="This student has not taken any exams."
            />
          )}
        </>
      )}
    </Section>
  );
}

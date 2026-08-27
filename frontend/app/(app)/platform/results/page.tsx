"use client";
import { useState } from "react";
import { Building2, Clock, Download, ExternalLink, FileText, Globe, Search, User } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { Badge, EmptyState, ErrorNote, PageHeader, Section, Skeleton } from "@/components/ui";
import { api, attemptApi, type Attempt, type TenantRow, type UserRow } from "@/lib/api";
import { PLATFORM_ROLES } from "@/lib/roles";
import { useData } from "@/lib/useData";

export default function PlatformResultsPage() {
  return (
    <RequireAuth roles={PLATFORM_ROLES}>
      <Results />
    </RequireAuth>
  );
}

function Results() {
  const tenants = useData(() => api.platformTenants());
  const [selectedTenant, setSelectedTenant] = useState<string>("");
  const [selectedStudent, setSelectedStudent] = useState<string>("");
  const [studentSearch, setStudentSearch] = useState("");

  // Fetch students when tenant is selected
  const students = useData(
    () => selectedTenant ? api.platformTenantUsers(selectedTenant) : Promise.resolve([]),
    [selectedTenant]
  );

  const studentList = (students.data ?? []).filter((s) => s.role === "student");
  const filteredStudents = studentSearch
    ? studentList.filter((s) =>
        s.full_name.toLowerCase().includes(studentSearch.toLowerCase()) ||
        s.email.toLowerCase().includes(studentSearch.toLowerCase()) ||
        (s.roll_number || "").toLowerCase().includes(studentSearch.toLowerCase())
      )
    : studentList;

  const selectedUserData = studentList.find((s) => s.id === selectedStudent);

  // When tenant changes, reset student selection
  const handleTenantChange = (tid: string) => {
    setSelectedTenant(tid);
    setSelectedStudent("");
    setStudentSearch("");
  };

  return (
    <>
      <PageHeader
        title="Exam Results"
        sub="Select an institution, then a student to view their exam history and download reports."
      />

      {/* Institution selector */}
      <Section className="mb-4" compact>
        {tenants.loading ? <Skeleton rows={2} /> : tenants.error ? <ErrorNote message={tenants.error} /> : (
          <div className="flex items-center gap-3 flex-wrap">
            <span className="text-[11px] font-bold uppercase tracking-wider text-muted">Institution</span>
            <div className="flex gap-1.5 flex-wrap">
              {(tenants.data ?? []).map((t) => (
                <button
                  key={t.id}
                  onClick={() => handleTenantChange(t.id)}
                  className={`px-2.5 py-1 text-[11px] font-semibold rounded-lg ds-focus transition-colors flex items-center gap-1.5 ${
                    selectedTenant === t.id ? "text-white" : "text-muted hover:text-text"
                  }`}
                  style={selectedTenant === t.id ? { background: "var(--primary)" } : { background: "var(--surface)" }}
                >
                  <Building2 size={10} /> {t.name}
                </button>
              ))}
            </div>
          </div>
        )}
      </Section>

      {/* Student selector (only when tenant is selected) */}
      {selectedTenant && (
        <Section title="Select student" className="mb-4">
          {students.loading ? <Skeleton rows={2} /> : students.error ? <ErrorNote message={students.error} /> : (
            <div className="space-y-3">
              <div className="relative">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
                <input
                  type="text"
                  placeholder="Search by name, email or roll number..."
                  value={studentSearch}
                  onChange={(e) => { setStudentSearch(e.target.value); setSelectedStudent(""); }}
                  className="w-full pl-9 pr-3 py-2 text-[13px] bg-surface border border-border rounded-lg ds-focus"
                />
              </div>
              <div className="grid sm:grid-cols-2 md:grid-cols-4 gap-2">
                {filteredStudents.slice(0, 40).map((s) => (
                  <button
                    key={s.id}
                    onClick={() => setSelectedStudent(s.id)}
                    className={`flex items-center gap-2 p-2 rounded-lg text-left text-[12px] transition-colors ${
                      selectedStudent === s.id ? "ring-2" : "hover:bg-surface"
                    }`}
                    style={selectedStudent === s.id
                      ? { background: "color-mix(in srgb, var(--primary) 8%, transparent)", borderWidth: 1 }
                      : { background: "var(--surface)", border: "1px solid var(--border)" }
                    }
                  >
                    <div className="w-6 h-6 rounded-full flex items-center justify-center text-[9px] font-bold shrink-0"
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
              {filteredStudents.length > 40 && (
                <p className="text-[10px] text-muted">Showing 40 of {filteredStudents.length}. Use search to narrow.</p>
              )}
            </div>
          )}
        </Section>
      )}

      {/* Attempt history */}
      {selectedTenant && selectedStudent && (
        <StudentAttemptHistory
          studentId={selectedStudent}
          tenantId={selectedTenant}
          student={selectedUserData}
        />
      )}

      {!selectedTenant && (
        <EmptyState
          icon={Building2}
          title="Select an institution"
          desc="Choose an institution above to browse its students and exam results."
        />
      )}

      {selectedTenant && !selectedStudent && (
        <EmptyState
          icon={User}
          title="Select a student"
          desc="Choose a student above to view their exam history and download reports."
        />
      )}

      {/* Quick stats */}
      <div className="grid sm:grid-cols-3 gap-3 mt-4">
        <div className="ds-card p-4">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-muted">Total institutions</div>
          <div className="text-2xl font-bold mt-2" style={{ color: "var(--primary)" }}>
            {(tenants.data ?? []).length}
          </div>
        </div>
        <div className="ds-card p-4">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-muted">Active institutions</div>
          <div className="text-2xl font-bold mt-2" style={{ color: "var(--rag-green)" }}>
            {(tenants.data ?? []).filter((t) => t.status === "active").length}
          </div>
        </div>
        <div className="ds-card p-4">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-muted">Total seats</div>
          <div className="text-2xl font-bold mt-2" style={{ color: "var(--accent)" }}>
            {(tenants.data ?? []).reduce((sum, t) => sum + t.seat_limit, 0)}
          </div>
        </div>
      </div>
    </>
  );
}

function StudentAttemptHistory({ studentId, tenantId, student }: {
  studentId: string; tenantId: string; student?: UserRow;
}) {
  const attempts = useData(() => api.platformStudentAttempts(studentId, tenantId), [studentId, tenantId]);

  const scoredAttempts = (attempts.data ?? []).filter((a) => a.status === "scored");
  const bestOverall = scoredAttempts.length > 0
    ? Math.max(...scoredAttempts.map((a) => a.overall_score ?? 0))
    : null;

  return (
    <Section title={`Exam history — ${student?.full_name ?? "Student"}`} className="mb-4">
      {attempts.loading ? <Skeleton rows={4} /> : attempts.error ? <ErrorNote message={attempts.error} /> : (
        <>
          {/* Quick stats */}
          <div className="grid sm:grid-cols-4 gap-3 mb-4">
            <div className="p-3 rounded-lg" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
              <div className="text-[10px] font-semibold uppercase text-muted">Total attempts</div>
              <div className="text-lg font-bold mt-1" style={{ color: "var(--primary)" }}>{attempts.data?.length ?? 0}</div>
            </div>
            <div className="p-3 rounded-lg" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
              <div className="text-[10px] font-semibold uppercase text-muted">Scored</div>
              <div className="text-lg font-bold mt-1" style={{ color: "var(--rag-green)" }}>{scoredAttempts.length}</div>
            </div>
            <div className="p-3 rounded-lg" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
              <div className="text-[10px] font-semibold uppercase text-muted">In progress</div>
              <div className="text-lg font-bold mt-1" style={{ color: "var(--rag-amber)" }}>
                {(attempts.data ?? []).filter((a) => a.status !== "scored").length}
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
              {student.roll_number && <Badge tone="var(--secondary)">Roll: {student.roll_number}</Badge>}
              {student.branch && <Badge tone="var(--accent)">{student.branch}</Badge>}
            </div>
          )}

          {/* Attempts */}
          <div className="space-y-2">
            {(attempts.data ?? []).map((a) => {
              const duration = a.started_at && a.submitted_at
                ? Math.round((new Date(a.submitted_at).getTime() - new Date(a.started_at).getTime()) / 60000)
                : null;
              return (
              <div key={a.id} className="flex items-center justify-between p-3 rounded-lg"
                   style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
                <div className="flex items-center gap-4">
                  <div className="min-w-0">
                    <div className="text-[12px] font-medium">{a.profile_name || "Unnamed assessment"}</div>
                    <div className="text-[10px] text-muted flex items-center gap-2">
                      <span>Attempt #{a.attempt_number} — {a.mode}</span>
                      {a.started_at && (
                        <span className="flex items-center gap-1">
                          <Clock size={9} />
                          {new Date(a.started_at).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
                        </span>
                      )}
                      {duration !== null && <span>{duration}m</span>}
                      {a.ip_address && (
                        <span className="flex items-center gap-1 font-mono">
                          <Globe size={9} />{a.ip_address}
                        </span>
                      )}
                    </div>
                  </div>
                  <Badge tone={
                    a.status === "scored" ? "var(--rag-green)" :
                    a.status === "scoring" ? "var(--rag-amber)" : "var(--muted)"
                  }>{a.status}</Badge>
                  {a.overall_score != null && (
                    <span className="text-sm font-bold" style={{
                      color: (a.overall_score as number) >= 60 ? "var(--rag-green)" : (a.overall_score as number) >= 40 ? "var(--rag-amber)" : "var(--rag-red)"
                    }}>
                      {(a.overall_score as number).toFixed(1)}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  {a.status === "scored" && (
                    <>
                      <button
                        onClick={() => window.open(attemptApi.reportUrl(a.id), "_blank")}
                        className="btn btn-ghost text-[10px] px-2 py-1 ds-focus"
                        title="Open report (print or save as PDF)"
                      >
                        <FileText size={11} /> Report
                      </button>
                      <a href={`/results/${a.id}`} className="btn btn-ghost text-[10px] px-2 py-1 ds-focus">
                        <ExternalLink size={11} /> View
                      </a>
                    </>
                  )}
                </div>
              </div>
            );
            })}
          </div>

          {attempts.data?.length === 0 && (
            <EmptyState icon={FileText} title="No attempts yet" desc="This student has not taken any exams." />
          )}
        </>
      )}
    </Section>
  );
}

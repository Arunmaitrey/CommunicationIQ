"use client";
import { useState, useEffect } from "react";
import { CalendarClock, Plus, X, Trash2, Save, Clock, Users, Layers, Edit } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { PageHeader } from "@/components/ui";
import { PLATFORM_ROLES } from "@/lib/roles";
import { api, type ExamTestSummary, type ScheduleRow, type TenantRow } from "@/lib/api";
import { useToast } from "@/components/Toast";

export default function ExamSchedulesPage() {
  return (
    <RequireAuth roles={PLATFORM_ROLES}>
      <ExamSchedules />
    </RequireAuth>
  );
}

interface ScheduleForm {
  exam_test_id: string;
  tenant_ids: string[];
  starts_at: string;
  ends_at: string;
  max_attempts: number;
  is_active: boolean;
}

function toLocalInput(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function ExamSchedules() {
  const { toast } = useToast();
  const [schedules, setSchedules] = useState<ScheduleRow[]>([]);
  const [tests, setTests] = useState<ExamTestSummary[]>([]);
  const [tenants, setTenants] = useState<TenantRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<ScheduleRow | null>(null);
  const [allInstitutions, setAllInstitutions] = useState(true);
  const [form, setForm] = useState<ScheduleForm>({
    exam_test_id: "",
    tenant_ids: [],
    starts_at: "",
    ends_at: "",
    max_attempts: 1,
    is_active: true,
  });

  const load = async () => {
    setLoading(true);
    try {
      const [schedRes, testsRes, tenantsRes] = await Promise.all([
        api.platformExamSchedules(),
        api.platformExamTests(),
        api.platformTenants(),
      ]);
      setSchedules(schedRes ?? []);
      setTests(testsRes ?? []);
      setTenants(tenantsRes ?? []);
    } catch (e) {
      toast("error", (e instanceof Error ? e.message : String(e)) || "Failed to load schedules");
    }
    setLoading(false);
  };

  useEffect(() => { void load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const set = <K extends keyof ScheduleForm>(k: K, v: ScheduleForm[K]) => setForm((prev) => ({ ...prev, [k]: v }));

  const toggleTenant = (id: string) => {
    setForm((prev) => ({
      ...prev,
      tenant_ids: prev.tenant_ids.includes(id)
        ? prev.tenant_ids.filter((x) => x !== id)
        : [...prev.tenant_ids, id],
    }));
  };

  const openCreate = () => {
    setEditing(null);
    setAllInstitutions(true);
    setForm({
      exam_test_id: tests[0]?.id ?? "",
      tenant_ids: [],
      starts_at: "",
      ends_at: "",
      max_attempts: 1,
      is_active: true,
    });
    setShowForm(true);
  };

  const openEdit = (s: ScheduleRow) => {
    setEditing(s);
    const isAll = !s.institutions || s.institutions.length === 0
      || s.institutions.some((i) => i.id === "");
    setAllInstitutions(isAll);
    setForm({
      exam_test_id: s.exam_test_id,
      tenant_ids: isAll ? [] : (s.institutions ?? []).map((i) => i.id),
      starts_at: toLocalInput(s.starts_at),
      ends_at: toLocalInput(s.ends_at),
      max_attempts: s.max_attempts,
      is_active: s.is_active,
    });
    setShowForm(true);
  };

  const save = async () => {
    if (!form.exam_test_id) { toast("error", "Select an exam test"); return; }
    if (!form.starts_at || !form.ends_at) { toast("error", "Set the start and end of the window"); return; }
    const starts = new Date(form.starts_at);
    const ends = new Date(form.ends_at);
    if (ends <= starts) { toast("error", "End must be after start"); return; }
    const body = {
      exam_test_id: form.exam_test_id,
      tenant_ids: allInstitutions ? [] : form.tenant_ids,
      starts_at: starts.toISOString(),
      ends_at: ends.toISOString(),
      max_attempts: form.max_attempts,
      is_active: form.is_active,
    };
    try {
      if (editing) {
        await api.updateExamSchedule(editing.id, body);
        toast("success", "Schedule updated");
      } else {
        await api.createExamSchedule(body);
        toast("success", "Exam scheduled");
      }
      setShowForm(false);
      setEditing(null);
      await load();
    } catch (e) {
      toast("error", (e instanceof Error ? e.message : String(e)) || "Failed to save schedule");
    }
  };

  const remove = async (id: string) => {
    if (!confirm("Delete this schedule? Students can no longer start it.")) return;
    try {
      await api.deleteExamSchedule(id);
      toast("success", "Schedule deleted");
      await load();
    } catch (e) {
      toast("error", (e instanceof Error ? e.message : String(e)) || "Failed to delete");
    }
  };

  const selectedTest = tests.find((t) => t.id === form.exam_test_id) ?? null;
  const totalQ = selectedTest
    ? (selectedTest.reading_questions + selectedTest.listening_questions
       + selectedTest.writing_questions + selectedTest.speaking_questions)
    : 0;

  const statusTone = (s: string) =>
    s === "live" ? "var(--rag-green)" : s === "upcoming" ? "var(--rag-amber)" : "var(--muted)";

  /** Flip a schedule's active flag without opening the form. */
  const toggleActive = async (s: ScheduleRow) => {
    try {
      await api.updateExamSchedule(s.id, {
        exam_test_id: s.exam_test_id,
        tenant_ids: s.institutions?.some((i) => i.id === "") ? [] : (s.institutions ?? []).map((i) => i.id),
        starts_at: s.starts_at,
        ends_at: s.ends_at,
        max_attempts: s.max_attempts,
        is_active: !s.is_active,
      });
      toast("success", s.is_active ? "Schedule deactivated — hidden from students" : "Schedule activated — visible to students");
      await load();
    } catch (e) {
      toast("error", (e instanceof Error ? e.message : String(e)) || "Failed to update schedule");
    }
  };

  return (
    <>
      <PageHeader
        title="Exam Schedules"
        sub={`${schedules.length} scheduled exam${schedules.length === 1 ? "" : "s"}`}
        action={
          <button onClick={openCreate}
            className="px-3 py-1.5 text-xs rounded-md text-white flex items-center gap-1.5"
            style={{ background: "var(--brand-grad)" }}>
            <Plus size={12} /> Schedule Exam
          </button>
        }
      />

      {showForm && (
        <div className="ds-card p-5 mb-4">
          <div className="flex items-center justify-between mb-4">
            <div className="text-sm font-bold">{editing ? "Edit Schedule" : "Schedule an Exam"}</div>
            <button onClick={() => { setShowForm(false); setEditing(null); }}><X size={14} className="text-muted" /></button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="md:col-span-2">
              <label className="block text-[11px] font-semibold mb-1">Exam Test *</label>
              <select value={form.exam_test_id}
                onChange={(e) => set("exam_test_id", e.target.value)}
                className="w-full px-3 py-2 text-xs rounded-md border bg-transparent"
                style={{ borderColor: "var(--border)" }}>
                <option value="">Select a test…</option>
                {tests.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}{t.company ? ` (${t.company})` : ""} — {t.duration_minutes} min
                  </option>
                ))}
              </select>
              {selectedTest && (
                <div className="mt-2 p-3 rounded flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-muted"
                  style={{ background: "var(--surface-2)" }}>
                  <span className="flex items-center gap-1"><Clock size={10} /> {selectedTest.duration_minutes} min</span>
                  <span>Reading {selectedTest.reading_questions} × {Math.round(selectedTest.reading_seconds / Math.max(selectedTest.reading_questions, 1))}s</span>
                  <span>Listening {selectedTest.listening_questions} × {Math.round(selectedTest.listening_seconds / Math.max(selectedTest.listening_questions, 1))}s</span>
                  <span>Writing {selectedTest.writing_questions} × {Math.round(selectedTest.writing_seconds / Math.max(selectedTest.writing_questions, 1))}s</span>
                  <span>Speaking {selectedTest.speaking_questions} × {Math.round(selectedTest.speaking_seconds / Math.max(selectedTest.speaking_questions, 1))}s</span>
                  <span className="font-semibold">Total: {totalQ} questions</span>
                </div>
              )}
            </div>

            <div>
              <label className="block text-[11px] font-semibold mb-1">Opens at *</label>
              <input type="datetime-local" value={form.starts_at}
                onChange={(e) => set("starts_at", e.target.value)}
                className="w-full px-3 py-2 text-xs rounded-md border bg-transparent"
                style={{ borderColor: "var(--border)" }} />
            </div>
            <div>
              <label className="block text-[11px] font-semibold mb-1">Closes at *</label>
              <input type="datetime-local" value={form.ends_at}
                onChange={(e) => set("ends_at", e.target.value)}
                className="w-full px-3 py-2 text-xs rounded-md border bg-transparent"
                style={{ borderColor: "var(--border)" }} />
            </div>
            <div>
              <label className="block text-[11px] font-semibold mb-1">Attempts per student (0 = unlimited)</label>
              <input type="number" min={0} max={50} value={form.max_attempts}
                onChange={(e) => set("max_attempts", +e.target.value)}
                className="w-full px-3 py-2 text-xs rounded-md border bg-transparent"
                style={{ borderColor: "var(--border)" }} />
            </div>
            <div>
              <label className="flex items-center gap-1.5 text-[11px] font-semibold cursor-pointer mt-6">
                <input type="checkbox" checked={form.is_active}
                  onChange={(e) => set("is_active", e.target.checked)} className="rounded" />
                Active
              </label>
            </div>

            <div className="md:col-span-2">
              <label className="flex items-center gap-2 text-[11px] font-semibold mb-1 cursor-pointer">
                <input type="checkbox" checked={allInstitutions}
                  onChange={(e) => { setAllInstitutions(e.target.checked); set("tenant_ids", []); }}
                  className="rounded" />
                <Users size={12} /> All institutions + general users
              </label>
              {!allInstitutions && (
                <div className="mt-2 flex flex-wrap gap-2">
                  {tenants.map((t) => (
                    <label key={t.id} className="flex items-center gap-1.5 text-[11px] px-2 py-1 rounded cursor-pointer"
                      style={{ background: form.tenant_ids.includes(t.id) ? "color-mix(in srgb, var(--primary) 15%, transparent)" : "var(--surface-2)" }}>
                      <input type="checkbox" checked={form.tenant_ids.includes(t.id)}
                        onChange={() => toggleTenant(t.id)} className="rounded" />
                      {t.name}
                    </label>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="flex justify-end gap-2 mt-4 pt-3 border-t" style={{ borderColor: "var(--border)" }}>
            <button onClick={() => { setShowForm(false); setEditing(null); }}
              className="px-3 py-1.5 text-xs rounded-md border" style={{ borderColor: "var(--border)" }}>
              Cancel
            </button>
            <button onClick={save}
              className="px-3 py-1.5 text-xs rounded-md text-white flex items-center gap-1.5"
              style={{ background: "var(--brand-grad)" }}>
              <Save size={12} /> {editing ? "Update" : "Schedule"}
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="text-xs text-muted p-4">Loading schedules...</div>
      ) : schedules.length === 0 ? (
        <div className="ds-card p-8 text-center">
          <CalendarClock size={32} className="mx-auto mb-2 text-muted" />
          <div className="text-sm text-muted mb-2">No exam schedules</div>
          <div className="text-[11px] text-muted">Pick an exam test, choose institutions and set a window to run a drive.</div>
        </div>
      ) : (
        <div className="grid gap-3">
          {schedules.map((s) => (
            <div key={s.id} className="ds-card p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <span className="text-sm font-bold">{s.name}</span>
                    <span className="px-1.5 py-0.5 rounded text-[9px] font-semibold uppercase"
                      style={{ background: `color-mix(in srgb, ${statusTone(s.status)} 14%, transparent)`, color: statusTone(s.status) }}>
                      {s.status}
                    </span>
                    {!s.is_active && <span className="px-1.5 py-0.5 rounded text-[9px] bg-surface2 text-muted">Inactive</span>}
                  </div>

                  {s.test?.description && (
                    <div className="text-[11px] text-muted mb-2">{s.test.description}</div>
                  )}

                  <div className="flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-muted">
                    <span className="flex items-center gap-1"><Clock size={10} /> {s.test?.duration_minutes ?? "–"} min</span>
                    <span className="flex items-center gap-1">
                      <Layers size={10} /> {s.test?.reading_questions ?? 0}R / {s.test?.listening_questions ?? 0}L /
                      {s.test?.writing_questions ?? 0}W / {s.test?.speaking_questions ?? 0}S
                    </span>
                    <span className="font-semibold">
                      Total: {(s.test?.reading_questions ?? 0) + (s.test?.listening_questions ?? 0)
                        + (s.test?.writing_questions ?? 0) + (s.test?.speaking_questions ?? 0)}
                    </span>
                    <span className="flex items-center gap-1"><Users size={10} />
                      {s.institutions?.length ? `${s.institutions.length} institution(s)` : "All institutions + general"}
                    </span>
                    {s.max_attempts > 0 && <span>{s.max_attempts} attempt(s) each</span>}
                  </div>

                  <div className="flex flex-wrap gap-x-4 gap-y-1 mt-1.5 text-[10px]">
                    <span className="text-muted flex items-center gap-1"><CalendarClock size={10} />
                      Opens {new Date(s.starts_at).toLocaleString()}</span>
                    <span className="text-muted flex items-center gap-1"><Clock size={10} />
                      Closes {new Date(s.ends_at).toLocaleString()}</span>
                  </div>

                  {!s.profile_id && (
                    <div className="text-[10px] mt-1.5" style={{ color: "var(--rag-red)" }}>
                      No published simulation found for this test — students cannot start it yet. Save the test or wait for the profile sync.
                    </div>
                  )}

                  {/* Live results for this schedule window */}
                  <div className="mt-2 pt-2 border-t flex flex-wrap gap-x-5 gap-y-1 text-[10px]"
                    style={{ borderColor: "var(--border)" }}>
                    <span className="text-muted">Attempts started: <strong>{s.results?.started ?? 0}</strong></span>
                    <span className="text-muted">Students: <strong>{s.results?.students ?? 0}</strong></span>
                    <span className="text-muted">Average score: <strong>
                      {s.results?.average_score != null ? `${s.results.average_score}%` : "—"}
                    </strong></span>
                  </div>
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  <button onClick={() => toggleActive(s)}
                    className="px-2 py-1.5 rounded text-[10px] font-semibold text-white"
                    style={{ background: s.is_active ? "var(--rag-red)" : "var(--rag-green)" }}
                    title={s.is_active ? "Hide this scheduled exam from students" : "Show this scheduled exam to students"}>
                    {s.is_active ? "Deactivate" : "Activate"}
                  </button>
                  <button onClick={() => openEdit(s)} className="p-1.5 rounded hover:bg-surface2 text-muted">
                    <Edit size={13} />
                  </button>
                  <button onClick={() => remove(s.id)} className="p-1.5 rounded hover:bg-surface2 text-muted hover:text-ragRed">
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}

"use client";
import { useState } from "react";
import { AlertTriangle, CheckCircle2, Copy, Upload } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import {
  Badge, ErrorNote, PageHeader, Section, Table,
} from "@/components/ui";
import { adminApi, ApiError, type ImportPreview, type ImportResult } from "@/lib/api";

export default function ImportPage() {
  return (
    <RequireAuth roles={["tenant_admin"]}>
      <ImportPeople />
    </RequireAuth>
  );
}

const SAMPLE = `Name,Email ID,Roll No,Branch,Year,Mother Tongue,Cohort
Ramya Krishnan,ramya.k@college.edu,20B81A9001,CSE,4,tamil,CSE-A Final Year
Imran Sheikh,imran.s@college.edu,20B81A9002,CSE,4,hindi,CSE-A Final Year`;

/** Bulk import (TEN-03).
 *
 *  Preview first, always. The endpoint reports every problem in a file at
 *  once rather than the first one, and this screen shows them against their
 *  line numbers — an admin fixing one error per upload gives up before row
 *  twenty.
 */
function ImportPeople() {
  const [csv, setCsv] = useState("");
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function readFile(file: File) {
    setCsv(await file.text());
    setPreview(null);
    setResult(null);
  }

  async function run(commit: boolean) {
    setBusy(true);
    setError("");
    try {
      if (commit) {
        setResult(await adminApi.commitImport(csv));
        setPreview(null);
      } else {
        setPreview(await adminApi.previewImport(csv));
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not process the file");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Import people"
        sub="Paste a spreadsheet or upload a CSV. Nothing is written until you have seen exactly what would happen."
      />

      <Section title="Your file" className="mb-4">
        <div className="flex flex-wrap items-center gap-3 mb-3">
          <label className="btn btn-ghost btn-sm ds-focus cursor-pointer">
            <Upload size={13} /> Choose a CSV
            <input type="file" accept=".csv,text/csv" className="hidden"
                   onChange={(e) => e.target.files?.[0] && void readFile(e.target.files[0])} />
          </label>
          <button onClick={() => setCsv(SAMPLE)} className="btn btn-ghost btn-sm ds-focus">
            <Copy size={13} /> Use a sample
          </button>
          <span className="text-[11px] text-muted">
            Column names are matched loosely — &ldquo;Roll No&rdquo;, &ldquo;Hall Ticket&rdquo; and
            &ldquo;Registration Number&rdquo; all work.
          </span>
        </div>

        <textarea
          className="ds-textarea ds-focus font-mono text-[11px]"
          rows={10}
          placeholder="Name,Email&#10;…"
          value={csv}
          onChange={(e) => { setCsv(e.target.value); setPreview(null); setResult(null); }}
        />

        <div className="flex items-center gap-2 mt-3">
          <button onClick={() => void run(false)} disabled={!csv.trim() || busy}
                  className="btn btn-primary ds-focus">
            {busy ? "Checking…" : "Preview"}
          </button>
          {preview?.ok && (
            <button onClick={() => void run(true)} disabled={busy}
                    className="btn btn-soft ds-focus">
              Import {preview.creating} new, update {preview.updating}
            </button>
          )}
        </div>
      </Section>

      {error && <div className="mb-4"><ErrorNote message={error} /></div>}

      {preview && (
        <Section title="What would happen" className="mb-4">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
            <Tile label="Rows" value={preview.total} />
            <Tile label="New accounts" value={preview.creating} tone="var(--rag-green)" />
            <Tile label="Updated" value={preview.updating} tone="var(--secondary)" />
            <Tile label="Seats after"
                  value={`${preview.seats_after}/${preview.seat_limit}`}
                  tone={preview.over_seat_limit ? "var(--rag-red)" : "var(--muted)"} />
          </div>

          {preview.over_seat_limit && (
            <div className="ds-card p-3 mb-3 flex items-start gap-2 text-xs"
                 style={{ borderColor: "var(--rag-red)" }}>
              <AlertTriangle size={14} className="shrink-0 mt-0.5"
                             style={{ color: "var(--rag-red)" }} />
              <span>
                This needs {preview.seats_after - preview.seat_limit} more seat(s) than
                the plan allows. The import is refused in full rather than truncated —
                a half-imported cohort is worse than a clear number.
              </span>
            </div>
          )}

          {preview.problems.length > 0 ? (
            <>
              <div className="text-xs font-bold mb-2" style={{ color: "var(--rag-red)" }}>
                {preview.problems.length} problem(s) — every one, not just the first
              </div>
              <Table
                columns={["Line", "Column", "Problem"]}
                rows={preview.problems.map((p) => [
                  p.line || "—", p.column || "—", p.message,
                ])}
              />
            </>
          ) : (
            <>
              <div className="flex items-center gap-2 text-xs mb-2"
                   style={{ color: "var(--rag-green)" }}>
                <CheckCircle2 size={14} /> No problems found
              </div>
              <Table
                columns={["Action", "Name", "Email", "Roll", "Cohort"]}
                rows={preview.sample.map((r) => [
                  r.action === "create"
                    ? <Badge key="a" tone="var(--rag-green)">create</Badge>
                    : <Badge key="a" tone="var(--secondary)">update</Badge>,
                  r.full_name, r.email, r.roll_number || "—", r.cohort || "—",
                ])}
              />
            </>
          )}
        </Section>
      )}

      {result && (
        <Section title="Imported">
          <div className="text-xs mb-3">
            {result.created} account(s) created, {result.updated} updated
            {result.cohorts_created.length > 0 &&
              ` · cohorts created: ${result.cohorts_created.join(", ")}`}
          </div>

          {Object.keys(result.temporary_passwords).length > 0 && (
            <>
              <div className="ds-card p-3 mb-3 text-xs" style={{ borderColor: "var(--rag-amber)" }}>
                These first passwords are shown <strong>once</strong>. They are not
                stored in a readable form and cannot be looked up again — copy them
                now. Everyone is made to change theirs at first sign-in.
              </div>
              <button
                onClick={() => navigator.clipboard.writeText(
                  Object.entries(result.temporary_passwords)
                    .map(([e, p]) => `${e},${p}`).join("\n"))}
                className="btn btn-ghost btn-sm mb-3 ds-focus">
                <Copy size={13} /> Copy all as CSV
              </button>
              <Table
                columns={["Email", "First password"]}
                rows={Object.entries(result.temporary_passwords).map(([email, pw]) => [
                  email, <code key="p" className="kbd">{pw}</code>,
                ])}
              />
            </>
          )}
        </Section>
      )}
    </>
  );
}

function Tile({ label, value, tone = "var(--text)" }: {
  label: string; value: string | number; tone?: string;
}) {
  return (
    <div className="ds-inset p-3">
      <div className="text-[10px] font-bold uppercase tracking-wide text-muted">{label}</div>
      <div className="text-xl font-bold mt-1" style={{ color: tone }}>{value}</div>
    </div>
  );
}

"use client";
import Link from "next/link";
import { useMemo, useState } from "react";
import { Check, Copy, FileText, Plus, X } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { Badge, ErrorNote, PageHeader, Section, Skeleton } from "@/components/ui";
import { ApiError, api, type InvitationRow } from "@/lib/api";
import { useData } from "@/lib/useData";

export default function TenantInvitationsPage() {
  return (
    <RequireAuth roles={["tenant_admin"]}>
      <Invitations />
    </RequireAuth>
  );
}

/**
 *  Inviting somebody who does not have an account here.
 *
 *  A campus student is imported, assigned and coached. An external candidate
 *  is a person an employer asked to take one test, once — so what they get is
 *  a link, not an account, and this screen is where it comes from.
 *
 *  The link is shown once, prominently, at the moment it is created. It stays
 *  visible in the list afterwards because an admin will be asked to re-send
 *  it: a candidate who lost the email needs the same link, not a new
 *  invitation and a burnt one.
 */
function Invitations() {
  const { data, loading, error, reload } = useData(() => api.tenantInvitations());
  const profiles = useData(() => api.tenantProfiles());
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState("");
  const [problem, setProblem] = useState("");
  const [copied, setCopied] = useState("");

  const publishable = useMemo(
    () => (profiles.data ?? []).filter((p) => p.status === "published"),
    [profiles.data]);

  const [draft, setDraft] = useState({
    profile_id: "", invited_name: "", invited_email: "", reference: "",
    valid_days: 7,
  });

  async function create() {
    setBusy("create");
    setProblem("");
    try {
      await api.createInvitation({ ...draft, valid_days: draft.valid_days });
      setCreating(false);
      setDraft({ profile_id: "", invited_name: "", invited_email: "",
                 reference: "", valid_days: 7 });
      reload();
    } catch (err) {
      setProblem(err instanceof ApiError ? err.detail : "That did not work");
    } finally {
      setBusy("");
    }
  }

  async function withdraw(id: string) {
    setBusy(id);
    setProblem("");
    try {
      await api.withdrawInvitation(id);
      reload();
    } catch (err) {
      setProblem(err instanceof ApiError ? err.detail : "That did not work");
    } finally {
      setBusy("");
    }
  }

  function linkFor(token: string) {
    if (typeof window === "undefined") return `/invite/${token}`;
    return `${window.location.origin}/invite/${token}`;
  }

  async function copy(token: string) {
    try {
      await navigator.clipboard.writeText(linkFor(token));
      setCopied(token);
      setTimeout(() => setCopied(""), 2000);
    } catch {
      // Clipboard access is refused in some browsers and contexts. The link
      // is on screen and selectable, so this is not worth an error.
    }
  }

  return (
    <>
      <PageHeader
        title="Invitations"
        sub="A link that lets one person outside your institution sit one assessment, once. They need no account and get none."
      />

      {problem && <div className="mb-4"><ErrorNote message={problem} /></div>}

      <div className="mb-4 flex items-center justify-between gap-3">
        <p className="text-[11px] text-muted leading-relaxed max-w-2xl">
          A link works once and expires. Opening it does not use it up — the
          candidate is only counted when they enter their name and start, so a
          link somebody previewed is still theirs to use.
        </p>
        <button className="btn btn-primary btn-sm ds-focus shrink-0"
                onClick={() => setCreating(true)}>
          <Plus size={14} /> New invitation
        </button>
      </div>

      {creating && (
        <Section title="Invite somebody" className="mb-4">
          <div className="grid md:grid-cols-2 gap-3">
            <Field label="Assessment"
                   hint="Published assessments only — nobody can be invited to a draft.">
              <select className="ds-input w-full" value={draft.profile_id}
                      onChange={(e) => setDraft({ ...draft, profile_id: e.target.value })}>
                <option value="">Choose…</option>
                {publishable.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} · about {p.estimated_minutes} min
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Valid for"
                   hint="A link that works forever is a credential nobody remembers issuing.">
              <select className="ds-input w-full" value={draft.valid_days}
                      onChange={(e) => setDraft({ ...draft, valid_days: Number(e.target.value) })}>
                {[1, 3, 7, 14, 30, 90].map((d) => (
                  <option key={d} value={d}>{d} day{d === 1 ? "" : "s"}</option>
                ))}
              </select>
            </Field>
            <Field label="Their name" hint="Shown on the invitation. They can correct it.">
              <input className="ds-input w-full" value={draft.invited_name}
                     onChange={(e) => setDraft({ ...draft, invited_name: e.target.value })}
                     placeholder="e.g. Asha Rao" />
            </Field>
            <Field label="Their email"
                   hint="For your own reference. We do not send the link — you do.">
              <input className="ds-input w-full" type="email" value={draft.invited_email}
                     onChange={(e) => setDraft({ ...draft, invited_email: e.target.value })}
                     placeholder="e.g. asha@example.com" />
            </Field>
            <Field label="Your reference" hint="A requisition number, a role — whatever you file by.">
              <input className="ds-input w-full" value={draft.reference}
                     onChange={(e) => setDraft({ ...draft, reference: e.target.value })}
                     placeholder="e.g. REQ-1042" />
            </Field>
          </div>
          <div className="flex gap-2 mt-3">
            <button className="btn btn-primary btn-sm ds-focus"
                    disabled={!draft.profile_id || busy === "create"}
                    onClick={() => void create()}>
              {busy === "create" ? "Creating…" : "Create the link"}
            </button>
            <button className="btn btn-ghost btn-sm ds-focus"
                    onClick={() => setCreating(false)}>
              Cancel
            </button>
          </div>
        </Section>
      )}

      {loading ? <Skeleton rows={4} /> : error ? <ErrorNote message={error} /> : (
        <div className="space-y-2">
          {(data ?? []).length === 0 && (
            <p className="text-xs text-muted">
              No invitations yet. Everybody sitting an assessment so far has an
              account here.
            </p>
          )}
          {(data ?? []).map((row) => (
            <Row key={row.id} row={row} link={linkFor(row.token)}
                 copied={copied === row.token} busy={busy === row.id}
                 onCopy={() => void copy(row.token)}
                 onWithdraw={() => void withdraw(row.id)} />
          ))}
        </div>
      )}
    </>
  );
}

function Row({ row, link, copied, busy, onCopy, onWithdraw }: {
  row: InvitationRow; link: string; copied: boolean; busy: boolean;
  onCopy: () => void; onWithdraw: () => void;
}) {
  const tone = row.status === "redeemed" ? "var(--rag-green)"
    : row.status === "withdrawn" ? "var(--muted)" : "var(--primary)";

  return (
    <div className="ds-card p-3">
      <div className="flex items-start gap-3 flex-wrap">
        <div className="flex-1 min-w-[14rem]">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-bold">
              {row.invited_name || "Someone"}
            </span>
            <Badge tone={tone}>{row.status}</Badge>
            {row.reference && (
              <span className="text-[11px] text-muted">{row.reference}</span>
            )}
          </div>
          <div className="text-[11px] text-muted mt-0.5">
            {row.profile_name}
            {row.invited_email && ` · ${row.invited_email}`}
            {row.expires_at && row.status === "pending"
              && ` · expires ${new Date(row.expires_at).toLocaleDateString()}`}
            {row.redeemed_at
              && ` · started ${new Date(row.redeemed_at).toLocaleDateString()}`}
          </div>
        </div>

        {row.status === "redeemed" && (
          // The point of the whole flow, and it had nowhere to go until now:
          // an employer could watch an invitation turn "redeemed" and never
          // see what the candidate scored.
          <Link href={`/tenant/invitations/${row.id}/result`}
                className="btn btn-ghost btn-sm ds-focus">
            <FileText size={13} /> View result
          </Link>
        )}

        {row.status === "pending" && (
          <div className="flex items-center gap-2">
            <button className="btn btn-ghost btn-sm ds-focus" onClick={onCopy}>
              {copied ? <><Check size={13} /> Copied</> : <><Copy size={13} /> Copy link</>}
            </button>
            <button className="btn btn-ghost btn-sm ds-focus" disabled={busy}
                    onClick={onWithdraw}
                    title="Cancel this link. Only possible before it is used.">
              <X size={13} /> Withdraw
            </button>
          </div>
        )}
      </div>

      {row.status === "pending" && (
        // On screen and selectable, so an admin can send it however they
        // send things. Nothing here emails anybody: a product that sent mail
        // on a customer's behalf would need their domain, their consent and
        // their deliverability problems.
        <div className="ds-inset p-2 mt-2 text-[11px] font-mono break-all">
          {link}
        </div>
      )}
    </div>
  );
}

function Field({ label, hint, children }: {
  label: string; hint?: string; children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="block text-[10px] font-bold uppercase tracking-wider text-muted mb-1">
        {label}
      </span>
      {children}
      {hint && <span className="block text-[10px] text-muted mt-1">{hint}</span>}
    </label>
  );
}

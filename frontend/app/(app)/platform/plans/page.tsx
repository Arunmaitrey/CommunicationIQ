"use client";
import { useState } from "react";
import { Copy, Plus } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { Badge, ErrorNote, PageHeader, Section, Skeleton } from "@/components/ui";
import { api, ApiError, operatorApi, type PlanRow } from "@/lib/api";
import { PLATFORM_ROLES } from "@/lib/roles";
import { useData } from "@/lib/useData";

export default function PlansPage() {
  return (
    <RequireAuth roles={PLATFORM_ROLES}>
      <Plans />
    </RequireAuth>
  );
}

// Must match BILLING_MODELS in the backend schema. An entry here that the
// validator rejects is a dropdown that fails on save.
const MODELS = [
  ["per_seat", "Per seat"],
  ["flat", "Institution flat"],
  ["usage", "Usage-based"],
  ["pilot", "Pilot / free"],
] as const;

const MODEL_LABEL: Record<string, string> = Object.fromEntries(MODELS);

const CURRENCIES = ["INR", "USD", "AED", "GBP"] as const;

const money = (n: number, currency: string) =>
  new Intl.NumberFormat("en-IN", {
    style: "currency", currency, maximumFractionDigits: 0,
  }).format(n);

type Draft = {
  code: string; name: string; billing_model: string; currency: string;
  price_per_seat: number; price_flat: number; attempt_allowance: number;
};

const blank = (): Draft => ({
  code: "", name: "", billing_model: "per_seat", currency: "INR",
  price_per_seat: 0, price_flat: 0, attempt_allowance: 3,
});

function Plans() {
  const { data, loading, error, reload } = useData(() => api.platformPlans());
  const tenants = useData(() => api.platformTenants());

  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState<Draft>(blank());
  const [versioning, setVersioning] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [busy, setBusy] = useState("");
  const [problem, setProblem] = useState("");
  const [note, setNote] = useState("");

  async function run(what: string, fn: () => Promise<unknown>, ok = "") {
    setBusy(what);
    setProblem("");
    setNote("");
    try {
      await fn();
      reload();
      if (ok) setNote(ok);
      return true;
    } catch (err) {
      setProblem(err instanceof ApiError ? err.detail : "That did not work");
      return false;
    } finally {
      setBusy("");
    }
  }

  const plans = data ?? [];
  const usage = new Map<string, number>();
  for (const t of tenants.data ?? []) {
    if (t.plan_id) usage.set(t.plan_id, (usage.get(t.plan_id) ?? 0) + 1);
  }

  return (
    <>
      <PageHeader
        title="Plan templates"
        sub="Versioned pricing templates. Assigning a plan to a tenant copies the terms onto their subscription, so changing a template never silently re-prices a live customer."
      />

      {problem && <div className="mb-4"><ErrorNote message={problem} /></div>}
      {note && (
        <div className="ds-card p-3 mb-4 text-xs" style={{ borderColor: "var(--rag-green)" }}>
          {note}
        </div>
      )}

      <div className="mb-4 flex items-center justify-between gap-3">
        <p className="text-[11px] text-muted leading-relaxed max-w-2xl">
          Price and billing model cannot be edited in place. A template whose
          price disagrees with what its customers are paying is worse than no
          template — to change a price, publish a new version and move tenants
          onto it when their term allows.
        </p>
        <button className="btn btn-primary btn-sm ds-focus shrink-0"
                onClick={() => { setCreating(true); setEditing(null); setVersioning(null); }}>
          <Plus size={14} /> New plan
        </button>
      </div>

      {creating && (
        <Section title="New plan">
          <PlanForm draft={draft} onChange={setDraft} withCode />
          <div className="flex gap-2 mt-3">
            <button className="btn btn-primary btn-sm ds-focus"
                    disabled={busy !== "" || !draft.code.trim() || !draft.name.trim()}
                    onClick={() => void run("create",
                      () => operatorApi.createPlan(draft), "Plan created.")
                      .then((ok) => { if (ok) { setCreating(false); setDraft(blank()); } })}>
              {busy === "create" ? "Creating…" : "Create plan"}
            </button>
            <button className="btn btn-ghost btn-sm ds-focus"
                    onClick={() => setCreating(false)}>Cancel</button>
          </div>
        </Section>
      )}

      {loading ? <Skeleton rows={3} /> : error ? <ErrorNote message={error} /> : (
        <div className="space-y-3">
          {plans.map((p) => (
            <PlanCard
              key={p.id}
              plan={p}
              tenantsOn={usage.get(p.id) ?? 0}
              busy={busy}
              editing={editing === p.id}
              versioning={versioning === p.id}
              onEdit={() => { setEditing(editing === p.id ? null : p.id); setVersioning(null); }}
              onVersion={() => { setVersioning(versioning === p.id ? null : p.id); setEditing(null); }}
              onRun={run}
              onDone={() => { setEditing(null); setVersioning(null); }}
            />
          ))}
        </div>
      )}
    </>
  );
}

function PlanCard({ plan, tenantsOn, busy, editing, versioning, onEdit, onVersion,
                   onRun, onDone }: {
  plan: PlanRow;
  tenantsOn: number;
  busy: string;
  editing: boolean;
  versioning: boolean;
  onEdit: () => void;
  onVersion: () => void;
  onRun: (what: string, fn: () => Promise<unknown>, ok?: string) => Promise<boolean>;
  onDone: () => void;
}) {
  const [form, setForm] = useState({
    name: plan.name,
    attempt_allowance: plan.attempt_allowance,
  });
  const [next, setNext] = useState<Draft>({
    code: plan.code, name: plan.name, billing_model: plan.billing_model,
    currency: plan.currency, price_per_seat: plan.price_per_seat,
    price_flat: plan.price_flat, attempt_allowance: plan.attempt_allowance,
  });

  return (
    <Section
      title={`${plan.name} · v${plan.version}`}
      action={
        <div className="flex items-center gap-2">
          <span className="text-[11px] text-muted">
            {MODEL_LABEL[plan.billing_model] ?? plan.billing_model}
          </span>
          {plan.active
            ? <Badge tone="var(--rag-green)">Active</Badge>
            : <Badge tone="var(--muted)">Retired</Badge>}
        </div>
      }
    >
      <div className="text-[11px] text-muted mb-3">
        <span className="font-mono">{plan.code}</span>
        {" · "}
        {plan.billing_model === "flat"
          ? money(plan.price_flat, plan.currency)
          : plan.billing_model === "pilot"
            ? "no charge"
            : `${money(plan.price_per_seat, plan.currency)} per seat`}
        {" · "}{plan.attempt_allowance} attempts per profile
        {" · "}
        <span style={{ color: tenantsOn ? "var(--text)" : undefined }}>
          {tenantsOn} tenant{tenantsOn === 1 ? "" : "s"} on this version
        </span>
      </div>

      <div className="flex flex-wrap gap-2">
        <button className="btn btn-ghost btn-sm ds-focus" disabled={busy !== ""}
                onClick={onEdit}>
          {editing ? "Close" : "Edit"}
        </button>
        <button className="btn btn-ghost btn-sm ds-focus" disabled={busy !== ""}
                onClick={onVersion}>
          <Copy size={13} /> {versioning ? "Close" : "New version"}
        </button>
        {plan.active ? (
          <button
            className="btn btn-ghost btn-sm ds-focus"
            disabled={busy !== "" || tenantsOn > 0}
            title={tenantsOn > 0
              ? `${tenantsOn} tenant(s) are on this plan — move them first`
              : ""}
            onClick={() => void onRun("retire",
              () => operatorApi.updatePlan(plan.id, { active: false }), "Plan retired.")}
          >
            Retire
          </button>
        ) : (
          <button className="btn btn-ghost btn-sm ds-focus" disabled={busy !== ""}
                  onClick={() => void onRun("activate",
                    () => operatorApi.updatePlan(plan.id, { active: true }),
                    "Plan reactivated.")}>
            Reactivate
          </button>
        )}
      </div>

      {editing && (
        <div className="ds-inset p-3 mt-3">
          <div className="text-[11px] font-bold mb-2">Edit this version</div>
          <div className="grid md:grid-cols-2 gap-3">
            <Field label="Name">
              <input className="ds-input w-full" value={form.name}
                     onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </Field>
            <Field label="Attempts per profile">
              <input className="ds-input w-full" type="number" min={0}
                     value={form.attempt_allowance}
                     onChange={(e) => setForm({
                       ...form, attempt_allowance: Number(e.target.value),
                     })} />
            </Field>
          </div>
          <p className="text-[10px] text-muted mt-2 leading-relaxed">
            Price and billing model are not editable here — they are copied onto
            live subscriptions. Use <strong>New version</strong> to change them.
          </p>
          <div className="flex gap-2 mt-2">
            <button className="btn btn-primary btn-sm ds-focus" disabled={busy !== ""}
                    onClick={() => void onRun("save",
                      () => operatorApi.updatePlan(plan.id, form), "Saved.")
                      .then((ok) => { if (ok) onDone(); })}>
              {busy === "save" ? "Saving…" : "Save"}
            </button>
          </div>
        </div>
      )}

      {versioning && (
        <div className="ds-inset p-3 mt-3">
          <div className="text-[11px] font-bold mb-2">
            New version of <span className="font-mono">{plan.code}</span>
          </div>
          <p className="text-[10px] text-muted mb-3 leading-relaxed">
            v{plan.version} stays exactly as it is, so anyone already on it keeps
            the terms they agreed to. New assignments pick up the new version.
          </p>
          <PlanForm draft={next} onChange={setNext} />
          <div className="flex gap-2 mt-3">
            <button className="btn btn-primary btn-sm ds-focus"
                    disabled={busy !== "" || !next.name.trim()}
                    onClick={() => void onRun("version",
                      () => operatorApi.newPlanVersion(plan.id, next),
                      `Published v${plan.version + 1}.`)
                      .then((ok) => { if (ok) onDone(); })}>
              {busy === "version" ? "Publishing…" : `Publish v${plan.version + 1}`}
            </button>
          </div>
        </div>
      )}
    </Section>
  );
}

function PlanForm({ draft, onChange, withCode = false }: {
  draft: Draft;
  onChange: (d: Draft) => void;
  withCode?: boolean;
}) {
  const set = (patch: Partial<Draft>) => onChange({ ...draft, ...patch });
  const perSeat = draft.billing_model === "per_seat" || draft.billing_model === "usage";
  const free = draft.billing_model === "pilot";

  return (
    <div className="grid md:grid-cols-3 gap-3">
      {withCode && (
        <Field label="Code" hint="Stable identifier. Versions share it.">
          <input className="ds-input w-full font-mono text-[12px]" value={draft.code}
                 onChange={(e) => set({
                   code: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_"),
                 })}
                 placeholder="campus_standard" />
        </Field>
      )}
      <Field label="Name">
        <input className="ds-input w-full" value={draft.name}
               onChange={(e) => set({ name: e.target.value })}
               placeholder="Campus Standard" />
      </Field>
      <Field label="Billing model">
        <select className="ds-input w-full" value={draft.billing_model}
                onChange={(e) => set({ billing_model: e.target.value })}>
          {MODELS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      </Field>
      <Field label="Currency">
        <select className="ds-input w-full" value={draft.currency}
                onChange={(e) => set({ currency: e.target.value })}>
          {CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      </Field>
      {!free && (
        <Field label={perSeat ? "Price per seat" : "Flat price"}>
          <input className="ds-input w-full" type="number" min={0}
                 value={perSeat ? draft.price_per_seat : draft.price_flat}
                 onChange={(e) => set(perSeat
                   ? { price_per_seat: Number(e.target.value) }
                   : { price_flat: Number(e.target.value) })} />
        </Field>
      )}
      <Field label="Attempts per profile"
             hint="How many times a student may take each simulation before it is re-purchased.">
        <input className="ds-input w-full" type="number" min={0}
               value={draft.attempt_allowance}
               onChange={(e) => set({ attempt_allowance: Number(e.target.value) })} />
      </Field>
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
      {hint && <span className="block text-[10px] text-muted mt-1 leading-relaxed">{hint}</span>}
    </label>
  );
}

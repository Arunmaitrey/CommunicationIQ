"use client";
import { useMemo, useRef, useState } from "react";
import {
  Building2, ChevronDown, ChevronRight, Download, Image as ImageIcon, Link2, Plus,
  Trash2, Upload,
} from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { PLATFORM_ROLES } from "@/lib/roles";
import { Badge, ErrorNote, PageHeader, Section, Skeleton } from "@/components/ui";
import {
  api, ApiError, assetUrl, operatorApi, EMPTY_TENANT_PROFILE,
  type PlanRow, type TenantProfile, type TenantRow,
} from "@/lib/api";
import { useData } from "@/lib/useData";

export default function PlatformTenantsPage() {
  return (
    <RequireAuth roles={PLATFORM_ROLES}>
      <Tenants />
    </RequireAuth>
  );
}

const STATUSES = ["trial", "active", "suspended", "offboarding", "closed"] as const;

const STATUS_TONE: Record<string, string> = {
  active: "var(--rag-green)",
  trial: "var(--accent)",
  suspended: "var(--rag-amber)",
  offboarding: "var(--rag-red)",
  closed: "var(--muted)",
};

type Draft = {
  name: string; slug: string; tenant_type: string; status: string;
  seat_limit: number; plan_id: string; region: string;
  admin_email: string; admin_name: string;
};

function newDraft(defaultType: string): Draft {
  return {
    name: "", slug: "", tenant_type: defaultType, status: "trial",
    seat_limit: 100, plan_id: "", region: "", admin_email: "", admin_name: "",
  };
}

/** A slug becomes a schema name and part of every recording key, so it is
 *  generated conservatively and never changed afterwards. */
function slugify(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "").replace(/^([0-9])/, "t$1").slice(0, 40);
}

/** The optional half of a tenant record.
 *
 *  Shared by the create form and the manage panel so the two cannot drift --
 *  a field added here appears in both, which is not true of two copies.
 *
 *  Everything is optional by design. A tenant needs a name and an admin to
 *  exist; the address, the contacts and the course list arrive later, in
 *  whatever order sales actually learns them. Making any of it required at
 *  creation would mean inventing placeholder data to get past the form.
 */
function ProfileFields({ value, onChange }: {
  value: TenantProfile;
  onChange: (p: TenantProfile) => void;
}) {
  const set = (patch: Partial<TenantProfile>) => onChange({ ...value, ...patch });

  return (
    <div className="space-y-4">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-wider text-muted mb-2">
          Address
        </div>
        <div className="grid md:grid-cols-3 gap-3">
          <div className="md:col-span-2">
            <Field label="Street">
              <input className="ds-input w-full" value={value.address_line1}
                     onChange={(e) => set({ address_line1: e.target.value })} />
            </Field>
          </div>
          <Field label="Area / landmark">
            <input className="ds-input w-full" value={value.address_line2}
                   onChange={(e) => set({ address_line2: e.target.value })} />
          </Field>
          <Field label="City">
            <input className="ds-input w-full" value={value.city}
                   onChange={(e) => set({ city: e.target.value })} />
          </Field>
          <Field label="State">
            <input className="ds-input w-full" value={value.state}
                   onChange={(e) => set({ state: e.target.value })} />
          </Field>
          <Field label="PIN code">
            <input className="ds-input w-full" value={value.postal_code}
                   onChange={(e) => set({ postal_code: e.target.value })} />
          </Field>
          <Field label="Country">
            <input className="ds-input w-full" value={value.country}
                   onChange={(e) => set({ country: e.target.value })} />
          </Field>
        </div>
      </div>

      <div>
        <div className="text-[10px] font-bold uppercase tracking-wider text-muted mb-2">
          Reaching them
        </div>
        <div className="grid md:grid-cols-3 gap-3">
          <Field label="Website">
            <input className="ds-input w-full" value={value.website}
                   onChange={(e) => set({ website: e.target.value })}
                   placeholder="https://college.edu" />
          </Field>
          <Field label="Switchboard">
            <input className="ds-input w-full" value={value.phone}
                   onChange={(e) => set({ phone: e.target.value })} />
          </Field>
          <Field label="Billing email" hint="Where invoices go, if not the admin.">
            <input className="ds-input w-full" type="email" value={value.billing_email}
                   onChange={(e) => set({ billing_email: e.target.value })} />
          </Field>
        </div>

        <div className="mt-3">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[10px] font-bold uppercase tracking-wider text-muted">
              People
            </span>
            <button type="button" className="btn btn-ghost btn-sm ds-focus"
                    onClick={() => set({
                      contacts: [...value.contacts,
                                 { role: "", name: "", email: "", phone: "" }],
                    })}>
              <Plus size={12} /> Add contact
            </button>
          </div>
          {value.contacts.length === 0 ? (
            <p className="text-[10px] text-muted">
              None yet. The first admin account is created separately.
            </p>
          ) : (
            <div className="space-y-2">
              {value.contacts.map((c, i) => (
                <div key={i} className="grid md:grid-cols-[1fr_1fr_1.3fr_1fr_auto] gap-2 items-end">
                  <Field label="Role">
                    <input className="ds-input w-full" value={c.role}
                           placeholder="Placement officer"
                           onChange={(e) => set({
                             contacts: value.contacts.map((x, n) =>
                               n === i ? { ...x, role: e.target.value } : x),
                           })} />
                  </Field>
                  <Field label="Name">
                    <input className="ds-input w-full" value={c.name}
                           onChange={(e) => set({
                             contacts: value.contacts.map((x, n) =>
                               n === i ? { ...x, name: e.target.value } : x),
                           })} />
                  </Field>
                  <Field label="Email">
                    <input className="ds-input w-full" type="email" value={c.email}
                           onChange={(e) => set({
                             contacts: value.contacts.map((x, n) =>
                               n === i ? { ...x, email: e.target.value } : x),
                           })} />
                  </Field>
                  <Field label="Phone">
                    <input className="ds-input w-full" value={c.phone}
                           onChange={(e) => set({
                             contacts: value.contacts.map((x, n) =>
                               n === i ? { ...x, phone: e.target.value } : x),
                           })} />
                  </Field>
                  <button type="button" className="btn btn-ghost btn-sm ds-focus mb-0.5"
                          onClick={() => set({
                            contacts: value.contacts.filter((_, n) => n !== i),
                          })}>
                    <Trash2 size={12} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div>
        <div className="text-[10px] font-bold uppercase tracking-wider text-muted mb-2">
          The institution
        </div>
        <div className="grid md:grid-cols-4 gap-3">
          <div className="md:col-span-2">
            <Field label="Affiliated to">
              <input className="ds-input w-full" value={value.affiliated_to}
                     onChange={(e) => set({ affiliated_to: e.target.value })}
                     placeholder="JNTU Kakinada" />
            </Field>
          </div>
          <Field label="Established">
            <input className="ds-input w-full" type="number"
                   value={value.established_year ?? ""}
                   onChange={(e) => set({
                     established_year: e.target.value ? Number(e.target.value) : null,
                   })} />
          </Field>
          <Field label="Students">
            <input className="ds-input w-full" type="number"
                   value={value.student_strength ?? ""}
                   onChange={(e) => set({
                     student_strength: e.target.value ? Number(e.target.value) : null,
                   })} />
          </Field>
          <Field label="Accreditation">
            <input className="ds-input w-full" value={value.accreditation}
                   onChange={(e) => set({ accreditation: e.target.value })}
                   placeholder="NAAC A+" />
          </Field>
          <Field label="GST number">
            <input className="ds-input w-full" value={value.gst_number}
                   onChange={(e) => set({ gst_number: e.target.value })} />
          </Field>
          <div className="md:col-span-2">
            <Field label="Courses / streams"
                   hint="Comma separated. Free text on purpose — every institution names these differently.">
              <input
                className="ds-input w-full"
                value={value.courses.join(", ")}
                onChange={(e) => set({
                  courses: e.target.value.split(",").map((x) => x.trim()).filter(Boolean),
                })}
                placeholder="CSE, ECE, Mechanical, MBA"
              />
            </Field>
          </div>
        </div>
        <div className="mt-3">
          <Field label="Notes">
            <textarea className="ds-input w-full" rows={2} value={value.notes}
                      onChange={(e) => set({ notes: e.target.value })}
                      placeholder="Anything worth knowing before a call." />
          </Field>
        </div>
      </div>
    </div>
  );
}

function Tenants() {
  const tenants = useData(() => api.platformTenants());
  const plans = useData(() => api.platformPlans());
  const types = useData(() => api.tenantTypes());

  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState<Draft>(newDraft("engineering_college"));
  // Collapsed by default. The required half fits on one screen; opening the
  // rest is a choice, not a wall to get past.
  const [showMore, setShowMore] = useState(false);
  const [newProfile, setNewProfile] = useState<TenantProfile>({ ...EMPTY_TENANT_PROFILE });
  const [editing, setEditing] = useState<string | null>(null);
  const [busy, setBusy] = useState("");
  const [problem, setProblem] = useState("");
  const [note, setNote] = useState("");

  const planList = useMemo(() => plans.data ?? [], [plans.data]);
  const typeList = useMemo(() => types.data ?? [], [types.data]);

  async function run(what: string, fn: () => Promise<unknown>, ok = "") {
    setBusy(what);
    setProblem("");
    setNote("");
    try {
      await fn();
      tenants.reload();
      if (ok) setNote(ok);
    } catch (err) {
      setProblem(err instanceof ApiError ? err.detail : "That did not work");
    } finally {
      setBusy("");
    }
  }

  async function create() {
    const body = {
      ...draft,
      slug: draft.slug || slugify(draft.name),
      plan_id: draft.plan_id || null,
      region: draft.region || undefined,
      profile: newProfile,
    };
    await run("create", () => operatorApi.createTenant(body),
              "Tenant created. Its admin must set a password on first sign-in.");
    setCreating(false);
    setShowMore(false);
    setDraft(newDraft(typeList[0]?.key ?? "engineering_college"));
    setNewProfile({ ...EMPTY_TENANT_PROFILE });
  }

  return (
    <>
      <PageHeader
        title="Tenants"
        sub="Every customer on the platform — colleges, schools, corporates and partners. Each one gets its own database schema; nothing here can read inside them."
      />

      {problem && <div className="mb-4"><ErrorNote message={problem} /></div>}
      {note && (
        <div className="ds-card p-3 mb-4 text-xs" style={{ borderColor: "var(--rag-green)" }}>
          {note}
        </div>
      )}

      <div className="mb-4 flex items-center justify-between gap-3">
        <p className="text-[11px] text-muted leading-relaxed max-w-2xl">
          A tenant&rsquo;s slug is fixed at creation: it names the database schema and
          is embedded in every stored recording key, so renaming it would strand
          both. Everything else can change.
        </p>
        <button className="btn btn-primary btn-sm ds-focus shrink-0"
                onClick={() => { setCreating(true); setEditing(null); }}>
          <Plus size={14} /> New tenant
        </button>
      </div>

      {creating && (
        <Section title="New tenant">
          <div className="grid md:grid-cols-2 gap-3">
            <Field label="Name">
              <input className="ds-input w-full" value={draft.name}
                     onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                     placeholder="e.g. Gayatri Institute of Technology" />
            </Field>
            <Field label="Slug" hint="Fixed once created. Left blank, it is derived from the name.">
              <input className="ds-input w-full" value={draft.slug}
                     onChange={(e) => setDraft({ ...draft, slug: slugify(e.target.value) })}
                     placeholder={draft.name ? slugify(draft.name) : "gayatri_tech"} />
            </Field>
            <Field label="Tenant type">
              <select className="ds-input w-full" value={draft.tenant_type}
                      onChange={(e) => setDraft({ ...draft, tenant_type: e.target.value })}>
                {typeList.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
              </select>
            </Field>
            <Field label="Status">
              <select className="ds-input w-full" value={draft.status}
                      onChange={(e) => setDraft({ ...draft, status: e.target.value })}>
                {STATUSES.map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </Field>
            <Field label="Plan">
              <select className="ds-input w-full" value={draft.plan_id}
                      onChange={(e) => setDraft({ ...draft, plan_id: e.target.value })}>
                <option value="">No plan yet</option>
                {planList.filter((p) => p.active).map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            </Field>
            <Field label="Seat limit">
              <input className="ds-input w-full" type="number" min={1}
                     value={draft.seat_limit}
                     onChange={(e) => setDraft({ ...draft, seat_limit: Number(e.target.value) })} />
            </Field>
            <Field label="First admin — name">
              <input className="ds-input w-full" value={draft.admin_name}
                     onChange={(e) => setDraft({ ...draft, admin_name: e.target.value })} />
            </Field>
            <Field label="First admin — email"
                   hint="They receive a temporary password and must change it.">
              <input className="ds-input w-full" type="email" value={draft.admin_email}
                     onChange={(e) => setDraft({ ...draft, admin_email: e.target.value })} />
            </Field>
          </div>
          <div className="mt-3 pt-3" style={{ borderTop: "1px solid var(--border)" }}>
            <button type="button"
                    className="btn btn-ghost btn-sm ds-focus"
                    onClick={() => setShowMore(!showMore)}>
              {showMore ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
              Address, contacts, courses — all optional
            </button>
            {showMore && (
              <div className="mt-3">
                <ProfileFields value={newProfile} onChange={setNewProfile} />
              </div>
            )}
          </div>

          <div className="flex gap-2 mt-3">
            <button className="btn btn-primary btn-sm ds-focus"
                    disabled={busy !== "" || !draft.name.trim() || !draft.admin_email.trim()
                              || !draft.admin_name.trim()}
                    onClick={() => void create()}>
              {busy === "create" ? "Creating…" : "Create tenant"}
            </button>
            <button className="btn btn-ghost btn-sm ds-focus"
                    onClick={() => setCreating(false)}>Cancel</button>
          </div>
        </Section>
      )}

      {tenants.loading ? <Skeleton rows={4} />
        : tenants.error ? <ErrorNote message={tenants.error} />
        : (
          <div className="space-y-3">
            {(tenants.data ?? []).map((t) => (
              <TenantCard
                key={t.id}
                tenant={t}
                plans={planList}
                types={typeList}
                open={editing === t.id}
                busy={busy}
                onToggle={() => { setEditing(editing === t.id ? null : t.id); setCreating(false); }}
                onRun={run}
              />
            ))}
          </div>
        )}
    </>
  );
}

function TenantCard({ tenant, plans, types, open, busy, onToggle, onRun }: {
  tenant: TenantRow;
  plans: PlanRow[];
  types: { key: string; label: string }[];
  open: boolean;
  busy: string;
  onToggle: () => void;
  onRun: (what: string, fn: () => Promise<unknown>, ok?: string) => Promise<void>;
}) {
  const [form, setForm] = useState({
    name: tenant.name,
    tenant_type: tenant.tenant_type,
    status: tenant.status,
    seat_limit: tenant.seat_limit,
    plan_id: tenant.plan_id ?? "",
    region: tenant.region,
    display_name: tenant.branding.display_name,
    primary_color: tenant.branding.primary_color,
    support_email: tenant.branding.support_email,
  });
  const [logoUrl, setLogoUrl] = useState("");
  const [profile, setProfile] = useState<TenantProfile>(tenant.profile);
  const [showDetails, setShowDetails] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const overSeats = tenant.seats_used > tenant.seat_limit;

  return (
    <Section
      title={tenant.name}
      action={
        <div className="flex items-center gap-2">
          <span className="text-[11px] text-muted">{tenant.tenant_type_label}</span>
          <Badge tone={STATUS_TONE[tenant.status] ?? "var(--muted)"}>{tenant.status}</Badge>
          <button className="btn btn-ghost btn-sm ds-focus" onClick={onToggle}>
            {open ? "Close" : "Manage"}
          </button>
        </div>
      }
    >
      <div className="flex items-center gap-3 mb-2">
        {tenant.branding.logo_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={assetUrl(tenant.branding.logo_url)} alt=""
               className="h-8 w-8 rounded object-contain shrink-0"
               style={{ background: "var(--surface)" }} />
        ) : (
          <span className="h-8 w-8 rounded flex items-center justify-center shrink-0"
                style={{ background: "var(--surface)", color: "var(--muted)" }}>
            <Building2 size={14} />
          </span>
        )}
        <div className="text-[11px] text-muted">
          <span className="font-mono">{tenant.slug}</span> · {tenant.region}
          {" · "}
          <span style={{ color: overSeats ? "var(--rag-red)" : undefined }}>
            {tenant.seats_used}/{tenant.seat_limit} seats
          </span>
          {tenant.plan_name && <> · {tenant.plan_name}</>}
          {tenant.subscription_status && <> · {tenant.subscription_status}</>}
        </div>
      </div>

      {open && (
        <div className="pt-3 space-y-4" style={{ borderTop: "1px solid var(--border)" }}>
          <div>
            <div className="text-[10px] font-bold uppercase tracking-wider text-muted mb-2">
              Details
            </div>
            <div className="grid md:grid-cols-3 gap-3">
              <Field label="Name">
                <input className="ds-input w-full" value={form.name}
                       onChange={(e) => setForm({ ...form, name: e.target.value })} />
              </Field>
              <Field label="Tenant type">
                <select className="ds-input w-full" value={form.tenant_type}
                        onChange={(e) => setForm({ ...form, tenant_type: e.target.value })}>
                  {types.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
                </select>
              </Field>
              <Field label="Region">
                <input className="ds-input w-full" value={form.region}
                       onChange={(e) => setForm({ ...form, region: e.target.value })} />
              </Field>
              <Field label="Status">
                <select className="ds-input w-full" value={form.status}
                        onChange={(e) => setForm({ ...form, status: e.target.value })}>
                  {STATUSES.map((v) => <option key={v} value={v}>{v}</option>)}
                </select>
              </Field>
              <Field label="Seat limit"
                     hint={`${tenant.seats_used} active accounts — it cannot go below that.`}>
                <input className="ds-input w-full" type="number" min={1}
                       value={form.seat_limit}
                       onChange={(e) => setForm({ ...form, seat_limit: Number(e.target.value) })} />
              </Field>
              <Field label="Plan">
                <select className="ds-input w-full" value={form.plan_id}
                        onChange={(e) => setForm({ ...form, plan_id: e.target.value })}>
                  <option value="">No plan</option>
                  {plans.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} · {p.currency} {p.billing_model === "flat"
                        ? p.price_flat : `${p.price_per_seat}/seat`}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
          </div>

          <div>
            <div className="text-[10px] font-bold uppercase tracking-wider text-muted mb-2">
              Branding
            </div>
            <div className="grid md:grid-cols-3 gap-3">
              <Field label="Display name"
                     hint="Shown to their people instead of the legal name.">
                <input className="ds-input w-full" value={form.display_name}
                       onChange={(e) => setForm({ ...form, display_name: e.target.value })}
                       placeholder={tenant.name} />
              </Field>
              <Field label="Primary colour" hint="Hex, e.g. #1E64C8.">
                <input className="ds-input w-full" value={form.primary_color}
                       onChange={(e) => setForm({ ...form, primary_color: e.target.value })}
                       placeholder="#1E64C8" />
              </Field>
              <Field label="Support email">
                <input className="ds-input w-full" type="email" value={form.support_email}
                       onChange={(e) => setForm({ ...form, support_email: e.target.value })} />
              </Field>
            </div>

            <div className="ds-inset p-3 mt-3">
              <div className="flex items-center gap-1.5 mb-2">
                <ImageIcon size={12} className="text-muted" />
                <span className="text-[11px] font-bold">Logo</span>
              </div>
              <div className="grid md:grid-cols-2 gap-3">
                <div>
                  <input ref={fileRef} type="file" className="hidden"
                         accept="image/png,image/jpeg,image/webp,image/gif"
                         onChange={(e) => {
                           const file = e.target.files?.[0];
                           if (file) {
                             void onRun("logo",
                               () => operatorApi.uploadTenantLogo(tenant.id, file),
                               "Logo uploaded.");
                           }
                           e.target.value = "";
                         }} />
                  <button className="btn btn-ghost btn-sm w-full ds-focus"
                          disabled={busy !== ""}
                          onClick={() => fileRef.current?.click()}>
                    <Upload size={13} /> Upload from this computer
                  </button>
                  <p className="text-[10px] text-muted mt-1 leading-relaxed">
                    PNG, JPEG, WebP or GIF, up to 2 MB. SVG is not accepted — it
                    can carry script, and this is served from our own origin.
                  </p>
                </div>
                <div>
                  <div className="flex gap-2">
                    <input className="ds-input flex-1" value={logoUrl}
                           onChange={(e) => setLogoUrl(e.target.value)}
                           placeholder="https://college.edu/logo.png" />
                    <button className="btn btn-ghost btn-sm ds-focus shrink-0"
                            disabled={busy !== "" || !logoUrl.trim()}
                            onClick={() => void onRun("logo",
                              () => operatorApi.setTenantLogoUrl(tenant.id, logoUrl.trim()),
                              "Logo linked.").then(() => setLogoUrl(""))}>
                      <Link2 size={13} /> Use URL
                    </button>
                  </div>
                  <p className="text-[10px] text-muted mt-1 leading-relaxed">
                    Must be https. The image is referenced, never copied — it
                    keeps loading from wherever they host it.
                  </p>
                </div>
              </div>
            </div>
          </div>

          <div className="pt-3" style={{ borderTop: "1px solid var(--border)" }}>
            <button type="button" className="btn btn-ghost btn-sm ds-focus"
                    onClick={() => setShowDetails(!showDetails)}>
              {showDetails ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
              Address, contacts and courses
            </button>
            {showDetails && <div className="mt-3"><ProfileFields value={profile} onChange={setProfile} /></div>}
          </div>

          <div className="flex gap-2">
            <button className="btn btn-primary btn-sm ds-focus" disabled={busy !== ""}
                    onClick={() => void onRun("save", () => operatorApi.updateTenant(tenant.id, {
                      name: form.name,
                      tenant_type: form.tenant_type,
                      status: form.status,
                      seat_limit: form.seat_limit,
                      plan_id: form.plan_id || null,
                      region: form.region,
                      branding: {
                        display_name: form.display_name,
                        logo_url: "",
                        primary_color: form.primary_color,
                        default_theme: tenant.branding.default_theme,
                        support_email: form.support_email,
                      },
                      profile,
                    }), "Saved.")}>
              {busy === "save" ? "Saving…" : "Save changes"}
            </button>
            <button className="btn btn-ghost btn-sm ds-focus" disabled={busy !== ""}
                    onClick={() => void onRun("invoice",
                      () => operatorApi.issueInvoice(tenant.id), "Invoice issued.")}>
              Issue invoice
            </button>
            {/* super_admin only — the server enforces it; other platform
                roles see the 403's own words instead of a hidden button
                they would not know exists. Audit-logged server-side. */}
            <button className="btn btn-ghost btn-sm ds-focus" disabled={busy !== ""}
                    onClick={() => void onRun("export", async () => {
                      const blob = await operatorApi.exportTenantReports(tenant.id);
                      const url = URL.createObjectURL(blob);
                      const a = document.createElement("a");
                      a.href = url;
                      a.download = `reports-${tenant.slug}.zip`;
                      a.click();
                      URL.revokeObjectURL(url);
                    }, "Student reports downloaded — this export is audit-logged.")}>
              <Download size={13} /> {busy === "export" ? "Exporting…" : "Download student reports"}
            </button>
          </div>
        </div>
      )}
    </Section>
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

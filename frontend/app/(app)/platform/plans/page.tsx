"use client";
import { useState } from "react";
import { Package, Plus, Trash2, Edit, Check, X } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { Badge, EmptyState, ErrorNote, PageHeader, Section, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { PLATFORM_ROLES } from "@/lib/roles";
import { useData } from "@/lib/useData";
import { useToast } from "@/components/Toast";

const ALL_FEATURES = ["reading", "writing", "listening", "speaking", "quiz"];

export default function PlansPage() {
  return (
    <RequireAuth roles={PLATFORM_ROLES}>
      <Plans />
    </RequireAuth>
  );
}

function Plans() {
  const { toast } = useToast();
  const { data, loading, error, reload } = useData(() => api.platformPlans());
  const [editing, setEditing] = useState<any | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({
    name: "", slug: "", description: "", price_monthly: 0, price_yearly: 0,
    seat_limit: 50, features: [...ALL_FEATURES], max_questions: 500,
    max_exams_per_day: 10, has_proctoring: true, has_analytics: true,
    has_custom_branding: false, has_api_access: false, is_active: true, is_default: false,
  });

  const plans = data ?? [];

  const startEdit = (plan: any) => {
    setEditing(plan);
    setForm({ ...plan });
    setCreating(false);
  };

  const startCreate = () => {
    setEditing(null);
    setCreating(true);
    setForm({
      name: "", slug: "", description: "", price_monthly: 0, price_yearly: 0,
      seat_limit: 50, features: [...ALL_FEATURES], max_questions: 500,
      max_exams_per_day: 10, has_proctoring: true, has_analytics: true,
      has_custom_branding: false, has_api_access: false, is_active: true, is_default: false,
    });
  };

  const save = async () => {
    try {
      if (editing) {
        await api.updatePlan(editing.id, form);
        toast("success", "Plan updated");
      } else {
        await api.createPlan(form);
        toast("success", "Plan created");
      }
      setEditing(null);
      setCreating(false);
      reload();
    } catch (e: any) {
      toast("error", e.message || "Failed");
    }
  };

  const remove = async (id: string) => {
    if (!confirm("Delete this plan?")) return;
    try {
      await api.deletePlan(id);
      toast("success", "Plan deleted");
      reload();
    } catch (e: any) {
      toast("error", e.message || "Failed");
    }
  };

  const toggleFeature = (f: string) => {
    setForm((prev) => ({
      ...prev,
      features: prev.features.includes(f) ? prev.features.filter((x) => x !== f) : [...prev.features, f],
    }));
  };

  return (
    <>
      <PageHeader
        title="Subscription Plans"
        sub="Manage plans that control feature access and limits for institutions."
        action={
          <button onClick={startCreate} className="btn btn-primary btn-sm flex items-center gap-1">
            <Plus size={14} /> New Plan
          </button>
        }
      />

      {loading ? <Skeleton rows={4} /> : error ? <ErrorNote message={error} /> : (
        <>
          {plans.length === 0 && !creating && (
            <EmptyState title="No plans yet" desc="Create a plan to get started." />
          )}

          {(creating || editing) && (
            <Section title={editing ? "Edit Plan" : "New Plan"} className="mb-4">
              <div className="grid grid-cols-2 gap-3">
                <label className="block">
                  <span className="text-[10px] font-bold uppercase text-muted">Name</span>
                  <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                    className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }} />
                </label>
                <label className="block">
                  <span className="text-[10px] font-bold uppercase text-muted">Slug</span>
                  <input value={form.slug} onChange={(e) => setForm({ ...form, slug: e.target.value })}
                    className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }} />
                </label>
                <label className="block col-span-2">
                  <span className="text-[10px] font-bold uppercase text-muted">Description</span>
                  <input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })}
                    className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }} />
                </label>
                <label className="block">
                  <span className="text-[10px] font-bold uppercase text-muted">Price/month (INR)</span>
                  <input type="number" value={form.price_monthly} onChange={(e) => setForm({ ...form, price_monthly: Number(e.target.value) })}
                    className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }} />
                </label>
                <label className="block">
                  <span className="text-[10px] font-bold uppercase text-muted">Price/year (INR)</span>
                  <input type="number" value={form.price_yearly} onChange={(e) => setForm({ ...form, price_yearly: Number(e.target.value) })}
                    className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }} />
                </label>
                <label className="block">
                  <span className="text-[10px] font-bold uppercase text-muted">Seat Limit</span>
                  <input type="number" value={form.seat_limit} onChange={(e) => setForm({ ...form, seat_limit: Number(e.target.value) })}
                    className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }} />
                </label>
                <label className="block">
                  <span className="text-[10px] font-bold uppercase text-muted">Max Questions</span>
                  <input type="number" value={form.max_questions} onChange={(e) => setForm({ ...form, max_questions: Number(e.target.value) })}
                    className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }} />
                </label>
                <label className="block">
                  <span className="text-[10px] font-bold uppercase text-muted">Max Exams/Day</span>
                  <input type="number" value={form.max_exams_per_day} onChange={(e) => setForm({ ...form, max_exams_per_day: Number(e.target.value) })}
                    className="w-full text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }} />
                </label>
              </div>
              <div className="mt-3">
                <span className="text-[10px] font-bold uppercase text-muted">Features</span>
                <div className="flex flex-wrap gap-2 mt-1">
                  {ALL_FEATURES.map((f) => (
                    <button key={f} onClick={() => toggleFeature(f)}
                      className={`text-[10px] px-2 py-1 rounded border ${form.features.includes(f) ? "font-bold" : ""}`}
                      style={{
                        borderColor: form.features.includes(f) ? "var(--primary)" : "var(--border)",
                        background: form.features.includes(f) ? "color-mix(in srgb, var(--primary) 10%, transparent)" : "transparent",
                      }}>
                      {form.features.includes(f) ? "✓" : ""} {f}
                    </button>
                  ))}
                </div>
              </div>
              <div className="flex flex-wrap gap-3 mt-3">
                {[
                  { key: "has_proctoring", label: "Proctoring" },
                  { key: "has_analytics", label: "Analytics" },
                  { key: "has_custom_branding", label: "Custom Branding" },
                  { key: "has_api_access", label: "API Access" },
                  { key: "is_active", label: "Active" },
                  { key: "is_default", label: "Default (Free)" },
                ].map(({ key, label }) => (
                  <label key={key} className="flex items-center gap-1.5 text-xs cursor-pointer">
                    <input type="checkbox" checked={(form as any)[key]}
                      onChange={(e) => setForm({ ...form, [key]: e.target.checked })} />
                    {label}
                  </label>
                ))}
              </div>
              <div className="flex gap-2 mt-4">
                <button onClick={save} className="px-3 py-1.5 text-xs rounded text-white" style={{ background: "var(--brand-grad)" }}>
                  {editing ? "Update" : "Create"}
                </button>
                <button onClick={() => { setEditing(null); setCreating(false); }} className="px-3 py-1.5 text-xs rounded bg-surface2 text-muted">
                  Cancel
                </button>
              </div>
            </Section>
          )}

          <div className="space-y-3">
            {plans.map((plan: any) => (
              <div key={plan.id} className="ds-card p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <Package size={14} style={{ color: "var(--primary)" }} />
                      <span className="text-sm font-bold">{plan.name}</span>
                      <Badge tone={plan.is_active ? "var(--rag-green)" : "var(--muted)"}>{plan.is_active ? "Active" : "Inactive"}</Badge>
                      {plan.is_default && <Badge tone="var(--primary)">Default</Badge>}
                    </div>
                    <p className="text-[11px] text-muted mb-3">{plan.description}</p>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-3">
                      {[
                        { label: "Monthly", value: `₹${plan.price_monthly}` },
                        { label: "Yearly", value: `₹${plan.price_yearly}` },
                        { label: "Seats", value: plan.seat_limit },
                        { label: "Exams / day", value: plan.max_exams_per_day },
                      ].map(({ label, value }) => (
                        <div key={label} className="rounded p-2" style={{ background: "var(--surface)" }}>
                          <div className="text-[9px] font-bold uppercase tracking-wider text-muted">{label}</div>
                          <div className="text-xs font-bold mt-0.5">{value}</div>
                        </div>
                      ))}
                    </div>
                    <div className="text-[10px] font-bold uppercase tracking-wider text-muted mb-1.5">Included</div>
                    <ul className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-1.5">
                      {plan.features?.map((f: string) => (
                        <li key={f} className="flex items-center gap-1.5 text-[11px]">
                          <Check size={11} style={{ color: "var(--rag-green)" }} className="shrink-0" />
                          <span className="capitalize">{f}</span>
                        </li>
                      ))}
                      {[
                        { k: "has_proctoring", label: "Proctoring" },
                        { k: "has_analytics", label: "Analytics" },
                        { k: "has_custom_branding", label: "Custom branding" },
                        { k: "has_api_access", label: "API access" },
                      ].map(({ k, label }) => (
                        plan[k] && (
                          <li key={k} className="flex items-center gap-1.5 text-[11px]">
                            <Check size={11} style={{ color: "var(--rag-green)" }} className="shrink-0" />
                            <span>{label}</span>
                          </li>
                        )
                      ))}
                      <li className="flex items-center gap-1.5 text-[11px]">
                        <Check size={11} style={{ color: "var(--rag-green)" }} className="shrink-0" />
                        <span>{plan.max_questions} questions</span>
                      </li>
                    </ul>
                  </div>
                  <div className="flex gap-1 shrink-0">
                    <button onClick={() => startEdit(plan)} className="p-1.5 rounded hover:bg-surface2"><Edit size={12} /></button>
                    <button onClick={() => remove(plan.id)} className="p-1.5 rounded hover:bg-surface2 text-ragRed"><Trash2 size={12} /></button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </>
  );
}
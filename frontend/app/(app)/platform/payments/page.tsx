"use client";
import { useState, useEffect } from "react";
import { CreditCard, Save, Loader2 } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { Badge, PageHeader, Section } from "@/components/ui";
import { api } from "@/lib/api";
import { PLATFORM_ROLES } from "@/lib/roles";
import { useToast } from "@/components/Toast";

export default function PaymentsPage() {
  return (
    <RequireAuth roles={PLATFORM_ROLES}>
      <PaymentSettings />
    </RequireAuth>
  );
}

function PaymentSettings() {
  const { toast } = useToast();
  const [saving, setSaving] = useState(false);
  const [gateway, setGateway] = useState("stripe");
  const [form, setForm] = useState({
    test_mode: true,
    stripe_publishable: "", stripe_secret: "", stripe_webhook_secret: "",
    razorpay_key_id: "", razorpay_key_secret: "",
    currency: "INR", is_active: false,
  });

  useEffect(() => {
    (async () => {
      try {
        const data = await api.platformPayment(gateway);
        if (data) setForm((prev) => ({ ...prev, ...data, stripe_secret: "", stripe_webhook_secret: "", razorpay_key_secret: "" }));
      } catch {}
    })();
  }, [gateway]);

  const save = async () => {
    setSaving(true);
    try {
      await api.savePayment({ ...form, gateway });
      toast("success", "Payment settings saved");
    } catch (e) {
      toast("error", (e instanceof Error ? e.message : String(e)) || "Failed");
    }
    setSaving(false);
  };

  return (
    <>
      <PageHeader title="Payment Gateway" sub="Configure Stripe or Razorpay for subscription billing." />

      <Section className="mb-4">
        <div className="flex gap-2 mb-4">
          {["stripe", "razorpay"].map((g) => (
            <button key={g} onClick={() => setGateway(g)}
              className={`text-xs px-3 py-1.5 rounded border flex items-center gap-1.5 ${gateway === g ? "font-bold" : ""}`}
              style={{
                borderColor: gateway === g ? "var(--primary)" : "var(--border)",
                background: gateway === g ? "color-mix(in srgb, var(--primary) 10%, transparent)" : "transparent",
              }}>
              <CreditCard size={12} />
              {g === "stripe" ? "Stripe" : "Razorpay"}
              {gateway === g && form.is_active && <Badge tone="var(--rag-green)">Active</Badge>}
            </button>
          ))}
        </div>

        <div className="p-3 rounded mb-4 text-[11px]" style={{ background: "color-mix(in srgb, var(--primary) 8%, transparent)" }}>
          {gateway === "stripe"
            ? "Get your keys from dashboard.stripe.com → Developers → API keys."
            : "Get your keys from dashboard.razorpay.com → Settings → API keys."}
        </div>

        {gateway === "stripe" ? (
          <div className="grid grid-cols-1 gap-3">
            <label className="block">
              <span className="text-[10px] font-bold uppercase text-muted">Publishable Key</span>
              <input value={form.stripe_publishable} onChange={(e) => setForm({ ...form, stripe_publishable: e.target.value })}
                placeholder="pk_test_..."
                className="w-full text-xs p-1.5 rounded border bg-transparent mt-1 font-mono" style={{ borderColor: "var(--border)" }} />
            </label>
            <label className="block">
              <span className="text-[10px] font-bold uppercase text-muted">Secret Key</span>
              <input type="password" value={form.stripe_secret} onChange={(e) => setForm({ ...form, stripe_secret: e.target.value })}
                placeholder="sk_test_..."
                className="w-full text-xs p-1.5 rounded border bg-transparent mt-1 font-mono" style={{ borderColor: "var(--border)" }} />
            </label>
            <label className="block">
              <span className="text-[10px] font-bold uppercase text-muted">Webhook Secret</span>
              <input type="password" value={form.stripe_webhook_secret} onChange={(e) => setForm({ ...form, stripe_webhook_secret: e.target.value })}
                placeholder="whsec_..."
                className="w-full text-xs p-1.5 rounded border bg-transparent mt-1 font-mono" style={{ borderColor: "var(--border)" }} />
            </label>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3">
            <label className="block">
              <span className="text-[10px] font-bold uppercase text-muted">Key ID</span>
              <input value={form.razorpay_key_id} onChange={(e) => setForm({ ...form, razorpay_key_id: e.target.value })}
                placeholder="rzp_test_..."
                className="w-full text-xs p-1.5 rounded border bg-transparent mt-1 font-mono" style={{ borderColor: "var(--border)" }} />
            </label>
            <label className="block">
              <span className="text-[10px] font-bold uppercase text-muted">Key Secret</span>
              <input type="password" value={form.razorpay_key_secret} onChange={(e) => setForm({ ...form, razorpay_key_secret: e.target.value })}
                placeholder="••••••••"
                className="w-full text-xs p-1.5 rounded border bg-transparent mt-1 font-mono" style={{ borderColor: "var(--border)" }} />
            </label>
          </div>
        )}

        <div className="flex gap-4 mt-4">
          <label className="block">
            <span className="text-[10px] font-bold uppercase text-muted">Currency</span>
            <select value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value })}
              className="text-xs p-1.5 rounded border bg-transparent mt-1" style={{ borderColor: "var(--border)" }}>
              <option value="INR">INR (₹)</option>
              <option value="USD">USD ($)</option>
              <option value="EUR">EUR (€)</option>
            </select>
          </label>
          <label className="flex items-center gap-1.5 text-xs cursor-pointer self-end">
            <input type="checkbox" checked={form.test_mode} onChange={(e) => setForm({ ...form, test_mode: e.target.checked })} />
            Test Mode
          </label>
          <label className="flex items-center gap-1.5 text-xs cursor-pointer self-end">
            <input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />
            Active
          </label>
        </div>

        <button onClick={save} disabled={saving}
          className="mt-4 px-4 py-2 text-xs rounded text-white disabled:opacity-50 flex items-center gap-2"
          style={{ background: "var(--brand-grad)" }}>
          {saving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
          Save Payment Settings
        </button>
      </Section>
    </>
  );
}

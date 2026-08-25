"use client";
import { useState } from "react";
import { FileText, Receipt } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import {
  Badge, EmptyState, ErrorNote, PageHeader, Section, Skeleton, Table,
} from "@/components/ui";
import { ApiError, api, operatorApi } from "@/lib/api";
import { PLATFORM_ROLES } from "@/lib/roles";
import { useData } from "@/lib/useData";

export default function BillingPage() {
  return (
    <RequireAuth roles={PLATFORM_ROLES}>
      <Billing />
    </RequireAuth>
  );
}

const inr = (n: number) =>
  new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR",
                                   maximumFractionDigits: 2 }).format(n);

function Billing() {
  const invoices = useData(() => operatorApi.invoices());
  const tenants = useData(() => api.platformTenants());
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  async function issue(tenantId: string) {
    setBusy(tenantId);
    setError("");
    try {
      await operatorApi.issueInvoice(tenantId);
      invoices.reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not issue the invoice");
    } finally {
      setBusy("");
    }
  }

  return (
    <>
      <PageHeader
        title="Billing"
        sub="GST-compliant invoices, priced from the seats actually in use rather than the plan's headline number."
      />

      {error && <div className="mb-4"><ErrorNote message={error} /></div>}

      <div className="ds-card p-4 mb-4 text-xs text-muted leading-relaxed">
        Money never touches this application. The payment gateway sits behind the
        same provider contract as everything else, and no card detail is stored
        here in any form — an invoice is a record, not a charge.
      </div>

      <Section title="Issue an invoice" className="mb-4">
        {tenants.loading ? <Skeleton rows={3} /> : (
          <Table
            columns={["Institution", "Plan", "Status", "Seat limit", ""]}
            rows={(tenants.data ?? []).map((t) => [
              <span key="n" className="font-medium">{t.name}</span>,
              t.plan_name || <span key="p" className="text-muted">no plan</span>,
              <Badge key="s" tone={t.status === "active" ? "var(--rag-green)" : "var(--accent)"}>
                {t.status}
              </Badge>,
              t.seat_limit,
              <button key="b" disabled={!t.plan_name || busy === t.id}
                      onClick={() => void issue(t.id)}
                      className="btn btn-ghost btn-sm ds-focus"
                      title={t.plan_name ? "" : "Assign a plan first"}>
                <Receipt size={12} /> {busy === t.id ? "Issuing…" : "Issue"}
              </button>,
            ])}
          />
        )}
      </Section>

      <Section title="Invoices">
        {invoices.loading ? <Skeleton rows={4} /> :
         invoices.error ? <ErrorNote message={invoices.error} /> :
         (invoices.data ?? []).length === 0 ? (
          <EmptyState icon={FileText} title="No invoices yet"
                      desc="Issue one above for any institution with a plan assigned." />
        ) : (
          <Table
            columns={["Number", "Institution", "Period", "Subtotal", "GST", "Total", "Status"]}
            rows={(invoices.data ?? []).map((i) => [
              <code key="n" className="kbd">{i.number}</code>,
              i.tenant_name,
              new Date(i.period_start).toLocaleDateString("en-IN",
                                                          { month: "short", year: "numeric" }),
              inr(i.subtotal),
              <span key="g" className="text-muted">{inr(i.gst_amount)} ({i.gst_rate}%)</span>,
              <span key="t" className="font-bold">{inr(i.total)}</span>,
              <Badge key="s" tone={i.status === "paid" ? "var(--rag-green)" : "var(--accent)"}>
                {i.status}
              </Badge>,
            ])}
          />
        )}
      </Section>
    </>
  );
}

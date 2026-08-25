"use client";
import { Boxes, Building2, ScrollText, Users } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { ErrorNote, PageHeader, Section, Skeleton, StatCard } from "@/components/ui";
import { Workflow, type Step } from "@/components/Workflow";
import { api, type PlatformOverview } from "@/lib/api";
import { PLATFORM_ROLES } from "@/lib/roles";
import { useData } from "@/lib/useData";

export default function PlatformOverviewPage() {
  return (
    <RequireAuth roles={PLATFORM_ROLES}>
      <Overview />
    </RequireAuth>
  );
}

function Overview() {
  const { data, loading, error } = useData(() => api.platformOverview());

  if (loading) return <Skeleton rows={5} />;
  if (error) return <ErrorNote message={error} />;
  if (!data) return null;

  return (
    <>
      <PageHeader
        title="Platform overview"
        sub="The shape of the business and the shape of the system. No student data is reachable from this console."
      />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
        <StatCard icon={Building2} label="Institutions" value={data.tenants_total}
                  sub={`${data.tenants_active} active or in trial`} />
        <StatCard icon={Users} label="Seats sold" value={data.seats_sold}
                  tone="var(--secondary)" sub={`${data.plans} plan templates`} />
        <StatCard icon={Boxes} label="Capabilities configured"
                  value={`${data.capabilities_configured}/${data.capabilities_total}`}
                  tone={data.capabilities_configured < data.capabilities_total ? "var(--rag-amber)" : "var(--rag-green)"}
                  sub={`${data.providers_registered} providers registered`} />
        <StatCard icon={ScrollText} label="Audit events (7d)" value={data.audit_events_7d}
                  tone="var(--accent)" />
      </div>

      <Workflow title="Bringing an institution live" steps={platformSteps(data)} />

      <Section title="Engine readiness">
        <div className="text-xs text-muted leading-relaxed">
          {data.capabilities_configured} of {data.capabilities_total} capabilities
          have a provider configured. The rest are registered but inactive — the
          console shows the real state rather than an optimistic one, and a
          capability with no provider reports its dimension as unscored rather
          than guessing at a number.
        </div>
      </Section>
    </>
  );
}

/** What a platform operator does to put an institution on the air.
 *
 *  This slot used to hold a hand-written "where this build is" note claiming
 *  M0 was done and M1 was next. It was written once and never touched again,
 *  so a console whose entire purpose is showing the real state of the system
 *  was telling its operator the product was several months behind where it
 *  actually is. A hand-maintained status paragraph is a promise nobody keeps;
 *  this list is computed.
 */
function platformSteps(data: PlatformOverview): Step[] {
  return [
    {
      title: "Create the institution",
      detail: "A tenant gets its own schema. No query can cross the boundary.",
      href: "/platform/tenants",
      done: data.tenants_total > 0,
    },
    {
      title: "Put it on a plan",
      detail: "Seats, features and the billing terms. Seats cover everybody, not just students.",
      href: "/platform/plans",
      done: data.plans > 0,
    },
    {
      title: "Configure the engine providers",
      detail: data.capabilities_configured < data.capabilities_total
        ? `${data.capabilities_total - data.capabilities_configured} capabilit${data.capabilities_total - data.capabilities_configured === 1 ? "y has" : "ies have"} no provider, so their dimensions report as unscored.`
        : "Every capability has a provider. Nothing is silently unmeasured.",
      href: "/platform/providers",
      done: data.capabilities_configured >= data.capabilities_total,
    },
    {
      title: "Tune the game economy",
      detail: "XP, streak rules and quest weights. Shared across institutions.",
      href: "/platform/gamification",
    },
    {
      title: "Watch the audit log",
      detail: `${data.audit_events_7d} events in the last seven days. Every write by every admin.`,
      href: "/platform/audit",
    },
  ];
}

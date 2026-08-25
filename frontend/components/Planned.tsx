"use client";
import { Construction } from "lucide-react";
import { EmptyState, PageHeader } from "@/components/ui";

/** A screen that exists in the nav but not yet in the product.
 *
 *  Shown rather than hidden on purpose: the milestone plan is the shared
 *  artefact this build is working through, and a visible "M5" tells a
 *  stakeholder more than a nav item that quietly is not there. What it must
 *  never do is show plausible fake data — an empty room beats a stage set.
 */
export function Planned({ title, sub, milestone, what }: {
  title: string;
  sub?: string;
  milestone: string;
  what: string;
}) {
  return (
    <>
      <PageHeader title={title} sub={sub} />
      <div className="ds-card">
        <EmptyState
          icon={Construction}
          title={`Arrives in ${milestone}`}
          desc={what}
        />
      </div>
    </>
  );
}

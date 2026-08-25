"use client";
import Link from "next/link";
import {
  BookOpen, Check, Ear, Mic, PenLine, TriangleAlert,
} from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import {
  Badge, ErrorNote, GapMeter, PageHeader, Section, Skeleton,
} from "@/components/ui";
import { practiceApi, type SkillModule } from "@/lib/api";
import { useData } from "@/lib/useData";

export default function SkillsPage() {
  return (
    <RequireAuth roles={["student"]}>
      <Skills />
    </RequireAuth>
  );
}

const ICON: Record<string, typeof Mic> = {
  speaking: Mic,
  listening: Ear,
  reading: BookOpen,
  writing: PenLine,
};

/** How each readiness state is shown. The wording is the point.
 *
 *  A module that does not work says so on its own card, in the same place and
 *  the same shape as one that does. The alternative -- four identical tiles
 *  where three quietly go nowhere -- is how a product ends up feeling broken
 *  rather than unfinished, which is a much worse impression and an unfair one.
 */
const STATE: Record<string, { label: string; tone: string; note: string }> = {
  live: {
    label: "Working",
    tone: "var(--rag-green)",
    note: "Measured properly, with real content behind it.",
  },
  partial: {
    label: "Partly built",
    tone: "var(--rag-amber)",
    note: "Some of this works. The card says which part does not.",
  },
  planned: {
    label: "Not built",
    tone: "var(--muted)",
    note: "Listed so the gap is visible rather than something you discover.",
  },
};

function Skills() {
  const { data, loading, error } = useData(() => practiceApi.skills());

  if (loading) return <Skeleton rows={6} />;
  if (error) return <ErrorNote message={error} />;
  if (!data) return null;

  return (
    <>
      <PageHeader
        title="The four skills"
        sub={data.headline}
      />

      <div className="grid md:grid-cols-2 gap-4">
        {data.modules.map((m) => <SkillCard key={m.key} module={m} />)}
      </div>

      {/* Said once, at the bottom, rather than repeated on every card. */}
      <Section title="Why some of these are empty" className="mt-4">
        <p className="text-xs text-muted leading-relaxed">
          This started as a spoken-English assessment, so Speaking is the part
          that is genuinely finished — the recording, the scoring and the
          reporting all exist for it. The other three are being built on top of
          that, and each one needs different machinery: Listening needs audio
          items with comprehension questions, Reading needs passages and a
          reading-rate measure, and Writing needs an essay scorer that does not
          exist yet at all.
        </p>
        <p className="text-xs text-muted leading-relaxed mt-2">
          They are listed here unfinished on purpose. A menu that only shows
          what works makes it impossible to tell the difference between a
          feature that is missing and one you simply have not found.
        </p>
      </Section>
    </>
  );
}

function SkillCard({ module: m }: { module: SkillModule }) {
  const Icon = ICON[m.key] ?? Mic;
  const state = STATE[m.status] ?? STATE.planned;
  const usable = m.href !== "";

  const body = (
    <>
      <div className="flex items-start gap-3">
        <span className="rounded-full p-2 shrink-0"
              style={{ background: `color-mix(in srgb, ${state.tone} 14%, transparent)` }}>
          <Icon size={17} style={{ color: state.tone }} />
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-bold">{m.label}</span>
            <Badge tone={state.tone}>
              {m.status === "live" && <Check size={9} />}
              {m.status === "partial" && <TriangleAlert size={9} />}
              {state.label}
            </Badge>
          </div>
          <p className="text-xs text-muted mt-1 leading-relaxed">{m.summary}</p>
        </div>
      </div>

      {/* A mastery number is shown only with the sentence that says where it
          came from. On Listening it is derived from repeat-accuracy, which
          includes Read Aloud -- a task with nothing to listen to -- so a bare
          percentage there would be a measurement of something else wearing
          this module's name. */}
      {m.mastery != null && (
        <div className="mt-3">
          <div className="flex items-baseline justify-between mb-1">
            <span className="text-[11px] font-semibold">Your mastery</span>
            <span className="text-[11px] text-muted">{m.mastery}%</span>
          </div>
          <GapMeter percent={m.mastery} />
          {m.mastery_basis && (
            <p className="text-[10px] text-muted mt-1.5 leading-relaxed">
              {m.mastery_basis}
            </p>
          )}
        </div>
      )}

      {m.measures.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-3">
          {m.measures.map((x) => (
            <span key={x} className="chip text-[10px]">{x}</span>
          ))}
        </div>
      )}

      {m.gap && (
        <div className="ds-inset p-2.5 mt-3">
          <p className="text-[11px] text-muted leading-relaxed">{m.gap}</p>
        </div>
      )}

      <div className="flex items-center gap-2 mt-3 pt-3 border-t border-border">
        <span className="text-[11px] text-muted flex-1">
          {m.item_count > 0
            ? `${m.item_count} items in the bank`
            : "No items yet"}
        </span>
        {usable && (
          <span className="text-[11px] font-semibold" style={{ color: state.tone }}>
            Practise →
          </span>
        )}
      </div>
    </>
  );

  // Nowhere honest to send anyone: the card is not a link rather than a link
  // to an apology.
  if (!usable) {
    return <div className="ds-card p-4 opacity-75">{body}</div>;
  }
  return (
    <Link href={m.href}
          className="ds-card p-4 hover:bg-surface2 transition-colors ds-focus block">
      {body}
    </Link>
  );
}

"use client";
import { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";

/* Shared primitives. Every colour here is a CSS variable — that is the whole
   reason sixteen themes work without sixteen sets of components. */

export { useToast } from "./Toast";

export function PageHeader({ title, sub, action }: {
  title: string; sub?: string; action?: ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4 mb-5">
      <div>
        <h1 className="text-xl font-bold text-text">{title}</h1>
        {sub && <p className="text-xs text-muted mt-1 max-w-2xl leading-relaxed">{sub}</p>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`ds-card p-4 ${className}`}>{children}</div>;
}

export function Section({ title, action, children, className = "", compact = false }: {
  title?: string; action?: ReactNode; children: ReactNode;
  className?: string; compact?: boolean;
}) {
  return (
    <section className={`ds-card ${compact ? "p-3" : "p-4"} ${className}`}>
      {(title || action) && (
        <div className="flex items-center justify-between gap-3 mb-3">
          {title && <h2 className="text-sm font-bold text-text">{title}</h2>}
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function StatCard({ icon: Icon, label, value, sub, tone = "var(--primary)" }: {
  icon?: LucideIcon; label: string; value: ReactNode; sub?: string; tone?: string;
}) {
  return (
    <div className="ds-card p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="text-[11px] font-semibold uppercase tracking-wide text-muted">{label}</div>
        {Icon && (
          <span className="rounded-full p-1.5" style={{ background: `color-mix(in srgb, ${tone} 14%, transparent)` }}>
            <Icon size={14} style={{ color: tone }} />
          </span>
        )}
      </div>
      <div className="text-2xl font-bold mt-2 leading-none" style={{ color: tone }}>{value}</div>
      {sub && <div className="text-[11px] text-muted mt-1.5">{sub}</div>}
    </div>
  );
}

export function EmptyState({ icon: Icon, title, desc, action }: {
  icon?: LucideIcon; title: string; desc?: string; action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center text-center py-12 px-6">
      {Icon && <Icon size={28} className="text-muted mb-3" />}
      <div className="text-sm font-semibold text-text">{title}</div>
      {desc && <p className="text-xs text-muted mt-1.5 max-w-sm leading-relaxed">{desc}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Badge({ children, tone = "var(--muted)" }: { children: ReactNode; tone?: string }) {
  return (
    <span className="chip" style={{
      color: tone,
      background: `color-mix(in srgb, ${tone} 14%, transparent)`,
      border: `1px solid color-mix(in srgb, ${tone} 26%, transparent)`,
    }}>
      {children}
    </span>
  );
}

export function Table({ columns, rows, onRowClick }: {
  columns: string[];
  rows: ReactNode[][];
  onRowClick?: (index: number) => void;
}) {
  return (
    <div className="overflow-x-auto thin-scroll">
      <table className="ds-table">
        <thead>
          <tr>{columns.map((c) => <th key={c}>{c}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}
                onClick={onRowClick ? () => onRowClick(i) : undefined}
                className={onRowClick ? "cursor-pointer" : ""}>
              {row.map((cell, j) => <td key={j}>{cell}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Progress({ value, tone }: { value: number; tone?: string }) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div className="ds-track">
      <div className="ds-fill" style={{ width: `${pct}%`, ...(tone ? { background: tone } : {}) }} />
    </div>
  );
}

/** Effort. Always rises, and says so (GAM-03). */
export function LevelMeter({ percent }: { percent: number }) {
  return (
    <div className="meter-level">
      <span style={{ width: `${Math.max(0, Math.min(100, percent))}%` }} />
    </div>
  );
}

/** Mastery. Can stall, and is allowed to look like it (GAM-03/23). */
export function GapMeter({ percent }: { percent: number }) {
  return (
    <div className="meter-gap">
      <span style={{ width: `${Math.max(0, Math.min(100, percent))}%` }} />
    </div>
  );
}

export function Avatar({ name, size = 28 }: { name: string; size?: number }) {
  const initials = name.split(" ").filter(Boolean).slice(0, 2).map((n) => n[0]).join("").toUpperCase();
  return (
    <span
      className="inline-flex items-center justify-center rounded-full font-bold shrink-0"
      style={{
        width: size, height: size, fontSize: size * 0.38,
        background: "color-mix(in srgb, var(--primary) 16%, transparent)",
        color: "var(--primary)",
      }}
    >
      {initials || "?"}
    </span>
  );
}

export function Tabs({ tabs, active, onChange }: {
  tabs: { id: string; label: string }[];
  active: string;
  onChange: (id: string) => void;
}) {
  return (
    <div className="flex gap-1 border-b border-border mb-4 overflow-x-auto thin-scroll">
      {tabs.map((t) => (
        <button
          key={t.id}
          onClick={() => onChange(t.id)}
          className={`px-3 py-2 text-xs font-semibold whitespace-nowrap border-b-2 -mb-px transition-colors ds-focus ${
            active === t.id ? "border-primary text-primary" : "border-transparent text-muted hover:text-text"
          }`}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function Skeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-2 animate-fade-in">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-9 rounded ds-inset" style={{ opacity: 1 - i * 0.12 }} />
      ))}
    </div>
  );
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <div className="ds-card p-4 text-xs" style={{ borderColor: "var(--rag-red)" }}>
      <div className="font-semibold mb-1" style={{ color: "var(--rag-red)" }}>Could not load this</div>
      <div className="text-muted">{message}</div>
    </div>
  );
}

/** A single-select answer choice — clearly selected, keyboard-friendly.
 *
 *  Replaces an ad-hoc button whose only "selected" cue was an 8% background
 *  tint and a `borderColor` set on an element that had no border to colour —
 *  so a picked answer was, on some themes, invisible. This gives selection a
 *  real affordance: a filled radio, a solid primary ring, a tinted fill and
 *  the label in the text colour, none of which depend on a theme's luck.
 */
export function ChoiceOption({ label, selected, onSelect, index }: {
  label: string; selected: boolean; onSelect: () => void; index?: number;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      onClick={onSelect}
      className="w-full flex items-center gap-3 text-left p-3 rounded-lg ds-focus transition-colors"
      style={{
        border: `1.5px solid ${selected ? "var(--primary)" : "var(--border)"}`,
        background: selected
          ? "color-mix(in srgb, var(--primary) 14%, var(--surface))"
          : "var(--surface)",
      }}
    >
      <span
        className="shrink-0 rounded-full flex items-center justify-center"
        style={{
          width: 18, height: 18,
          border: `2px solid ${selected ? "var(--primary)" : "var(--muted)"}`,
        }}
      >
        {selected && (
          <span className="rounded-full" style={{
            width: 8, height: 8, background: "var(--primary)",
          }} />
        )}
      </span>
      <span className="text-sm leading-snug"
            style={{ color: selected ? "var(--text)" : "var(--fg)",
                     fontWeight: selected ? 600 : 400 }}>
        {typeof index === "number" && (
          <span className="text-muted mr-1.5">{String.fromCharCode(65 + index)}.</span>
        )}
        {label}
      </span>
    </button>
  );
}

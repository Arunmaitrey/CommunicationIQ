import {
  Activity, Award, BarChart3, Boxes, Building2, ClipboardList, CreditCard,
  FileText, Flag, GraduationCap, Home, Layers, LineChart, ListChecks, Mic,
  ScrollText, Send, Settings, ShieldCheck, Sparkles, Target, Upload, Users,
  Wallet,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { Role } from "@/lib/api";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  roles: Role[];
  /** M0 shells exist but the feature lands later — the nav says so rather than
   *  pretending. Nothing here is hidden; a locked door is more honest than a
   *  missing one when the roadmap is the point. */
  milestone?: string;
  /** Icon colour. See TINT below. */
  tint?: string;
}

/** Icon colours for the rail.
 *
 *  Fixed values rather than theme tokens, and that is safe here for one
 *  specific reason: the rail is the only surface in the product whose colour
 *  does not vary. Every theme derives it from a single rule --
 *  `color-mix(in srgb, var(--primary) 10%, #0a2540)` -- so it is a dark navy
 *  in all seventeen. A palette tuned once for a dark background therefore
 *  holds everywhere, which a set of theme-derived hues would not: on the Gold
 *  theme every icon would come out gold, which is not colour-coding, it is
 *  just tinting.
 *
 *  Chosen for legibility on that navy rather than for brightness. These are
 *  the 300/400 band of each hue -- light enough to carry on a dark panel,
 *  desaturated enough that six of them side by side do not look like a toy.
 *  The colour is a wayfinding aid, not information: nothing is conveyed by
 *  hue alone, every item still has its own glyph and its own label.
 */
export const TINT = {
  sky: "#7dd3fc",
  teal: "#5eead4",
  emerald: "#6ee7b7",
  lime: "#bef264",
  amber: "#fcd34d",
  orange: "#fdba74",
  rose: "#fda4af",
  violet: "#c4b5fd",
  indigo: "#a5b4fc",
  cyan: "#67e8f9",
  slate: "#cbd5e1",
} as const;

export interface NavSection {
  title: string;
  items: NavItem[];
}

const STUDENT: Role[] = ["student"];
const TRAINER: Role[] = ["trainer"];
const TENANT: Role[] = ["tenant_admin"];
const PLATFORM: Role[] = ["super_admin", "finance", "content", "data_ml", "support"];

export const NAV: NavSection[] = [
  // Three verbs, in the order a student needs them.
  //
  // This was eight destinations: Today, Four skills,
  // Simulations, Progress, Drills, Quiz, Season. Four of those were practice
  // and three were progress, and the words separating them -- drill, quiz,
  // simulation -- are ours, not a student's. Nobody outside the team could
  // say which to open, so the honest description of that menu is that it
  // asked the user to understand our data model before they could practise.
  //
  // Every old route still resolves, so links and bookmarks keep working. What
  // changed is what a person is asked to choose between.
  {
    title: "Practice",
    items: [
      { href: "/home", label: "Today", icon: Home, roles: STUDENT, tint: TINT.amber },
      { href: "/practise", label: "Practise", icon: Target, roles: STUDENT, tint: TINT.teal },
      { href: "/tests", label: "Take a test", icon: Mic, roles: STUDENT, tint: TINT.violet },
      { href: "/my-progress", label: "My progress", icon: LineChart, roles: STUDENT, tint: TINT.sky },
    ],
  },
  {
    title: "Coaching",
    items: [
      { href: "/coaching", label: "Overview", icon: Home, roles: TRAINER, tint: TINT.amber },
      { href: "/cohorts", label: "Cohorts", icon: Users, roles: TRAINER, tint: TINT.cyan },
      { href: "/momentum", label: "Momentum", icon: Activity, roles: TRAINER, tint: TINT.lime },
      { href: "/flags", label: "At-risk flags", icon: Flag, roles: TRAINER, tint: TINT.rose },
    ],
  },
  {
    title: "Tenant",
    items: [
      { href: "/tenant", label: "Overview", icon: Building2, roles: TENANT, tint: TINT.sky },
      { href: "/tenant/users", label: "People", icon: Users, roles: TENANT, tint: TINT.cyan },
      { href: "/tenant/import", label: "Import", icon: Upload, roles: TENANT, tint: TINT.lime },
      { href: "/tenant/cohorts", label: "Cohorts", icon: GraduationCap, roles: TENANT, tint: TINT.teal },
      { href: "/tenant/readiness", label: "Readiness", icon: BarChart3, roles: TENANT, tint: TINT.emerald },
      { href: "/tenant/season", label: "Placement season", icon: ClipboardList, roles: TENANT, tint: TINT.orange },
      { href: "/tenant/profiles", label: "Assessments", icon: Layers, roles: TENANT, tint: TINT.violet },
      { href: "/tenant/invitations", label: "Invitations", icon: Send, roles: TENANT, tint: TINT.rose },
    ],
  },
  {
    title: "Platform",
    items: [
      { href: "/platform", label: "Overview", icon: Activity, roles: PLATFORM, tint: TINT.sky },
      { href: "/platform/tenants", label: "Tenants", icon: Building2, roles: PLATFORM, tint: TINT.cyan },
      { href: "/platform/plans", label: "Plans", icon: Wallet, roles: PLATFORM, tint: TINT.emerald },
      { href: "/platform/providers", label: "Providers", icon: Boxes, roles: PLATFORM, tint: TINT.violet },
      { href: "/platform/gamification", label: "Game economy", icon: Sparkles, roles: PLATFORM, tint: TINT.amber },
      { href: "/platform/audit", label: "Audit log", icon: ScrollText, roles: PLATFORM, tint: TINT.slate },
      { href: "/platform/billing", label: "Billing", icon: CreditCard, roles: PLATFORM, tint: TINT.lime },
      { href: "/platform/content", label: "Item bank", icon: FileText, roles: PLATFORM, milestone: "M6", tint: TINT.orange },
    ],
  },
  {
    title: "Account",
    items: [
      { href: "/settings", label: "Settings", icon: Settings, roles: [...STUDENT, ...TRAINER, ...TENANT, ...PLATFORM], tint: TINT.slate },
    ],
  },
];

export function navFor(role: Role | undefined): NavSection[] {
  if (!role) return [];
  return NAV
    .map((section) => ({ ...section, items: section.items.filter((i) => i.roles.includes(role)) }))
    .filter((section) => section.items.length > 0);
}

/** The two roles that sit an assessment.
 *
 *  An invited candidate is not a student -- no practice, no drills, no
 *  history, no home page -- but the environment check, the runner and their
 *  own report are the entire reason they were sent a link. Those three pages
 *  guarded on `["student"]` alone, so a candidate who consented was bounced
 *  off the assessment they had just agreed to sit.
 */
export const SITTING_ROLES: Role[] = ["student", "candidate"];

export function landingFor(role: Role | undefined): string {
  switch (role) {
    case "student": return "/home";
    // Was /cohorts, which is a table. A trainer signing in needs to be told
    // what to do this week before being shown how many students there are.
    case "trainer": return "/coaching";
    case "tenant_admin": return "/tenant";
    // A candidate has no home. They came for one assessment, and the pages
    // that run it are the only ones they may see -- so arriving here at all
    // means something already went wrong. The login screen is the honest
    // destination: they have no account to sign in with, but it says so.
    case "candidate": return "/login";
    // Named one by one rather than left to `default`.
    //
    // This used to end `default: return "/platform"`, which meant any role
    // the frontend did not recognise was sent to the operator console. That
    // is fail-open, and it fired in practice: `candidate` was missing from
    // the `Role` union, so a candidate rejected by a route guard was routed
    // to /platform. Whatever the next unrecognised role turns out to be, it
    // now lands on the login screen instead.
    case "super_admin":
    case "finance":
    case "content":
    case "data_ml":
    case "support":
      return "/platform";
    default: return "/login";
  }
}

export const ShieldIcon = ShieldCheck;
